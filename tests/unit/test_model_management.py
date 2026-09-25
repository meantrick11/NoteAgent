"""Runtime management: leases, the maintenance window, and rebuild publishing."""

import threading
import time
from pathlib import Path

import pytest
from pydantic import SecretStr

from noteagent.bootstrap.settings import Settings
from noteagent.model_management.catalog import repo_dir_name
from noteagent.model_management.schemas import (
    ChatActivateIn,
    ChatProfileIn,
    ChatProfileWriteIn,
    EmbeddingJobRecord,
    EmbeddingSwitchIn,
)
from noteagent.model_management.service import (
    BusyError,
    ChatProbeResult,
    InvalidProfileError,
    JobNotFoundError,
    ModelRuntimeService,
    ModelUnavailableError,
    ProtocolUnsupportedError,
    RepairRequiredError,
    RevisionConflictError,
    embedding_collection_name,
)
from noteagent.model_management.store import ModelSettingsStore
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore

MINILM = "sentence-transformers/all-MiniLM-L6-v2"
E5 = "intfloat/multilingual-e5-small"


# ---------- 测试替身 ----------


class FakeAgent:
    """Records which profile/retrieval it was built for."""

    def __init__(self, tag: str, retrieval=None):
        self.tag = tag
        self.retrieval = retrieval


class FakeRetrieval:
    """Stand-in index for one collection: tracks chunks, fails and blocks on demand."""

    def __init__(self, model_id: str, collection: str, block: threading.Event | None = None):
        self.model_id = model_id
        self.collection = collection
        self.indexed: list[str] = []
        self.deleted: list[str] = []
        # index_note 被调用的次数：测试用它确定"清单已抓取、索引进程中"。
        self.started = 0
        self._block = block
        self.fail_on: str | None = None

    def config_fingerprint(self) -> str:
        return f"fp:{self.model_id}"

    def index_note(self, file_name: str) -> int:
        self.started += 1
        if self._block is not None:
            self._block.wait(timeout=5)
        if self.fail_on == file_name:
            raise RuntimeError(f"index failed for {file_name}")
        self.indexed.append(file_name)
        return 1

    def indexed_files(self) -> set[str]:
        return set(self.indexed)

    def delete_note(self, file_name: str) -> None:
        self.deleted.append(file_name)
        if file_name in self.indexed:
            self.indexed.remove(file_name)

    def search(self, query: str, top_k: int = 3) -> list[object]:
        return [object()] if self.indexed else []


