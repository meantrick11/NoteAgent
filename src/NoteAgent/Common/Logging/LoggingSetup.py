import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorama

colorama.init(autoreset=True)
#日志颜色打印
_COLORS = {
    logging.DEBUG: colorama.Fore.CYAN,
    logging.INFO: colorama.Fore.GREEN,
    logging.WARNING: colorama.Fore.YELLOW,
    logging.ERROR: colorama.Fore.RED,
    logging.CRITICAL: colorama.Fore.MAGENTA,
}
_RESET = colorama.Style.RESET_ALL


class ColoredFormatter(logging.Formatter):
    """Color level and logger name for console output only."""

    def format(self, record):
        """Color the console line; copy the record so the file handler stays uncolored."""
        record = logging.makeLogRecord(record.__dict__)
        color = _COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{_RESET}"
        record.name = f"{colorama.Style.DIM}{record.name}{_RESET}"
        return super().format(record)


def setup_logging(log_dir: Path, level: int = logging.DEBUG) -> None:
    """Configure root logging: colored stdout plus a rotating file under log_dir."""
    root = logging.getLogger()
    root.handlers.clear()   #清理处理器
    root.setLevel(level)    #传入日志记录器初始等级，默认为DEBUG
    
    #1. 流式输出文件日志logger及其handler的初始化
    console = logging.StreamHandler(sys.stdout) #流式输出处理器/输出到标准屏幕
    console.setLevel(level) #同样处理器也设置DUBUG的日志等级
    console.setFormatter(ColoredFormatter(
        "%(asctime)s  %(levelname)-28s  %(name)-20s  %(message)s",
        datefmt="%H:%M:%S",
    ))  #设置日志的格式器   
    root.addHandler(console)    #将此流式输出日志添加到root根记录器中
    
    ##2. 配置文件输出日志logger日志handler的处理
    log_dir.mkdir(parents=True, exist_ok=True)     #创建日志文件
    file_handler = RotatingFileHandler(
        str(log_dir / "noteagent.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )   #日志文件处理器
    file_handler.setLevel(logging.DEBUG)    #硬性等级设置为DEBUG
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))  #同样设置输出格式
    root.addHandler(file_handler)   #同样添加到root的根目录日志记录器中

    # Keep third-party HTTP/model libraries from drowning app logs
    # #单独压低第三方库的日志等级，不让它们大量打印 DEBUG/INFO 垃圾日志，只保留警告和报错，保证你自己业务日志干净好看。.
    for name in (
        "openai",
        "openai._base_client",
        "httpx",
        "httpx_sse",
        "chromadb",
        "sentence_transformers",
        "urllib3",
        "watchfiles",
        "hpack",
        "httpcore",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
