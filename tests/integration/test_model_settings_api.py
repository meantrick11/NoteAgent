"""HTTP contract of the model settings API: gating, revisions, and redaction."""

import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient
from pydantic import SecretStr

from noteagent.bootstrap.app import AppContainer, create_app
from noteagent.bootstrap.settings import Settings
from noteagent.chat.history import ConversationStore, start_turn
from noteagent.db import Base, create_engine_from_url, create_session_factory
from noteagent.model_management.catalog import repo_dir_name
from noteagent.model_management.service import (
    ChatProbeResult,
    ModelRuntimeService,
    embedding_collection_name,
)
from noteagent.model_management.store import ModelSettingsStore
from noteagent.notes.repository import FileNoteRepository

MINILM = "sentence-transformers/all-MiniLM-L6-v2"
E5 = "intfloat/multilingual-e5-small"
SECRET_MARKER = "test-only-secret-do-not-echo"


class FakeAgent:
    """Chat agent stand-in; the API tests never stream."""

    async def stream(self, question: str, thread_id: str, turn_id: str | None = None):
        yield {"event": "assistant_final", "data": "ok"}

    def review(self, thread_id: str, action: str, write_action=None, file_name=None):
        return {"status": "rejected"}


class FakeEmbedder:
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, query: str) -> list[float]:
        return [float(len(query)), 1.0]


class FakeRetrieval:
    """Index stand-in that can be held open to keep a rebuild in progress."""

    def __init__(self, model_id: str, collection: str, block: threading.Event | None = None):
        self.model_id = model_id
        self.collection = collection
        self.indexed: list[str] = []
        self.errors: list[str] = []
        self.gone = False
        self._block = block

    def config_fingerprint(self) -> str:
        return f"fp:{self.model_id}"

    def verify_index(self) -> bool:
        return not self.gone

    def point_count(self) -> int:
        return len(self.indexed)

    def index_note(self, file_name: str) -> int:
        if self._block is not None:
            self._block.wait(timeout=5)
        if file_name in self.errors:
            raise RuntimeError(f"index failed for {file_name}")
        self.indexed.append(file_name)
        return 1

    def indexed_files(self) -> set[str]:
        return set(self.indexed)

    def delete_note(self, file_name: str) -> None:
        if file_name in self.indexed:
            self.indexed.remove(file_name)

    def search(self, query: str, top_k: int = 3) -> list[object]:
        return [object()] if self.indexed else []

    def is_indexed(self, file_name: str) -> bool:
        return file_name in self.indexed


class FakeAssembler:
    def __init__(self, block: threading.Event | None = None):
        self.retrievals: list[FakeRetrieval] = []
        self._by_collection: dict[str, FakeRetrieval] = {}
        self._block = block

    def build_chat_model(self, profile):
        raise AssertionError("API tests must not build a real chat model")

    def index_fingerprint(self, *, model_id, resolved_revision):
        return f"fp:{model_id}"

    def build_retrieval(
        self, *, model_id, resolved_revision, collection, local_files_only, create_if_missing
    ):
        existing = self._by_collection.get(collection)
        if existing is not None:
            return existing
        retrieval = FakeRetrieval(model_id, collection, self._block)
        self._by_collection[collection] = retrieval
        self.retrievals.append(retrieval)
        return retrieval

    def build_agent(self, *, profile, retrieval):
        return FakeAgent()


class Probe:
    """Injectable connection probe: answers from the test, or raises on demand."""

    def __init__(self):
        self.result = ChatProbeResult(streaming=True, tool_calling=True)
        self.error: Exception | None = None
        self.calls = 0

    async def __call__(self, profile) -> ChatProbeResult:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result