class FakeAssembler:
    """Builds fakes and remembers every object the service asked for.

    Retrievals are cached per collection, mirroring Chroma: the same collection keeps
    its stored vectors across rebuilds.
    """

    def __init__(self, block: threading.Event | None = None):
        self.retrievals: list[FakeRetrieval] = []
        self.agents: list[FakeAgent] = []
        self.fail_models: set[str] = set()
        self._by_collection: dict[str, FakeRetrieval] = {}
        self._block = block

    def build_chat_model(self, profile):
        return object()

    def build_retrieval(self, *, model_id, collection, local_files_only):
        if model_id in self.fail_models:
            raise RuntimeError(f"cannot load {model_id}")
        existing = self._by_collection.get(collection)
        if existing is not None:
            return existing
        retrieval = FakeRetrieval(model_id, collection, self._block)
        self._by_collection[collection] = retrieval
        self.retrievals.append(retrieval)
        return retrieval

    def build_agent(self, *, profile, retrieval):
        agent = FakeAgent(profile.id, retrieval)
        self.agents.append(agent)
        return agent


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Settings with fake cache and storage directories under tmp_path."""
    values: dict[str, object] = {
        "_env_file": None,
        "deepseek_api_key": SecretStr("env-secret"),
        "deepseek_api_base": "",
        "chat_model": "env-chat-model",
        "embedding_model": MINILM,
        "chroma_collection": "notes",
        "notes_dir": tmp_path / "notes",
        "chroma_dir": tmp_path / "chroma",
        "log_dir": tmp_path / "logs",
        "embedding_cache_dir": tmp_path / "models",
        "model_settings_dir": tmp_path / "settings",
    }
    values.update(overrides)
    return Settings(**values)


def write_cached_model(cache_dir: Path, model_id: str, revision: str = "rev1") -> None:
    """Create a complete HF-style cache entry so the catalog calls it available."""
    repo = cache_dir / repo_dir_name(model_id)
    (repo / "refs").mkdir(parents=True, exist_ok=True)
    (repo / "refs" / "main").write_text(revision, encoding="utf-8")
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.safetensors", "tokenizer.json"):
        (snapshot / name).write_bytes(b"payload")


def build_service(tmp_path: Path, *, block=None, probe=None, **overrides):
    """A started service plus its notes repository and assembler."""
    settings = make_settings(tmp_path, **overrides)
    notes = FileNoteRepository(settings.notes_dir)
    assembler = FakeAssembler(block)
    store = ModelSettingsStore(settings.model_settings_dir)
    service = ModelRuntimeService(
        settings=settings,
        store=store,
        notes=notes,
        assembler=assembler,
        probe=probe or ok_probe,
    )
    service.initialize()
    return service, notes, assembler, store


async def ok_probe(profile) -> ChatProbeResult:
    """A probe that reports both capabilities working."""
    return ChatProbeResult(streaming=True, tool_calling=True)


class TracingEmbedder:
    """Deterministic vectors that still carry a model name, so fingerprints differ."""

    def __init__(self, model_name: str):
        self.model_name = model_name

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [float(len(query)), 1.0]


class RealRetrievalAssembler:
    """Builds the real RetrievalService (real Chroma, fake embedder) per collection."""

    def __init__(self, settings: Settings, notes: FileNoteRepository):
        self._settings = settings
        self._notes = notes

    def build_chat_model(self, profile):
        return object()

    def build_retrieval(self, *, model_id, collection, local_files_only):
        return RetrievalService(
            notes=self._notes,
            chunker=MarkdownChunker(strategy=self._settings.chunk_strategy),
            embedder=TracingEmbedder(model_id),
            store=ChromaVectorStore(self._settings.chroma_dir, collection),
            embed_heading_prefix=self._settings.embed_heading_prefix,
        )

    def build_agent(self, *, profile, retrieval):
        return FakeAgent(profile.id, retrieval)


async def no_tools_probe(profile) -> ChatProbeResult:
    """A probe for a service that answers but cannot call tools."""
    return ChatProbeResult(streaming=True, tool_calling=False)


def wait_for_job(service: ModelRuntimeService, job_id: str, timeout: float = 5.0):
    """Poll until a rebuild stops running; the worker is a real thread."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = service.get_job(job_id)
        if job.status != "running":
            return job
        time.sleep(0.01)
    raise AssertionError("rebuild did not finish in time")


def wait_until(predicate, timeout: float = 5.0) -> None:
    """Poll until a condition holds; used to line a test up with the rebuild thread."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition never became true")


def activate_payload(profile_id: str, revision: int) -> ChatActivateIn:
    """Activate an existing stored profile by id."""
    return ChatActivateIn(expected_revision=revision, profile_id=profile_id)


def saved_profile(**overrides) -> ChatProfileWriteIn:
    """A creatable OpenAI-compatible profile."""
    values: dict[str, object] = {
        "label": "兼容服务",
        "provider": "openai-compatible",
        "model": "qwen2.5",
        "base_url": "http://localhost:1234/v1",
        "api_key": "ui-secret",
        "context_window": 8192,
        "expected_revision": 0,
    }
    values.update(overrides)
    return ChatProfileWriteIn(**values)


# ---------- 启动与快照 ----------


def test_initialize_builds_runtime_from_environment(tmp_path):
    """First boot uses the environment's model and collection, and stays available."""
    service, _, assembler, _ = build_service(tmp_path)

    snapshot = service.snapshot()

    assert snapshot.embedding_model_id == MINILM
    assert snapshot.collection == "notes"
    assert snapshot.retrieval is assembler.retrievals[0]
    assert snapshot.embedding.fingerprint == f"fp:{MINILM}"
    assert service.status().retrieval_available is True


