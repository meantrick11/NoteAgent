"""Runtime snapshot, lease and embedding-maintenance behavior on a fake stack."""

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import SecretStr

from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import (
    disable_capability,
    initial_capabilities,
    text_verified,
)
from NoteAgent.Modules.Models.Domain.Vo.ModelCatalog import repo_dir_name
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Domain.Vo.ModelContracts import EmbeddingJobRecord, StoredModelSettings
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import (
    BusyError,
    InvalidProfileError,
    JobNotFoundError,
    ModelNotConfiguredError,
    ModelUnavailableError,
    RuntimeConfigurationError,
)
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Service.ModelRuntime import ModelRuntimeService
from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository
from NoteAgent.Modules.Retrieval.Engine.VectorStore.ChromaVectorStore import CollectionMissingError

from NoteAgent.Modules.Models.Domain.Po import ModelConfigModels  # noqa: F401

MINILM = "sentence-transformers/all-MiniLM-L6-v2"
E5 = "intfloat/multilingual-e5-small"


class FakeAgent:
    def __init__(self, tag: str, retrieval=None):
        self.tag = tag
        self.retrieval = retrieval


class FakeRetrieval:
    def __init__(self, model_id: str, collection: str, block: threading.Event | None = None):
        self.model_id = model_id
        self.collection = collection
        self.indexed: list[str] = []
        self._block = block

    def config_fingerprint(self) -> str:
        return f"fp:{self.model_id}"

    def verify_index(self) -> bool:
        return True

    def point_count(self) -> int:
        return len(self.indexed)

    def index_note(self, file_name: str) -> int:
        if self._block is not None:
            self._block.wait(timeout=5)
        self.indexed.append(file_name)
        return 1

    def indexed_files(self) -> set[str]:
        return set(self.indexed)

    def delete_note(self, file_name: str) -> None:
        if file_name in self.indexed:
            self.indexed.remove(file_name)

    def search(self, query: str, top_k: int = 3) -> list[object]:
        return [object()] if self.indexed else []


class FakeAssembler:
    def __init__(self, block: threading.Event | None = None):
        self.agents: list[FakeAgent] = []
        self.fail_models: set[str] = set()
        self.fail_retrieval = False
        self._block = block
        self._by_collection: dict[str, FakeRetrieval] = {}

    def index_fingerprint(self, *, model_id, resolved_revision):
        return f"fp:{model_id}"

    def build_retrieval(
        self, *, model_id, resolved_revision, collection, local_files_only, create_if_missing
    ):
        if self.fail_retrieval or model_id in self.fail_models:
            raise CollectionMissingError("missing")
        existing = self._by_collection.get(collection)
        if existing is not None:
            return existing
        retrieval = FakeRetrieval(model_id, collection, self._block)
        self._by_collection[collection] = retrieval
        return retrieval

    def build_agent(self, *, model, retrieval):
        agent = FakeAgent(model.id, retrieval)
        self.agents.append(agent)
        return agent


def make_settings(tmp_path: Path, **overrides) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "deepseek_api_key": SecretStr("env-secret"),
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
    repo = cache_dir / repo_dir_name(model_id)
    (repo / "refs").mkdir(parents=True, exist_ok=True)
    (repo / "refs" / "main").write_text(revision, encoding="utf-8")
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.safetensors", "tokenizer.json"):
        (snapshot / name).write_bytes(b"payload")


def _model(model_id: str = "m") -> ModelConfig:
    return ModelConfig(
        id=model_id,
        label="M",
        provider="deepseek",
        model="deepseek-chat",
        api_key="secret",
        is_active=True,
        capabilities=text_verified(
            initial_capabilities(),
            evidence={"streaming": True, "tool_calling": True},
            checked_at=datetime.now(UTC),
        ),
    )


def build_runtime(tmp_path: Path, *, model: ModelConfig | None = None, block=None):
    settings = make_settings(tmp_path)
    notes = FileNoteRepository(settings.notes_dir)
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    repository = SqlModelConfigRepository(create_session_factory(engine))
    if model is not None:
        repository.import_models([model], model.id)
    assembler = FakeAssembler(block)
    store = ModelSettingsStore(settings.model_settings_dir)
    service = ModelRuntimeService(
        settings=settings,
        repository=repository,
        store=store,
        notes=notes,
        assembler=assembler,
    )
    return service, repository, assembler, store, settings


def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition not reached")