def write_cached_model(cache_dir: Path, model_id: str, revision: str = "rev1") -> None:
    """Create a complete HF-style cache entry so the catalog calls it available."""
    repo = cache_dir / repo_dir_name(model_id)
    (repo / "refs").mkdir(parents=True, exist_ok=True)
    (repo / "refs" / "main").write_text(revision, encoding="utf-8")
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.safetensors", "tokenizer.json"):
        (snapshot / name).write_bytes(b"payload")


def make_settings(tmp_path: Path) -> Settings:
    """Deterministic settings; .env never leaks into an API test."""
    return Settings(
        _env_file=None,
        deepseek_api_key=SecretStr("env-secret"),
        deepseek_api_base="",
        chat_model="env-chat-model",
        embedding_model=MINILM,
        chroma_collection="notes",
        notes_dir=tmp_path / "notes",
        chroma_dir=tmp_path / "chroma",
        log_dir=tmp_path / "logs",
        embedding_cache_dir=tmp_path / "models",
        model_settings_dir=tmp_path / "settings",
    )


def build_client(tmp_path: Path, *, block: threading.Event | None = None):
    """A test client plus the runtime, notes repository, probe, and history."""
    settings = make_settings(tmp_path)
    notes = FileNoteRepository(settings.notes_dir)
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    history = ConversationStore(create_session_factory(engine))
    probe = Probe()
    runtime = ModelRuntimeService(
        settings=settings,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=notes,
        assembler=FakeAssembler(block),
        probe=probe,
    )
    runtime.initialize()
    container = AppContainer(
        settings=settings,
        notes=notes,
        engine=engine,
        history=history,
        model_runtime=runtime,
    )
    return TestClient(create_app(container)), runtime, notes, probe, history


def wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    """Poll the job endpoint until the rebuild leaves the running state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/model-settings/jobs/{job_id}").json()
        if body["status"] != "running":
            return body
        time.sleep(0.01)
    raise AssertionError("job did not finish in time")


def compatible_profile(**overrides) -> dict:
    """A profile body for an OpenAI-compatible endpoint."""
    values: dict[str, object] = {
        "label": "本地兼容服务",
        "provider": "openai-compatible",
        "model": "qwen2.5",
        "base_url": "http://localhost:1234/v1",
        "api_key": "ui-key",
        "context_window": 8192,
    }
    values.update(overrides)
    return values


# ---------- 状态与脱敏 ----------


def test_status_reports_the_environment_default(tmp_path):
    """A fresh install shows the env profile as active and retrieval as available."""
    client, _, _, _, _ = build_client(tmp_path)

    body = client.get("/model-settings").json()

    assert body["revision"] == 0
    assert body["active_chat"]["model"] == "env-chat-model"
    assert body["active_chat"]["credential_source"] == "env"
    assert body["active_embedding"]["model_id"] == MINILM
    assert body["retrieval_available"] is True
    assert body["busy"] is False
    assert body["embedding_job"] is None


def test_invalid_profile_never_echoes_secret(tmp_path):
    """A rejected body must not send the submitted key back in the error detail."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/test",
        json={
            "label": "invalid",
            "provider": "unsupported",
            "model": "demo",
            "base_url": "https://example.invalid",
            "api_key": SECRET_MARKER,
            "context_window": 32768,
        },
    )

    assert response.status_code == 422
    assert SECRET_MARKER not in response.text
    assert response.json()["code"] == "invalid_request"