def test_initialize_marks_a_running_job_interrupted(tmp_path):
    """A half-finished rebuild must never be treated as active after a restart."""
    settings = make_settings(tmp_path)
    notes = FileNoteRepository(settings.notes_dir)
    store = ModelSettingsStore(settings.model_settings_dir)
    document = store.load_effective(settings)
    store.save(
        document.model_copy(
            update={
                "embedding_job": EmbeddingJobRecord(
                    id="job-1",
                    status="running",
                    active_model=MINILM,
                    target_model=E5,
                    started_at=document.embedding_job.started_at
                    if document.embedding_job
                    else __import__("datetime").datetime.now(__import__("datetime").UTC),
                )
            }
        )
    )

    service = ModelRuntimeService(
        settings=settings,
        store=store,
        notes=notes,
        assembler=FakeAssembler(),
        probe=ok_probe,
    )
    service.initialize()

    assert service.status().embedding_job.status == "interrupted"
    assert service.snapshot().embedding_model_id == MINILM


def test_retrieval_problem_is_reported_instead_of_faking_an_index(tmp_path):
    """An unloadable model leaves retrieval explicitly unavailable, not empty."""

    class FailingAssembler(FakeAssembler):
        def build_retrieval(self, *, model_id, collection, local_files_only):
            raise RuntimeError("index config mismatch")

    settings = make_settings(tmp_path)
    service = ModelRuntimeService(
        settings=settings,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=FileNoteRepository(settings.notes_dir),
        assembler=FailingAssembler(),
        probe=ok_probe,
    )
    service.initialize()

    status = service.status()
    assert status.retrieval_available is False
    assert "不可用" in status.retrieval_problem


# ---------- 门禁与租约 ----------


def test_write_lease_is_counted_and_released(tmp_path):
    """A completed write must not leave the gate closed for later operations."""
    service, _, _, _ = build_service(tmp_path)

    with service.write() as snapshot:
        assert snapshot.chat_label
    # 释放后可以再次获取；计数没有泄漏。
    with service.chat():
        pass


async def test_chat_round_keeps_its_own_agent_after_activation(tmp_path):
    """A round started under A keeps A for its whole life; the next round uses B."""
    service, _, assembler, _ = build_service(tmp_path)
    with service.chat() as before:
        stored = service.save_chat_profile(saved_profile(), profile_id=None)
        await service.activate_chat(activate_payload(stored.id, service.status().revision))
        after = service.snapshot()
    assert before.chat_agent.tag != after.chat_agent.tag
    assert before.chat_agent is assembler.agents[0]
    assert after.chat_agent is assembler.agents[-1]
    assert after.chat_profile_id == stored.id


async def test_activation_is_refused_when_the_probe_says_no_tools(tmp_path):
    """Activation is transactional: a failed probe leaves the old agent in force."""
    service, _, assembler, _ = build_service(tmp_path, probe=no_tools_probe)
    original = service.snapshot()
    stored_revision = service.save_chat_profile(saved_profile(), profile_id=None)
    assert stored_revision.id

    with pytest.raises(ProtocolUnsupportedError):
        await service.activate_chat(
            activate_payload(stored_revision.id, service.status().revision)
        )

    assert service.snapshot().chat_agent is original.chat_agent


async def test_activation_rejects_a_stale_revision(tmp_path):
    """Two tabs cannot both publish on the same revision."""
    service, _, _, _ = build_service(tmp_path)
    stored = service.save_chat_profile(saved_profile(), profile_id=None)

    # 保存已经让 revision 前进，此时用旧 revision 提交必须被拒。
    with pytest.raises(RevisionConflictError):
        await service.activate_chat(activate_payload(stored.id, 0))


# ---------- 向量重建 ----------


