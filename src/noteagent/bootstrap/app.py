import logging  #日志logging包
from contextlib import asynccontextmanager  #异步迭代器
from dataclasses import dataclass

from fastapi import FastAPI #FastAPI包
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Engine   #数据库连接engine

from noteagent.bootstrap.runtime import BootstrapAssembler
from noteagent.bootstrap.settings import Settings   #配置
from noteagent.chat.agent import ChatAgent  #聊天Agent
from noteagent.chat.drafts import DraftStore    #
from noteagent.chat.history import ConversationStore
from noteagent.chat.router import router as chat_router
from noteagent.notes.router import router as notes_router
from noteagent.db import create_engine_from_url, create_session_factory
from noteagent.model_management.router import (
    model_management_error_handler,
    router as model_settings_router,
    validation_error_handler,
)
from noteagent.model_management.service import (
    ModelManagementError,
    ModelRuntimeService,
)
from noteagent.model_management.store import ModelSettingsStore
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.service import RetrievalService
from noteagent.web import STATIC_DIR

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

    @property
    def retrieval(self) -> RetrievalService | None:
        """Read-only compatibility view; requests must use model_runtime instead."""
        return self.model_runtime.snapshot().retrieval

    @property
    def chat_agent(self) -> ChatAgent:
        """Read-only compatibility view; requests must use model_runtime instead."""
        return self.model_runtime.snapshot().chat_agent


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

    # 装配器是 bootstrap 与 model_management 之间唯一的接口，避免两边互相导入。
    assembler = BootstrapAssembler(settings, notes, drafts, history)
    model_runtime = ModelRuntimeService(
        settings=settings,
        store=ModelSettingsStore(settings.model_settings_dir),
        notes=notes,
        assembler=assembler,
    )
    # 持久化的 active 选择决定本次启动用哪个聊天模型与向量 collection。
    model_runtime.initialize()

    return AppContainer(
        settings=settings,
        notes=notes,
        engine=engine,
        history=history,
        model_runtime=model_runtime,
    )   ##返回一个AppContainer对象，包含所有初始化好的组件


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Stop model work, then dispose the SQLAlchemy engine, when the app shuts down."""
    yield
    app.state.container.model_runtime.shutdown()
    app.state.container.engine.dispose()


def create_app(container: AppContainer) -> FastAPI:
    """Build the FastAPI app and attach the runtime container."""   #创建FastAPI应用并attach运行时容器
    app = FastAPI(lifespan=lifespan)
    app.state.container = container   #将容器(包括所有的chat_agent,db,history等的一个container容器类)attach到应用状态
    # 模型设置的前端代码在 web/static 下，必须显式挂载才能被浏览器取到。
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    # 模型管理的错误结构与参数错误脱敏统一在这里注册，覆盖所有路由。
    app.add_exception_handler(ModelManagementError, model_management_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(chat_router)   #注册聊天路由
    app.include_router(notes_router)
    app.include_router(model_settings_router)
    return app   #返回FastAPI应用