def test_bad_base_url_is_rejected_without_echoing_it(tmp_path):
    """Validation errors keep the location and message, not the raw input."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/test",
        json=compatible_profile(base_url="https://user:pass@host/v1"),
    )

    assert response.status_code == 422
    assert "pass" not in response.text
    assert response.json()["retryable"] is False


def test_stored_profile_response_has_no_key(tmp_path):
    """Saving returns the masked shape; the key stays server-side."""
    client, _, _, _, _ = build_client(tmp_path)

    created = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(api_key=SECRET_MARKER, expected_revision=0),
    )

    assert created.status_code == 201
    body = created.json()
    assert body["has_api_key"] is True
    assert "api_key" not in body
    assert SECRET_MARKER not in created.text

    listed = client.get("/model-settings").json()
    assert SECRET_MARKER not in str(listed)


def test_saving_a_profile_does_not_activate_it(tmp_path):
    """POST /chat/profiles only stores; the active pointer stays put."""
    client, _, _, _, _ = build_client(tmp_path)

    client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(expected_revision=0),
    )

    body = client.get("/model-settings").json()
    assert body["active_chat"]["model"] == "env-chat-model"
    assert len(body["chat_profiles"]) == 2


# ---------- 请求身份与删除 ----------


def test_create_ignores_a_client_supplied_id(tmp_path):
    """A new profile id is minted server-side, never taken from the body."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(id="chosen-by-client", expected_revision=0),
    )

    assert response.status_code == 201
    assert response.json()["id"] != "chosen-by-client"
    ids = {p["id"] for p in client.get("/model-settings").json()["chat_profiles"]}
    assert "chosen-by-client" not in ids
    assert response.json()["id"] in ids


def test_update_rejects_a_body_id_that_contradicts_the_url(tmp_path):
    """The URL owns the identity; a conflicting body id is a validation error."""
    client, _, _, _, _ = build_client(tmp_path)
    created = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(expected_revision=0),
    ).json()

    response = client.put(
        f"/model-settings/chat/profiles/{created['id']}",
        json=compatible_profile(id="someone-else", expected_revision=1),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_profile"


def test_delete_removes_a_non_active_profile(tmp_path):
    """Deleting a draft profile removes exactly that one."""
    client, _, _, _, _ = build_client(tmp_path)
    created = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(expected_revision=0),
    ).json()

    response = client.delete(
        f"/model-settings/chat/profiles/{created['id']}?expected_revision=1"
    )

    assert response.status_code == 204
    ids = {p["id"] for p in client.get("/model-settings").json()["chat_profiles"]}
    assert created["id"] not in ids
    assert "env-default" in ids


def test_delete_refuses_the_active_profile(tmp_path):
    """The running profile has to be switched away from first."""
    client, _, _, _, _ = build_client(tmp_path)
    active_id = client.get("/model-settings").json()["active_chat"]["id"]

    response = client.delete(
        f"/model-settings/chat/profiles/{active_id}?expected_revision=0"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "busy"
    assert client.get("/model-settings").json()["active_chat"]["id"] == active_id


def test_delete_requires_the_current_revision(tmp_path):
    """A stale tab must not delete what it has not seen the current state of."""
    client, _, _, _, _ = build_client(tmp_path)
    created = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(expected_revision=0),
    ).json()

    response = client.delete(
        f"/model-settings/chat/profiles/{created['id']}?expected_revision=0"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "revision_conflict"


def test_delete_unknown_profile_is_404(tmp_path):
    """Deleting something that is not stored is not a silent success."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.delete("/model-settings/chat/profiles/nope?expected_revision=0")

    assert response.status_code == 404
    assert response.json()["code"] == "profile_not_found"


def test_delete_refuses_a_cross_origin_call(tmp_path):
    """Deleting a credential-bearing profile is protected like the other writes."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.delete(
        "/model-settings/chat/profiles/env-default?expected_revision=0",
        headers={"origin": "https://evil.example", "host": "testserver"},
    )

    assert response.status_code == 403