def test_startup_without_active_model_is_degraded(tmp_path):
    service, *_ = build_runtime(tmp_path)
    service.initialize()
    assert service.snapshot().model is None
    with pytest.raises(ModelNotConfiguredError):
        with service.chat():
            pass


def test_startup_builds_agent_for_active_model(tmp_path):
    service, _, assembler, _, _ = build_runtime(tmp_path, model=_model())
    service.initialize()
    snapshot = service.snapshot()
    assert snapshot.model.id == "m"
    assert snapshot.revision == 1
    assert assembler.agents[0].tag == "m"
    with service.chat() as lease:
        assert lease.require_agent().tag == "m"


def test_active_model_without_verified_text_fails_startup(tmp_path):
    model = _model()
    model = model.model_copy(
        update={"capabilities": disable_capability(model.capabilities, "text")}
    )
    service, *_ = build_runtime(tmp_path, model=model)
    with pytest.raises(RuntimeConfigurationError, match="text"):
        service.initialize()


def test_sync_model_disables_chat_without_rebuilding_agent(tmp_path):
    service, repository, assembler, _, _ = build_runtime(tmp_path, model=_model())
    service.initialize()
    model = repository.get_model("m")
    disabled = repository.replace_capabilities(
        "m", model.revision, disable_capability(model.capabilities, "text")
    )
    service.sync_model(disabled)
    with pytest.raises(InvalidProfileError, match="text"):
        with service.chat():
            pass
    assert len(assembler.agents) == 1


def test_maintenance_window_blocks_chat_and_write_but_allows_reads(tmp_path):
    block = threading.Event()
    service, *_ = build_runtime(tmp_path, model=_model(), block=block)
    service.initialize()
    write_cached_model(service._settings.embedding_cache_dir, E5)
    unchanged, job = service.switch_embedding(model_id=E5, expected_revision=0)
    assert unchanged is False and job is not None
    wait_for(lambda: service._live_job is not None)
    with pytest.raises(BusyError):
        with service.chat():
            pass
    with pytest.raises(BusyError):
        with service.write():
            pass
    with service.read():
        pass
    block.set()
    service._job_thread.join(timeout=5)
    wait_for(lambda: service.status().busy is False)


def test_switch_publishes_new_retrieval_and_preserves_model(tmp_path):
    service, *_ = build_runtime(tmp_path, model=_model())
    service.initialize()
    write_cached_model(service._settings.embedding_cache_dir, E5)
    _, job = service.switch_embedding(model_id=E5, expected_revision=0)
    service._job_thread.join(timeout=5)
    snapshot = service.snapshot()
    assert snapshot.model.id == "m"
    assert snapshot.embedding.model_id == E5
    assert job is not None
    assert service.get_job(job.id).status == "succeeded"


def test_rebuild_failure_keeps_old_retrieval_and_records_failure(tmp_path):
    service, _, assembler, _, _ = build_runtime(tmp_path, model=_model())
    service.initialize()
    old = service.snapshot().retrieval
    write_cached_model(service._settings.embedding_cache_dir, E5)
    assembler.fail_models.add(E5)
    _, job = service.switch_embedding(model_id=E5, expected_revision=0)
    service._job_thread.join(timeout=5)
    assert service.snapshot().retrieval is old
    assert service.get_job(job.id).status == "failed"


def test_initialization_marks_running_job_interrupted(tmp_path):
    service, _, _, store, _ = build_runtime(tmp_path)
    job = EmbeddingJobRecord(
        id="j1",
        status="running",
        stage="indexing",
        active_model=MINILM,
        target_model=E5,
        started_at=datetime.now(UTC),
    )
    store.save(StoredModelSettings(revision=0, embedding_job=job))
    service.initialize()
    assert service.get_job("j1").status == "interrupted"


def test_retrieval_problem_is_reported(tmp_path):
    service, _, assembler, _, _ = build_runtime(tmp_path, model=_model())
    assembler.fail_retrieval = True
    service.initialize()
    status = service.status()
    assert status.retrieval_available is False
    assert status.retrieval_state == "missing"


def test_unknown_job_is_not_found(tmp_path):
    service, *_ = build_runtime(tmp_path)
    service.initialize()
    with pytest.raises(JobNotFoundError):
        service.get_job("missing")


def test_switch_refuses_missing_embedding_cache(tmp_path):
    service, *_ = build_runtime(tmp_path)
    service.initialize()
    with pytest.raises(ModelUnavailableError):
        service.switch_embedding(model_id=E5, expected_revision=0)
