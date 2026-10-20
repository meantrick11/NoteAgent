import logging
from dataclasses import dataclass

from sqlalchemy import Engine

from NoteAgent.AppBootstrap.RuntimeAssembler import BootstrapAssembler
from NoteAgent.AppBootstrap.AppSettings import Settings
from NoteAgent.Modules.Chat.Agent.Graph.ChatAgent import ChatAgent
from NoteAgent.Modules.Conversations.Service.PendingDrafts import DraftStore
from NoteAgent.Modules.Conversations.Legacy.LegacyConversationStore import ConversationStore
from NoteAgent.Modules.Conversations.Checkpoint.ConversationCheckpoints import CheckpointRuntime, postgres_uri
from NoteAgent.Modules.Conversations.Service.ConversationStateService import ConversationService
from NoteAgent.Common.Database import create_engine_from_url, create_session_factory
from NoteAgent.Modules.Models.Mapper.ModelSettingsStorage import ModelSettingsStore
from NoteAgent.Modules.Models.Mapper.SqlModelConfigRepository import SqlModelConfigRepository
from NoteAgent.Modules.Models.Provider.ProviderRegistry import ProviderRegistry
from NoteAgent.Modules.Models.Service.LegacyModelSettingsImporter import LegacyModelSettingsImporter
from NoteAgent.Modules.Models.Service.ModelActivationService import ModelActivationService
from NoteAgent.Modules.Models.Service.ModelConfigService import ModelConfigService
from NoteAgent.Modules.Models.Service.ModelRuntime import ModelRuntimeService
from NoteAgent.Modules.Notes.Storage.Markdown.MarkdownRepository import FileNoteRepository
from NoteAgent.Modules.Notes.Service.NoteChanges import NoteMutationService
from NoteAgent.Modules.Notes.Storage.Version.NoteVersions import NoteVersionStore
from NoteAgent.Common.WorkspaceAccess.NoteAccessGate import WorkspaceGate, is_postgres_url
from NoteAgent.Modules.Recovery.Service.RecoveryCoordinator import RecoveryCoordinator
from NoteAgent.Modules.Retrieval.Service.IndexRepairService import IndexRepairService
from NoteAgent.Modules.Retrieval.Service.NoteRetrievalService import RetrievalService
from NoteAgent.Modules.Sources.Service.SourceFileService import SourceFileService
from NoteAgent.Modules.Sources.Storage.LocalSourceFileStore import LocalSourceFileStore
from NoteAgent.Modules.Sources.Service.SourceFileWorker import SourceFileWorker
from NoteAgent.AppBootstrap.SourceVision import vision_factory

_logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Runtime dependencies shared by HTTP handlers."""

    settings: Settings  #基础配置问题
    notes: FileNoteRepository   #文件撰写相关
    engine: Engine  #数据库引擎
    history: ConversationStore  #历史消息存储/PostgreSQL连接
    # 唯一持有运行对象（模型/Agent/检索）的管理器；生产请求必须通过它取快照。
    model_runtime: ModelRuntimeService
    model_configs: ModelConfigService
    model_activation: ModelActivationService
    providers: ProviderRegistry
    # 会话元数据与 checkpoint：lifespan 负责 open/close，构造时还未连接。
    conversations: ConversationService | None = None
    checkpoints: CheckpointRuntime | None = None
    # 跨进程工作区门禁：read/chat 共享，mutate/recovery/model_rebuild 独占。
    workspace: WorkspaceGate | None = None
    # 影子 Git 版本仓库；Git 不可用时为 None（B3 必须拒绝无历史保护的写入）。
    versions: NoteVersionStore | None = None
    # 正式笔记写入的唯一入口（Library、草稿批准、导入）。
    mutations: NoteMutationService | None = None
    history_required: bool = False
    # 整体回退协调器：预览、启动、重试。
    recovery: RecoveryCoordinator | None = None
    source_files: SourceFileService | None = None
    source_worker: SourceFileWorker | None = None

    @property
    def retrieval(self) -> RetrievalService | None:
        """Read-only compatibility view; requests must use model_runtime instead."""
        return self.model_runtime.snapshot().retrieval

    @property
    def chat_agent(self) -> ChatAgent:
        """Read-only compatibility view; requests must use model_runtime instead."""
        return self.model_runtime.snapshot().require_agent()


def build_container(settings: Settings) -> AppContainer:
    """Wire notes, the model runtime, history, and the HTTP routes from settings."""
    # Fail fast on missing database config before loading the embedder model.
    if not settings.database_url.strip():
        _logger.error("DATABASE_URL is required (postgresql+psycopg://...)")
        raise ValueError("DATABASE_URL is required")
    #create-engine for memory
    engine = create_engine_from_url(settings.database_url)  #连接数据库的引擎初始化
    history = ConversationStore(create_session_factory(engine)) #将engine放到ConversationStore内部进行数据库连接等SELECT相关

    notes = FileNoteRepository(settings.notes_dir)  #Notes repository initialization
    drafts = DraftStore(history)

    # 只构造，不连接：异步 saver 必须由 lifespan 打开，否则没有地方关闭它。
    checkpoints = CheckpointRuntime.from_conn_string(postgres_uri(settings.database_url))
    session_factory = create_session_factory(engine)
    source_files = SourceFileService(session_factory, LocalSourceFileStore(settings.uploads_dir))
    # 门禁只用 libpq 连接（PostgreSQL）。SQLite 测试走进程内读写锁。
    workspace = WorkspaceGate(
        session_factory,
        libpq_dsn=postgres_uri(settings.database_url) if is_postgres_url(settings.database_url) else None,
    )
    conversations = ConversationService(
        session_factory, checkpoints,
        workspace_seq_provider=lambda: workspace.state().seq,
    )
    # 影子 Git 版本仓库：与 notes_dir、代码仓库 .git 隔离。Git 不可用时不阻断启动，
    # 但版本存储为 None，正式写入必须据此拒绝（无历史保护的写入不允许）。
    try:
        versions = NoteVersionStore(settings.notes_history_dir, settings.notes_dir)
    except Exception as exc:  # noqa: BLE001 - 启动不因缺少 Git 而失败
        _logger.error("shadow note repository unavailable: %s", exc)
        from NoteAgent.Modules.Notes.Service.NoteChanges import HistoryUnavailable
        raise HistoryUnavailable("shadow history unavailable; refusing unprotected writes") from exc
    mutations = (
        NoteMutationService(
            notes, versions, workspace, session_factory,
            repairs=IndexRepairService(session_factory, notes),
        )
        if versions is not None else None
    )
    repairs = IndexRepairService(session_factory, notes)

    # 装配器是 bootstrap 与 model_management 之间唯一的接口，避免两边互相导入。
    # 它拿到共享的会话服务与 checkpointer：切换模型只重建图运行对象，不换状态存储。
    catalog = ProviderRegistry()
    assembler = BootstrapAssembler(
        settings, notes, drafts, history, conversations, checkpoints, mutations, source_files,
        catalog=catalog,
    )
    model_settings_store = ModelSettingsStore(settings.model_settings_dir)
    model_repository = SqlModelConfigRepository(session_factory)
    LegacyModelSettingsImporter(
        repository=model_repository,
        catalog=catalog,
        store=model_settings_store,
        settings=settings,
    ).run()
    model_configs = ModelConfigService(repository=model_repository, catalog=catalog)
    model_runtime = ModelRuntimeService(
        settings=settings,
        repository=model_repository,
        store=model_settings_store,
        notes=notes,
        assembler=assembler,
        workspace=workspace,
    )
    # 持久化的 active 选择决定本次启动用哪个聊天模型与向量 collection。
    model_runtime.initialize()
    model_activation = ModelActivationService(
        repository=model_repository,
        config_service=model_configs,
        catalog=catalog,
        assembler=assembler,
        retrieval_provider=lambda: model_runtime.snapshot().retrieval,
        publisher=model_runtime,
    )
    source_worker = SourceFileWorker(
        source_files,
        vision_factory=lambda source: vision_factory(source, model_configs)
        if source.media_type in ("image/png", "image/jpeg", "application/pdf") else None,
    )

    recovery = None
    if mutations is not None:
        recovery = RecoveryCoordinator(
            session_factory=session_factory,
            gate=workspace,
            conversations=conversations,
            mutations=mutations,
            repairs=repairs,
            notes=notes,
            retrieval_provider=lambda: model_runtime.snapshot().retrieval,
        )

    return AppContainer(
        settings=settings,
        notes=notes,
        engine=engine,
        history=history,
        model_runtime=model_runtime,
        model_configs=model_configs,
        model_activation=model_activation,
        providers=catalog,
        conversations=conversations,
        checkpoints=checkpoints,
        workspace=workspace,
        versions=versions,
        mutations=mutations,
        history_required=True,
        recovery=recovery,
        source_files=source_files,
        source_worker=source_worker,
    )   ##返回一个AppContainer对象，包含所有初始化好的组件
