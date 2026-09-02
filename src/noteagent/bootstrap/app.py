import logging  #日志logging包
from contextlib import asynccontextmanager  #异步迭代器
from dataclasses import dataclass

from fastapi import FastAPI #FastAPI包
from sqlalchemy import Engine   #数据库连接engine

from noteagent.bootstrap.settings import Settings   #配置
from noteagent.chat.agent import ChatAgent  #聊天Agent
from noteagent.chat.context_budget import budget_from_settings
from noteagent.chat.drafts import DraftStore    #
from noteagent.chat.history import ConversationStore
from noteagent.chat.router import router as chat_router
from noteagent.chat.tools import build_chat_tools
from noteagent.db import create_engine_from_url, create_session_factory
from noteagent.llm.factory import create_chat_model
from noteagent.notes.repository import FileNoteRepository
from noteagent.retrieval.chunker import MarkdownChunker
from noteagent.retrieval.embedder import SentenceTransformerEmbedder
from noteagent.retrieval.service import RetrievalService
from noteagent.retrieval.vector_store import ChromaVectorStore

_logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Runtime dependencies shared by HTTP handlers."""

    settings: Settings  #基础配置问题
    notes: FileNoteRepository   #文件撰写相关
    retrieval: RetrievalService #RAG检索相关
    chat_agent: ChatAgent   #基础chatAgent
    engine: Engine  #数据库引擎
    history: ConversationStore  #历史消息存储/PostgreSQL连接


def build_container(settings: Settings) -> AppContainer:
    """Wire notes, retrieval, tools, the chat agent, and history from settings."""
    # Fail fast on missing database config before loading the embedder model.
    if not settings.database_url.strip():
        _logger.error("DATABASE_URL is required (postgresql+psycopg://...)")
        raise ValueError("DATABASE_URL is required")
    #create-engine for memory
    engine = create_engine_from_url(settings.database_url)  #连接数据库的引擎初始化
    history = ConversationStore(create_session_factory(engine)) #将engine放到ConversationStore内部进行数据库连接等SELECT相关

    notes = FileNoteRepository(settings.notes_dir)  #Notes repository initialization

    embedder = SentenceTransformerEmbedder(
        settings.embedding_model,
        cache_folder=settings.embedding_cache_dir,
        local_files_only=settings.embedding_local_files_only,
    )           #Embedding model initialization

    retrieval = RetrievalService(
        notes=notes,
        chunker=MarkdownChunker(),
        embedder=embedder,
        store=ChromaVectorStore(settings.chroma_dir, settings.chroma_collection),
    )
     #Retrieval service initialization
    drafts = DraftStore()

    tools = build_chat_tools(notes, retrieval, drafts)     #创建所有交给Agent的工具，包括笔记管理（CURD），RAG检索工具，草稿工具等

    chat_agent = ChatAgent(
        model=create_chat_model(settings),
        tools=tools,
        notes=notes,
        drafts=drafts,
        history=history,
        budget=budget_from_settings(settings),
        retrieval=retrieval,
    )       #上层封装Agent

    return AppContainer(
        settings=settings,
        notes=notes,
        retrieval=retrieval,
        chat_agent=chat_agent,
        engine=engine,
        history=history,
    )   ##返回一个AppContainer对象，包含所有初始化好的组件


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Dispose the SQLAlchemy engine when the app shuts down."""
    yield
    app.state.container.engine.dispose()


def create_app(container: AppContainer) -> FastAPI:
    """Build the FastAPI app and attach the runtime container."""   #创建FastAPI应用并attach运行时容器
    app = FastAPI(lifespan=lifespan)
    app.state.container = container   #将容器(包括所有的chat_agent,db,history等的一个container容器类)attach到应用状态
    app.include_router(chat_router)   #注册聊天路由
    return app   #返回FastAPI应用