def test_switch_builds_a_new_collection_and_publishes_it(tmp_path):
    """A successful rebuild swaps retrieval and the agent that binds it, together."""
    write_cached_model(tmp_path / "models", E5, revision="e5rev")
    service, notes, assembler, _ = build_service(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制用 Query Key Value。\n", append=True)

    unchanged, job = service.switch_embedding(
        model_id=E5, expected_revision=service.status().revision
    )
    assert unchanged is False
    finished = wait_for_job(service, job.id)

    assert finished.status == "succeeded"
    snapshot = service.snapshot()
    assert snapshot.embedding_model_id == E5
    assert snapshot.collection == "notes__multilingual-e5-small"
    assert snapshot.embedding.resolved_revision == "e5rev"
    assert snapshot.retrieval.model_id == E5
    # Agent 与工具是随新 retrieval 一起重建的。
    assert snapshot.chat_agent.retrieval is snapshot.retrieval
    assert service.status().embedding_job.status == "succeeded"


def test_switch_is_unchanged_when_model_and_fingerprint_match(tmp_path):
    """Re-selecting the active model must not rebuild anything."""
    write_cached_model(tmp_path / "models", MINILM)
    service, _, _, _ = build_service(tmp_path)

    unchanged, job = service.switch_embedding(
        model_id=MINILM, expected_revision=service.status().revision
    )

    assert unchanged is True
    assert job is None


def test_switch_refuses_an_incomplete_cache(tmp_path):
    """A directory without usable files is not a selectable model."""
    repo = tmp_path / "models" / repo_dir_name(E5)
    (repo / "snapshots").mkdir(parents=True)
    service, _, _, _ = build_service(tmp_path)

    with pytest.raises(ModelUnavailableError):
        service.switch_embedding(model_id=E5, expected_revision=service.status().revision)


def test_maintenance_window_blocks_chat_and_writes_but_allows_reads(tmp_path):
    """The rebuild gate is enforced in the service, not only in the UI."""
    write_cached_model(tmp_path / "models", E5)
    block = threading.Event()
    service, _, _, _ = build_service(tmp_path, block=block)

    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    try:
        assert service.status().busy is True
        with pytest.raises(BusyError):
            with service.chat():
                pass
        with pytest.raises(BusyError):
            with service.write():
                pass
        # 读取与状态查询不受影响。
        with service.read():
            pass
        assert service.status().embedding_job.status == "running"
    finally:
        block.set()
    assert wait_for_job(service, job.id).status == "succeeded"
    assert service.status().busy is False
    with service.chat():
        pass


def test_switch_is_refused_while_a_chat_is_in_flight(tmp_path):
    """An open lease must stop the maintenance window from opening."""
    write_cached_model(tmp_path / "models", E5)
    service, _, _, _ = build_service(tmp_path)

    with service.chat():
        with pytest.raises(BusyError):
            service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    # 租约释放后同一个切换可以被接受。
    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    assert wait_for_job(service, job.id).status == "succeeded"


def test_model_load_failure_keeps_the_old_index(tmp_path):
    """A candidate that cannot be loaded leaves retrieval and the agent untouched."""
    write_cached_model(tmp_path / "models", E5)
    service, _, assembler, _ = build_service(tmp_path)
    before = service.snapshot()
    assembler.fail_models.add(E5)

    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    finished = wait_for_job(service, job.id)

    assert finished.status == "failed"
    assert "cannot load" in finished.error
    assert service.snapshot().retrieval is before.retrieval
    assert service.snapshot().embedding_model_id == MINILM
    assert service.status().busy is False


def test_external_edit_during_rebuild_fails_the_job(tmp_path):
    """Writes the app did not make must not be silently missed by the new index."""
    write_cached_model(tmp_path / "models", E5)
    block = threading.Event()
    service, notes, assembler, _ = build_service(tmp_path, block=block)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "第一版。\n", append=True)

    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    # 等索引真正开始（此时清单已抓取），编辑才会落在 before/after 之间。
    wait_until(
        lambda: any(r.model_id == E5 and r.started > 0 for r in assembler.retrievals)
    )
    target = next(r for r in assembler.retrievals if r.model_id == E5)
    notes.write("Go.md", "外部追加的一行。\n", append=True)
    assert target.started > 0
    block.set()
    finished = wait_for_job(service, job.id)

    assert finished.status == "failed"
    assert "外部修改" in finished.error
    assert service.snapshot().embedding_model_id == MINILM


def test_empty_corpus_rebuild_succeeds(tmp_path):
    """A notes directory with no notes still produces a valid, empty index."""
    write_cached_model(tmp_path / "models", E5)
    service, _, _, _ = build_service(tmp_path)

    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    finished = wait_for_job(service, job.id)

    assert finished.status == "succeeded"
    assert service.snapshot().embedding_model_id == E5