def test_moving_the_env_profile_to_another_vendor_needs_a_key(tmp_path):
    """The .env DeepSeek key must not be reused for a different vendor."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/activate",
        json={
            "expected_revision": 0,
            "profile": {
                "id": "env-default",
                "label": "本地兼容服务",
                "provider": "openai-compatible",
                "model": "qwen2.5",
                "base_url": "http://localhost:1234/v1",
                "context_window": 8192,
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_profile"
    body = client.get("/model-settings").json()
    assert body["active_chat"]["credential_source"] == "env"
    assert body["revision"] == 0


def test_two_vendors_keep_their_own_keys_across_a_restart(tmp_path, caplog):
    """Both profiles and both credentials survive a restart, and never leak."""
    caplog.set_level("DEBUG")
    deepseek_key = "sk-deepseek-only-marker"
    compat_key = "sk-compat-only-marker"
    client, _, _, _, _ = build_client(tmp_path)
    first = client.post(
        "/model-settings/chat/profiles",
        json={
            "label": "DeepSeek 主账号",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "base_url": "",
            "api_key": deepseek_key,
            "context_window": 65536,
            "expected_revision": 0,
        },
    ).json()
    second = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(api_key=compat_key, expected_revision=1),
    ).json()
    activated = client.post(
        "/model-settings/chat/activate",
        json={"expected_revision": 2, "profile_id": second["id"]},
    )
    assert activated.status_code == 200

    restarted, _, _, _, _ = build_client(tmp_path)
    status = restarted.get("/model-settings").json()

    assert status["active_chat"]["id"] == second["id"]
    assert {p["id"] for p in status["chat_profiles"]} == {
        "env-default",
        first["id"],
        second["id"],
    }
    written = ModelSettingsStore(tmp_path / "settings").load()
    assert written.profile_by_id(first["id"]).api_key.get_secret_value() == deepseek_key
    assert written.profile_by_id(second["id"]).api_key.get_secret_value() == compat_key
    # 两个 Key 都不出现在任何响应、状态或日志里。
    assert deepseek_key not in restarted.get("/model-settings").text
    assert compat_key not in restarted.get("/model-settings").text
    assert deepseek_key not in caplog.text
    assert compat_key not in caplog.text


# ---------- 连接测试与激活 ----------


def test_connection_test_reports_capabilities_without_switching(tmp_path):
    """A test call probes the candidate and changes nothing."""
    client, _, _, probe, _ = build_client(tmp_path)
    probe.result = ChatProbeResult(streaming=True, tool_calling=False)

    response = client.post("/model-settings/chat/test", json=compatible_profile())

    assert response.status_code == 200
    assert response.json() == {
        "verified": False,
        "streaming": True,
        "tool_calling": False,
        "message": response.json()["message"],
    }
    assert probe.calls == 1
    assert client.get("/model-settings").json()["revision"] == 0


def test_connection_test_maps_a_provider_failure_to_502(tmp_path):
    """A refused endpoint is a 502 with a readable reason, not a raw exception."""
    from noteagent.model_management.service import ModelProbeFailedError

    client, _, _, probe, _ = build_client(tmp_path)
    probe.error = ModelProbeFailedError("模型服务认证失败，请检查 API Key")

    response = client.post("/model-settings/chat/test", json=compatible_profile())

    assert response.status_code == 502
    assert response.json()["code"] == "probe_failed"
    assert response.json()["retryable"] is True


def test_activation_switches_only_after_a_successful_probe(tmp_path):
    """The inline candidate is saved and enabled in one call."""
    client, _, _, probe, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/activate",
        json={"expected_revision": 0, "profile": compatible_profile()},
    )

    assert response.status_code == 200
    assert response.json()["model"] == "qwen2.5"
    assert probe.calls == 1
    body = client.get("/model-settings").json()
    assert body["active_chat"]["model"] == "qwen2.5"
    assert body["revision"] == 1


def test_activation_failure_leaves_the_active_profile_alone(tmp_path):
    """A probe that refuses the candidate must not move the pointer."""
    client, _, _, probe, _ = build_client(tmp_path)
    from noteagent.model_management.service import ProtocolUnsupportedError

    probe.error = ProtocolUnsupportedError("模型未通过验证：不支持 工具调用")

    response = client.post(
        "/model-settings/chat/activate",
        json={"expected_revision": 0, "profile": compatible_profile()},
    )

    assert response.status_code == 502
    body = client.get("/model-settings").json()
    assert body["active_chat"]["model"] == "env-chat-model"
    assert body["revision"] == 0


def test_activation_rejects_a_stale_revision(tmp_path):
    """A second tab holding an old revision gets a 409 and a way forward."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/activate",
        json={"expected_revision": 7, "profile": compatible_profile()},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "revision_conflict"
    assert response.json()["retryable"] is True


