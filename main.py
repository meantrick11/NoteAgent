import logging

import uvicorn

from noteagent.bootstrap.app import build_container, create_app #构建Agent+FastAPI的函数
from noteagent.bootstrap.settings import Settings   #设置文件
from noteagent.observability.logging import setup_logging

_logger = logging.getLogger(__name__)


def main() -> None:
    """Start logging, assemble the app, and run uvicorn."""
    settings = Settings()   #读取初始化配置，包括模型URL、模型API、向量模型/向量存储地址、数据库URL等
    
    level = getattr(logging, settings.log_level.upper(), logging.DEBUG) #初始化日志

    setup_logging(settings.log_dir, level=level)    #设置

    _logger.info(
        "embedding model=%s cache=%s local_files_only=%s",
        settings.embedding_model,
        settings.embedding_cache_dir,
        settings.embedding_local_files_only,
    )   #模型初始化记录，向量模型的初始化
    
    container = build_container(settings)
    app = create_app(container)

    _logger.info("NoteAgent starting on %s:%s", settings.host, settings.port)
    
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
