import asyncio
import logging
import sys
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from noteagent.bootstrap.app import build_container, create_app #构建Agent+FastAPI的函数
from noteagent.bootstrap.settings import Settings   #设置文件
from noteagent.observability.logging import setup_logging

_logger = logging.getLogger(__name__)

# psycopg 的异步驱动无法运行在 Windows 默认的 ProactorEventLoop 上，而 uvicorn 恰好会装它；
# checkpointer 的连接因此必须在 selector loop 上运行。生产镜像为 Linux，不受影响。
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def main() -> None:
    """Start logging, assemble the app, and run uvicorn."""
    settings = Settings()   #读取初始化配置，包括模型URL、模型API、向量模型/向量存储地址、数据库URL等
    
    level = getattr(logging, settings.log_level.upper(), logging.DEBUG) #初始化日志

    setup_logging(settings.log_dir, level=level)    #初始化设置logging模块中root等记录器的配置

    _logger.info(
        "embedding model=%s cache=%s local_files_only=%s",
        settings.embedding_model,
        settings.embedding_cache_dir,
        settings.embedding_local_files_only,
    )   #模型初始化记录，向量模型的初始化

    ini = Path(__file__).resolve().parent / "alembic.ini"   #数据库迁移操作，可以删除
    _logger.info("alembic upgrade head ini=%s", ini)
    command.upgrade(Config(str(ini)), "head")
    
    container = build_container(settings)
    app = create_app(container)

    _logger.info("NoteAgent starting on %s:%s", settings.host, settings.port)
    
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_config=None,
        # Windows 上 uvicorn 默认会装载 ProactorEventLoop，覆盖上面的 selector policy；
        # loop="none" 让它沿用当前 policy。Linux 保持 auto（可用 uvloop）。
        loop="none" if sys.platform == "win32" else "auto",
    )


if __name__ == "__main__":
    main()