def test_activate_requires_exactly_one_target(tmp_path):
    """Neither "id and profile" nor "neither" is a valid request."""
    client, _, _, _, _ = build_client(tmp_path)

    both = client.post(
        "/model-settings/chat/activate",
        json={
            "expected_revision": 0,
            "profile_id": "env-default",
            "profile": compatible_profile(),
        },
    )
    neither = client.post("/model-settings/chat/activate", json={"expected_revision": 0})

    assert both.status_code == 422
    assert neither.status_code == 422


# ---------- 向量候选与切换 ----------


def test_embedding_candidates_do_not_leak_cache_paths(tmp_path):
    """The picker gets availability and reasons, never a local directory."""
    write_cached_model(tmp_path / "models", E5)
    client, _, _, _, _ = build_client(tmp_path)

    rows = client.get("/model-settings/embeddings").json()

    by_id = {row["model_id"]: row for row in rows}
    assert by_id[E5]["availability"] == "available"
    assert by_id[E5]["active"] is False
    assert by_id[MINILM]["active"] is True
    assert str(tmp_path) not in str(rows)
    assert "reason" in by_id[E5]


def test_switch_starts_a_job_and_reports_active_until_it_finishes(tmp_path):
    """202 means started: the old model stays active until the job succeeds."""
    write_cached_model(tmp_path / "models", E5)
    client, _, notes, _, _ = build_client(tmp_path)
    notes.create("Go.md", "Go")
    notes.write("Go.md", "注意力机制用 Query Key Value。\n", append=True)

    started = client.post(
        "/model-settings/embedding/switch",
        json={"model_id": E5, "expected_revision": 0},
    )

    assert started.status_code == 202
    body = started.json()
    assert body["unchanged"] is False
    assert body["job"]["target_model"] == E5
    assert body["job"]["active_model"] == MINILM
    finished = wait_for_job(client, body["job"]["id"])
    assert finished["status"] == "succeeded"

    status = client.get("/model-settings").json()
    assert status["active_embedding"]["model_id"] == E5
    assert status["active_embedding"]["collection"] == embedding_collection_name(
        "notes", E5, f"fp:{E5}"
    )
    assert status["retrieval_state"] == "ok"
    assert status["indexed_files"] == 1


def test_status_distinguishes_a_missing_index_from_an_empty_one(tmp_path):
    """丢失的索引必须报不可用，空语料则是一个有效的空索引。"""
    client, runtime, _, _, _ = build_client(tmp_path)

    fresh = client.get("/model-settings").json()
    assert fresh["retrieval_available"] is True
    assert fresh["retrieval_state"] == "empty"
    assert fresh["indexed_files"] == 0

    # 活动索引被外部删掉：状态立刻变差，而不是继续报可用。
    runtime.snapshot().retrieval.gone = True
    gone = client.get("/model-settings").json()
    assert gone["retrieval_available"] is False
    assert gone["retrieval_state"] == "missing"
    assert gone["retrieval_problem"]


def test_switch_to_the_same_model_is_unchanged(tmp_path):
    """Re-selecting the active model returns 200 with no job."""
    write_cached_model(tmp_path / "models", MINILM)
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/embedding/switch",
        json={"model_id": MINILM, "expected_revision": 0},
    )

    assert response.status_code == 200
    assert response.json() == {"unchanged": True, "job": None}


