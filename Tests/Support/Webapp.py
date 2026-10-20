"""Build a real FastAPI app whose chat routes run the checkpoint graph.

The router, service, and checkpointer are the production objects; only the model and
the embedding stack are deterministic doubles. Assembled agents are rebuilt per
activation (like production) but always share one ConversationService and saver, so a
model switch can be observed to keep the same checkpoint store.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from NoteAgent.AppBootstrap.ContainerAssembly import AppContainer
from NoteAgent.AppBootstrap.HttpApp import create_app
from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgent.Modules.Conversations.Service.PendingDrafts import DraftStore
from NoteAgent.Modules.Conversations.Legacy.LegacyConversationStore import ConversationStore
from NoteAgent.AppBootstrap.ChatAgentFactory import build_graph_agent, local_checkpoints
from NoteAgent.Modules.Chat.Agent.Tools.ChatTools import build_chat_tools
from NoteAgent.Modules.Conversations.Checkpoint.ConversationCheckpoints import CheckpointRuntime
from NoteAgent.Modules.Conversations.Service.ConversationStateService import ConversationService
from NoteAgent.Common.Database import Base, create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Domain.Vo.ModelCapabilities import initial_capabilities, text_verified
from NoteAgent.Modules.Models.Domain.Vo.ModelConfig import ModelConfig
from NoteAgent.Modules.Models.Provider.ModelProbes import ChatProbeResult
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Models.Service.ModelActivationService import ModelActivationService
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService
from NoteAgent.Modules.Models.Service.ModelRuntime import ModelRuntimeService
from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository
from Support.Fakes import FakeChatModel, FakeRetrieval
from Support.Harness import TEST_BUDGET


class _StubRetrieval:
    """Placeholder index the chat routes never search."""

    def search(self, query: str, top_k: int = 3):
        return []

    def config_fingerprint(self) -> str:
        return "stub-config"

    def verify_index(self) -> bool:
        return True

    def point_count(self) -> int:
        return 0

    def index_note(self, file_name: str) -> int:
        return 0

    def delete_note(self, file_name: str) -> None:
        return None


class _GraphAssembler:
    """Rebuilds a graph agent per profile, sharing one service and checkpointer."""

    def __init__(self, app: "CheckpointApp") -> None:
        self._app = app

    def index_fingerprint(self, *, model_id: str, resolved_revision: str | None) -> str:
        return f"stub:{model_id}:{resolved_revision or ''}"

    def build_retrieval(
        self, *, model_id, resolved_revision, collection, local_files_only, create_if_missing
    ):
        return self._app.status_retrieval

    def build_agent(self, *, model, retrieval):
        client = self._app.next_model()
        self._app.model = client
        return build_graph_agent(
            model=client,
            tools=build_chat_tools(self._app.notes, self._app.agent_retrieval, self._app.drafts, web_reader=self._app.web_reader),
            notes=self._app.notes,
            drafts=self._app.drafts,
            budget=TEST_BUDGET,
            system_prompt="SYSTEM",
            service=self._app.service,
            checkpoints=self._app.checkpoints,
            retrieval=self._app.agent_retrieval,
        )


@dataclass
class CheckpointApp:
    """Everything a checkpoint-backed HTTP test needs to inspect after a request."""

    client: TestClient
    container: AppContainer
    service: ConversationService
    history: ConversationStore
    notes: FileNoteRepository
    drafts: DraftStore
    checkpoints: object
    status_retrieval: object
    agent_retrieval: FakeRetrieval
    model: FakeChatModel
    _reply_batches: list[list]
    web_reader: object | None = None

    def next_model(self):
        """One scripted model per built agent (initial + each activation).

        An entry that already looks like a chat model is used as-is, so a test can
        inject a model with custom streaming granularity.
        """
        if not self._reply_batches:
            return FakeChatModel([])
        entry = self._reply_batches.pop(0)
        if hasattr(entry, "astream"):
            return entry
        return FakeChatModel(list(entry))


def build_checkpoint_app(
    tmp_path: Path,
    *,
    reply_batches: list[list],
    sqlalchemy_url: str = "sqlite:///:memory:",
    libpq_dsn: str | None = None,
    web_reader: object | None = None,
) -> CheckpointApp:
    """Assemble the app; ``reply_batches`` scripts one model per build, in order.

    With ``libpq_dsn`` the saver is a real ``AsyncPostgresSaver`` opened through the
    app lifespan, so a rebuild over the same schema is a genuine restart.
    """
    settings = Settings(
        _env_file=None,
        deepseek_api_key=__import__("pydantic").SecretStr("env-secret"),
        notes_dir=tmp_path,
        chroma_dir=tmp_path / "chroma",
        model_settings_dir=tmp_path / "model_settings",
        frontend_mode="legacy",
    )
    engine = create_engine_from_url(sqlalchemy_url)
    Base.metadata.create_all(engine)
    factory = create_session_factory(engine)
    repository = SqlModelConfigRepository(factory)
    repository.import_models(
        [
            ModelConfig(
                id="env-default",
                label="env",
                provider="deepseek",
                model="env-chat-model",
                api_key="env-secret",
                is_active=True,
                capabilities=text_verified(
                    initial_capabilities(),
                    evidence={"streaming": True, "tool_calling": True},
                    checked_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                ),
            )
        ],
        "env-default",
    )
    history = ConversationStore(factory)
    notes = FileNoteRepository(tmp_path)
    drafts = DraftStore(history)
    checkpoints = (
        CheckpointRuntime.from_conn_string(libpq_dsn)
        if libpq_dsn is not None
        else local_checkpoints()
    )
    service = ConversationService(factory, checkpoints)

    app = CheckpointApp(
        client=None,  # type: ignore[arg-type]
        container=None,  # type: ignore[arg-type]
        service=service,
        history=history,
        notes=notes,
        drafts=drafts,
        checkpoints=checkpoints,
        status_retrieval=_StubRetrieval(),
        agent_retrieval=FakeRetrieval(),
        model=FakeChatModel([]),
        _reply_batches=list(reply_batches),
        web_reader=web_reader,
    )
    async def probe_client(_client):
        return ChatProbeResult(streaming=True, tool_calling=True)

    def client_factory(_config, _spec):
        return object()

    catalog = ProviderRegistry()
    assembler = _GraphAssembler(app)
    configs = ModelConfigService(
        repository=repository,
        catalog=catalog,
        probe_text=probe_client,
        client_factory=client_factory,
    )
    runtime = ModelRuntimeService(
        settings=settings,
        repository=repository,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=notes,
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
        probe_text=probe_client,
        client_factory=client_factory,
    )
    container = AppContainer(
        settings=settings,
        notes=notes,
        engine=engine,
        history=history,
        model_runtime=runtime,
        model_configs=configs,
        model_activation=activation,
        providers=catalog,
        conversations=service,
        checkpoints=checkpoints,
    )
    app.container = container
    app.client = TestClient(create_app(container))
    # The lifespan must run to open the Postgres saver; the in-memory one needs no open.
    if libpq_dsn is not None:
        app.client.__enter__()
    return app


@pytest.fixture
def pg_checkpoint_app(pg_target, tmp_path):
    """Factory for Postgres-backed checkpoint apps; every app is closed on teardown."""
    created: list[CheckpointApp] = []

    def factory(*, reply_batches: list[list], name: str = "") -> CheckpointApp:
        root = tmp_path / name if name else tmp_path
        root.mkdir(parents=True, exist_ok=True)
        app = build_checkpoint_app(
            root,
            reply_batches=reply_batches,
            sqlalchemy_url=pg_target.sqlalchemy_url,
            libpq_dsn=pg_target.libpq_dsn,
        )
        created.append(app)
        return app

    yield factory
    for app in created:
        app.client.__exit__(None, None, None)
        app.container.engine.dispose()


async def _probe(profile: ChatProfile) -> ChatProbeResult:
    """Always-successful probe so activation never touches the network."""
    return ChatProbeResult(streaming=True, tool_calling=True)
