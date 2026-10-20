"""HTTP contract for the database-backed model configuration API."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgent.AppBootstrap.ContainerAssembly import AppContainer
from NoteAgent.AppBootstrap.HttpApp import create_app
from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Conversations.Legacy.LegacyConversationStore import ConversationStore
from NoteAgent.Modules.Models.Domain.Vo.ModelCatalog import repo_dir_name
from NoteAgent.Modules.Models.Domain.Vo.ModelErrors import ModelNotConfiguredError
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ModelProbes import ChatProbeResult
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Models.Service.ModelActivationService import ModelActivationService
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService
from NoteAgent.Modules.Models.Service.ModelRuntime import ModelRuntimeService
from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository

MINILM = "sentence-transformers/all-MiniLM-L6-v2"
E5 = "intfloat/multilingual-e5-small"


class FakeAgent:
    async def stream(self, question, thread_id, turn_id=None):
        yield {"event": "assistant_final", "data": "ok"}

    def review(self, thread_id, action, write_action=None, file_name=None):
        return {"status": "rejected"}


class FakeRetrieval:
    def __init__(self, model_id: str, collection: str, block=None):
        self.model_id = model_id
        self.collection = collection
        self.indexed: list[str] = []
        self._block = block

    def config_fingerprint(self):
        return f"fp:{self.model_id}"

    def verify_index(self):
        return True

    def point_count(self):
        return len(self.indexed)

    def index_note(self, file_name):
        if self._block is not None:
            self._block.wait(timeout=5)
        self.indexed.append(file_name)
        return 1

    def indexed_files(self):
        return set(self.indexed)

    def delete_note(self, file_name):
        if file_name in self.indexed:
            self.indexed.remove(file_name)

    def search(self, query, top_k=3):
        return [object()] if self.indexed else []


class FakeAssembler:
    def __init__(self, block=None):
        self._block = block
        self._by_collection = {}

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
        return retrieval

    def build_agent(self, *, model, retrieval):
        return FakeAgent()


class Probe:
    def __init__(self):
        self.result = ChatProbeResult(streaming=True, tool_calling=True)
        self.error = None
        self.vision = True
        self.calls = 0

    async def text(self, _client):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.result

    async def vision_probe(self, _client):
        return self.vision


def make_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        deepseek_api_key=SecretStr("env-secret"),
        chat_model="env-chat-model",
        embedding_model=MINILM,
        chroma_collection="notes",
        notes_dir=tmp_path / "notes",
        chroma_dir=tmp_path / "chroma",
        log_dir=tmp_path / "logs",
        embedding_cache_dir=tmp_path / "models",
        model_settings_dir=tmp_path / "settings",
    )


def write_cached_model(cache_dir: Path, model_id: str, revision: str = "rev1") -> None:
    repo = cache_dir / repo_dir_name(model_id)
    (repo / "refs").mkdir(parents=True, exist_ok=True)
    (repo / "refs" / "main").write_text(revision, encoding="utf-8")
    snapshot = repo / "snapshots" / revision
    snapshot.mkdir(parents=True, exist_ok=True)
    for name in ("config.json", "model.safetensors", "tokenizer.json"):
        (snapshot / name).write_bytes(b"payload")


def build_client(tmp_path: Path, *, block=None):
    settings = make_settings(tmp_path)
    engine = create_engine_from_url("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = SqlModelConfigRepository(factory)
    catalog = ProviderRegistry()
    probe = Probe()
    configs = ModelConfigService(
        repository=repository,
        catalog=catalog,
        probe_text=probe.text,
        probe_vision=probe.vision_probe,
        client_factory=lambda _config, _spec: object(),
    )
    assembler = FakeAssembler(block)
    runtime = ModelRuntimeService(
        settings=settings,
        repository=repository,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=FileNoteRepository(settings.notes_dir),
        assembler=assembler,
    )
    runtime.initialize()
    activation = ModelActivationService(
        repository=repository,
        config_service=configs,
        catalog=catalog,
        assembler=assembler,
        retrieval_provider=lambda: runtime.snapshot().retrieval,
        publisher=runtime,
        probe_text=probe.text,
        client_factory=lambda _config, _spec: object(),
    )
    container = AppContainer(
        settings=settings,
        notes=FileNoteRepository(settings.notes_dir),
        engine=engine,
        history=ConversationStore(factory),
        model_runtime=runtime,
        model_configs=configs,
        model_activation=activation,
        providers=catalog,
    )
    return TestClient(create_app(container)), container, probe, repository


def payload(**overrides):
    values = {
        "label": "A",
        "provider": "deepseek",
        "model": "deepseek-chat",
        "api_key": "secret",
        "max_tokens": 1024,
    }
    values.update(overrides)
    return values


def create(client, **overrides):
    response = client.post("/model-settings/models", json=payload(**overrides))
    assert response.status_code == 201, response.text
    return response.json()


def test_empty_status_and_provider_list(tmp_path):
    client, container, _, _ = build_client(tmp_path)
    body = client.get("/model-settings").json()
    assert body["models"] == []
    assert body["active_model"] is None
    assert "revision" not in body
    providers = client.get("/model-settings/providers").json()
    assert {item["id"] for item in providers} == {"deepseek", "openai", "openai-compatible"}
    with pytest.raises(ModelNotConfiguredError):
        with container.model_runtime.chat():
            pass


def test_create_model_is_inactive_and_secret_free(tmp_path):
    client, *_ = build_client(tmp_path)
    body = client.get("/model-settings").json()
    assert body["models"] == []
    created = client.post("/model-settings/models", json=payload()).json()
    assert created["is_active"] is False
    assert created["revision"] == 1
    assert created["has_api_key"] is True
    assert "api_key" not in created
    assert created["capabilities"][0]["capability"] == "text"
    assert created["capabilities"][0]["verification"] == "unverified"
    assert client.get("/model-settings").json()["models"][0]["id"] == created["id"]


def test_provider_validation_is_spec_driven(tmp_path):
    client, *_ = build_client(tmp_path)
    unknown = client.post("/model-settings/models", json=payload(provider="missing"))
    assert unknown.status_code == 422 and unknown.json()["code"] == "provider_not_found"
    missing_url = client.post(
        "/model-settings/models",
        json=payload(provider="openai-compatible", base_url=""),
    )
    assert missing_url.status_code == 422
    missing_key = client.post("/model-settings/models", json=payload(api_key=None))
    assert missing_key.status_code == 422


def test_update_uses_row_revision_and_protects_active(tmp_path):
    client, container, _, _ = build_client(tmp_path)
    created = create(client)
    updated = client.put(
        f"/model-settings/models/{created['id']}",
        json={**payload(label="B"), "expected_revision": 1},
    )
    assert updated.status_code == 200 and updated.json()["revision"] == 2
    stale = client.put(
        f"/model-settings/models/{created['id']}",
        json={**payload(label="C"), "expected_revision": 1},
    )
    assert stale.status_code == 409
    client.post(
        f"/model-settings/models/{created['id']}/activate",
        json={"expected_revision": 2},
    )
    protected = client.put(
        f"/model-settings/models/{created['id']}",
        json={**payload(label="D"), "expected_revision": 2},
    )
    assert protected.status_code == 409 and protected.json()["code"] == "model_active"


def test_activation_switches_only_after_a_successful_probe(tmp_path):
    client, container, probe, _ = build_client(tmp_path)
    created = create(client)
    activated = client.post(
        f"/model-settings/models/{created['id']}/activate",
        json={"expected_revision": 1},
    )
    assert activated.status_code == 200, activated.text
    body = activated.json()
    assert body["is_active"] is True
    assert body["revision"] == 2
    status = client.get("/model-settings").json()
    assert status["active_model"]["id"] == created["id"]
    assert container.model_runtime.snapshot().model.id == created["id"]

    second = create(client, label="B")
    probe.result = ChatProbeResult(streaming=False, tool_calling=False)
    failed = client.post(
        f"/model-settings/models/{second['id']}/activate",
        json={"expected_revision": 1},
    )
    assert failed.status_code == 502
    assert client.get("/model-settings").json()["active_model"]["id"] == created["id"]


def test_capability_verify_disable_and_stale_revision(tmp_path):
    client, container, probe, _ = build_client(tmp_path)
    created = create(client)
    text = client.post(
        f"/model-settings/models/{created['id']}/capabilities/text/verify",
        json={"expected_revision": 1},
    )
    assert text.status_code == 200
    assert text.json()["capabilities"][0]["verification"] == "verified"
    vision = client.post(
        f"/model-settings/models/{created['id']}/capabilities/vision/verify",
        json={"expected_revision": 2},
    )
    assert vision.status_code == 200
    assert {item["capability"] for item in vision.json()["capabilities"]} == {"text", "vision"}
    disabled = client.delete(
        f"/model-settings/models/{created['id']}/capabilities/vision",
        params={"expected_revision": 3},
    )
    assert disabled.status_code == 200
    vision_row = next(
        item for item in disabled.json()["capabilities"] if item["capability"] == "vision"
    )
    assert vision_row["status"] == "disabled"
    assert vision_row["verification"] == "unverified"
    stale = client.post(
        f"/model-settings/models/{created['id']}/capabilities/text/verify",
        json={"expected_revision": 1},
    )
    assert stale.status_code == 409


def test_test_endpoint_does_not_save_or_activate(tmp_path):
    client, container, probe, _ = build_client(tmp_path)
    created = create(client)
    response = client.post(f"/model-settings/models/{created['id']}/test")
    assert response.status_code == 200
    assert response.json()["verified"] is True
    assert container.model_runtime.snapshot().model is None
    probe.result = ChatProbeResult(streaming=True, tool_calling=False)
    failed = client.post(f"/model-settings/models/{created['id']}/test")
    assert failed.status_code == 200
    assert failed.json()["verified"] is False


def test_delete_rules(tmp_path):
    client, *_ = build_client(tmp_path)
    active = create(client)
    client.post(
        f"/model-settings/models/{active['id']}/activate", json={"expected_revision": 1}
    )
    refused = client.delete(
        f"/model-settings/models/{active['id']}", params={"expected_revision": 2}
    )
    assert refused.status_code == 409
    inactive = create(client, label="B")
    removed = client.delete(
        f"/model-settings/models/{inactive['id']}", params={"expected_revision": 1}
    )
    assert removed.status_code == 204
    assert [item["id"] for item in client.get("/model-settings").json()["models"]] == [active["id"]]


def test_cross_origin_writes_are_refused(tmp_path):
    client, *_ = build_client(tmp_path)
    refused = client.post(
        "/model-settings/models",
        json=payload(),
        headers={"Origin": "http://evil.example"},
    )
    assert refused.status_code == 403
    allowed = client.post(
        "/model-settings/models",
        json=payload(),
        headers={"Origin": "http://testserver"},
    )
    assert allowed.status_code == 201


def test_embedding_switch_still_uses_retrieval_revision(tmp_path):
    client, container, _, _ = build_client(tmp_path)
    write_cached_model(container.settings.embedding_cache_dir, E5)
    response = client.post(
        "/model-settings/embedding/switch",
        json={"model_id": E5, "expected_revision": 0},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job"]["id"]
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = client.get(f"/model-settings/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "succeeded"
    assert client.get("/model-settings").json()["active_embedding"]["model_id"] == E5