def test_switch_refuses_an_uncached_model(tmp_path):
    """A model that is not in the local cache cannot be selected."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/embedding/switch",
        json={"model_id": E5, "expected_revision": 0},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "model_unavailable"


def test_switch_rejects_an_arbitrary_path(tmp_path):
    """The model id is an id, never a filesystem path."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/embedding/switch",
        json={"model_id": "../../models", "expected_revision": 0},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "model_not_found"


def test_unknown_job_is_404(tmp_path):
    """An unknown job id is not reported as a running or finished job."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.get("/model-settings/jobs/nope")

    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"


# ---------- 维护窗口 ----------


def test_maintenance_window_blocks_chat_and_note_writes(tmp_path):
    """During a rebuild new chat and note writes are refused; reads still work."""
    write_cached_model(tmp_path / "models", E5)
    block = threading.Event()
    client, runtime, notes, _, history = build_client(tmp_path, block=block)
    notes.create("Go.md", "Go")
    conversation = history.create("t")
    history.append_message(conversation.id, "user", "hi", turn_id=start_turn())

    started = client.post(
        "/model-settings/embedding/switch",
        json={"model_id": E5, "expected_revision": 0},
    )
    job_id = started.json()["job"]["id"]
    try:
        assert client.get("/model-settings").json()["busy"] is True

        chat = client.post("/chat", json={"question": "你好", "thread_id": conversation.id})
        assert chat.status_code == 409
        assert chat.json()["code"] == "busy"

        create = client.post("/notes", json={"file_name": "New.md"})
        assert create.status_code == 409
        save = client.put("/notes/Go.md", json={"content": "# Go\n\n改过了。\n"})
        assert save.status_code == 409
        review = client.post(
            "/chat/review", json={"thread_id": conversation.id, "action": "reject"}
        )
        assert review.status_code == 409

        draft_update = client.put(
            "/chat/draft",
            json={"thread_id": conversation.id, "content": "## 改过了\n\n"},
        )
        assert draft_update.status_code == 409
        assert draft_update.json()["code"] == "busy"

        # 读路径不受影响。
        assert client.get("/notes").status_code == 200
        assert client.get(f"/notes/Go.md").status_code == 200
        assert client.get("/conversations").status_code == 200
    finally:
        block.set()
    assert wait_for_job(client, job_id)["status"] == "succeeded"

    # 被拒绝的聊天没有留下任何消息，笔记也没有落盘。
    messages = client.get(f"/conversations/{conversation.id}/messages").json()
    assert [m["role"] for m in messages] == ["user"]
    assert not notes.exists("New.md")
    assert "改过了" not in notes.read("Go.md")
    assert client.post("/notes", json={"file_name": "New.md"}).status_code == 200


def test_maintenance_window_blocks_profile_changes(tmp_path):
    """A candidate built from a stale profile must not be activated mid-rebuild."""
    write_cached_model(tmp_path / "models", E5)
    block = threading.Event()
    client, _, _, _, _ = build_client(tmp_path, block=block)

    started = client.post(
        "/model-settings/embedding/switch",
        json={"model_id": E5, "expected_revision": 0},
    )
    job_id = started.json()["job"]["id"]
    try:
        save = client.post(
            "/model-settings/chat/profiles",
            json=compatible_profile(expected_revision=1),
        )
        assert save.status_code == 409

        # 只读的状态查询仍然可用。
        assert client.get("/model-settings").status_code == 200
    finally:
        block.set()
    wait_for_job(client, job_id)


def test_cross_origin_write_is_refused(tmp_path):
    """A browser page on another origin must not post credentials to localhost."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(expected_revision=0),
        headers={"origin": "https://evil.example", "host": "testserver"},
    )

    assert response.status_code == 403


def test_same_origin_write_is_allowed(tmp_path):
    """The app's own page keeps working."""
    client, _, _, _, _ = build_client(tmp_path)

    response = client.post(
        "/model-settings/chat/profiles",
        json=compatible_profile(expected_revision=0),
        headers={"origin": "http://testserver", "host": "testserver"},
    )

    assert response.status_code == 201