def test_stale_vectors_are_dropped_by_the_rebuild(tmp_path):
    """Vectors for notes that no longer exist must not survive into the new index."""
    write_cached_model(tmp_path / "models", MINILM)
    write_cached_model(tmp_path / "models", E5)
    service, notes, assembler, _ = build_service(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制。\n", append=True)

    _, first = service.switch_embedding(
        model_id=E5, expected_revision=service.status().revision
    )
    wait_for_job(service, first.id)
    e5_collection = service.snapshot().retrieval
    # 切走再切回：回到 E5 必须重新全量构建，而不是直接复用旧 collection。
    _, away = service.switch_embedding(
        model_id=MINILM, expected_revision=service.status().revision
    )
    wait_for_job(service, away.id)
    # 上一次使用 E5 collection 时留下的、磁盘上已删除的笔记。
    e5_collection.indexed.append("Deleted.md")

    _, back = service.switch_embedding(
        model_id=E5, expected_revision=service.status().revision
    )
    wait_for_job(service, back.id)

    assert "Deleted.md" in e5_collection.deleted
    assert "Deleted.md" not in e5_collection.indexed_files()


def test_a_single_note_failure_aborts_the_rebuild(tmp_path):
    """One note that cannot be indexed must not leave a half-built index published."""
    write_cached_model(tmp_path / "models", E5)
    settings = make_settings(tmp_path)
    notes = FileNoteRepository(settings.notes_dir)
    notes.create("Good.md", "Good")
    notes.create("Bad.md", "Bad")
    notes.write("Good.md", "注意力机制。\n", append=True)
    notes.write("Bad.md", "检索。\n", append=True)
    assembler = FakeAssembler()
    service = ModelRuntimeService(
        settings=settings,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=notes,
        assembler=assembler,
        probe=ok_probe,
    )
    service.initialize()
    # 先把目标 collection 的检索对象取出来，才能在重建开始前埋下失败点。
    collection = embedding_collection_name(settings.chroma_collection, E5)
    target = assembler.build_retrieval(
        model_id=E5, collection=collection, local_files_only=True
    )
    target.fail_on = "Bad.md"

    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    finished = wait_for_job(service, job.id)

    assert finished.status == "failed"
    assert "index failed" in finished.error
    assert service.snapshot().embedding_model_id == MINILM


def test_persistence_failure_does_not_publish(tmp_path, monkeypatch):
    """If the new active pointer cannot be stored, the old objects stay in force."""
    write_cached_model(tmp_path / "models", E5)
    service, notes, _, store = build_service(tmp_path)
    notes.create("Go.md", "Go")
    before = service.snapshot()
    original_save = store.save

    def failing_save(document, *, expected_revision=None):
        if document.active_embedding is not None and document.active_embedding.model_id == E5:
            raise OSError("disk full")
        return original_save(document, expected_revision=expected_revision)

    monkeypatch.setattr(store, "save", failing_save)
    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    finished = wait_for_job(service, job.id)

    assert finished.status == "failed"
    assert service.snapshot().retrieval is before.retrieval
    assert service.snapshot().embedding_model_id == MINILM


def test_persisted_active_embedding_is_used_on_restart(tmp_path):
    """After a successful switch, a fresh start loads the new model and collection."""
    write_cached_model(tmp_path / "models", E5)
    service, _, _, _ = build_service(tmp_path)
    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    wait_for_job(service, job.id)

    restarted, _, assembler, _ = build_service(tmp_path)

    assert restarted.snapshot().embedding_model_id == E5
    assert restarted.snapshot().collection == "notes__multilingual-e5-small"
    assert assembler.retrievals[0].collection == "notes__multilingual-e5-small"


def test_unknown_job_is_not_found(tmp_path):
    """An unknown job id is a 404, not an empty result."""
    service, _, _, _ = build_service(tmp_path)

    with pytest.raises(JobNotFoundError):
        service.get_job("nope")


def test_rebuild_works_against_the_real_retrieval_stack(tmp_path):
    """The rebuild path must run against the real RetrievalService, not only fakes.

    Fakes that mirror the interface can hide a missing method; this drives a real
    Chroma collection and checks the new index is searchable and isolated.
    """
    write_cached_model(tmp_path / "models", E5)
    settings = make_settings(tmp_path)
    notes = FileNoteRepository(settings.notes_dir)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制用 Query Key Value。\n", append=True)
    assembler = RealRetrievalAssembler(settings, notes)
    service = ModelRuntimeService(
        settings=settings,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=notes,
        assembler=assembler,
        probe=ok_probe,
    )
    service.initialize()

    _, job = service.switch_embedding(model_id=E5, expected_revision=service.status().revision)
    finished = wait_for_job(service, job.id)

    assert finished.status == "succeeded", finished.error
    snapshot = service.snapshot()
    assert snapshot.embedding_model_id == E5
    assert snapshot.collection == "notes__multilingual-e5-small"
    assert snapshot.retrieval.is_indexed("Go.md") is True
    assert snapshot.retrieval.search("注意力", top_k=1)
    # 切换只写新集合：原 collection 依然没有这篇笔记的向量。
    assert ChromaVectorStore(settings.chroma_dir, "notes").has_file_name("Go.md") is False
    assert (
        ChromaVectorStore(settings.chroma_dir, "notes__multilingual-e5-small")
        .has_file_name("Go.md")
        is True
    )


# ---------- 配置写入 ----------


def test_saving_a_profile_does_not_activate_it(tmp_path):
    """Saving is separate from activating; the pointer only moves on activate."""
    service, _, assembler, _ = build_service(tmp_path)
    before = service.snapshot()

    stored = service.save_chat_profile(saved_profile(), profile_id=None)

    assert service.snapshot().chat_agent is before.chat_agent
    assert service.snapshot().chat_profile_id == before.chat_profile_id
    assert stored.has_api_key is True
    assert stored.credential_source == "ui"


def test_active_profile_cannot_be_edited_in_place(tmp_path):
    """Editing the live profile would desync the running client from the file."""
    service, _, _, _ = build_service(tmp_path)
    active_id = service.status().active_chat.id

    with pytest.raises(BusyError):
        service.save_chat_profile(
            saved_profile(label="改个名字", expected_revision=service.status().revision),
            profile_id=active_id,
        )


def test_editing_a_profile_without_a_key_keeps_the_stored_one(tmp_path):
    """A blank password box must not wipe the saved credential."""
    service, _, _, _ = build_service(tmp_path)
    created = service.save_chat_profile(saved_profile(), profile_id=None)

    updated = service.save_chat_profile(
        saved_profile(model="qwen3", api_key=None, expected_revision=service.status().revision),
        profile_id=created.id,
    )

    assert updated.model == "qwen3"
    assert updated.has_api_key is True


def test_key_required_but_missing_is_rejected(tmp_path):
    """A profile that needs a key cannot be saved without one."""
    service, _, _, _ = build_service(tmp_path)

    with pytest.raises(InvalidProfileError):
        service.save_chat_profile(
            saved_profile(api_key=None, clear_api_key=True), profile_id=None
        )


def test_keyless_compatible_service_is_allowed(tmp_path):
    """An explicitly keyless local service needs no credential."""
    service, _, _, _ = build_service(tmp_path)

    stored = service.save_chat_profile(
        saved_profile(api_key=None, auth_mode="none"), profile_id=None
    )

    assert stored.auth_mode == "none"
    assert stored.has_api_key is False


async def test_inline_candidate_is_saved_by_activation(tmp_path):
    """Activating a form candidate stores it as part of the same transaction."""
    service, _, _, _ = build_service(tmp_path)

    candidate = ChatProfileIn(
        label="临时候选",
        provider="openai-compatible",
        model="qwen2.5",
        base_url="http://localhost:1234/v1",
        api_key="ui-secret",
        context_window=8192,
    )
    active = await service.activate_chat(
        ChatActivateIn(
            expected_revision=service.status().revision,
            profile=candidate,
        )
    )

    ids = [profile.id for profile in service.status().chat_profiles]
    assert active.id in ids
    assert service.status().active_chat.id == active.id
    assert service.snapshot().chat_profile_id == active.id
