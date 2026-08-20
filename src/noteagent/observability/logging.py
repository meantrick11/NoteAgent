import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import colorama

colorama.init(autoreset=True)

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
        # Copy so file handlers still see uncolored levelname/name.
        record = logging.makeLogRecord(record.__dict__)
        color = _COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{_RESET}"
        record.name = f"{colorama.Style.DIM}{record.name}{_RESET}"
        return super().format(record)


def setup_logging(log_dir: Path, level: int = logging.DEBUG) -> None:
    """Configure root logging: colored stdout plus a rotating file under log_dir."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(ColoredFormatter(
        "%(asctime)s  %(levelname)-28s  %(name)-20s  %(message)s",
        datefmt="%H:%M:%S",
    ))
    root.addHandler(console)

    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        str(log_dir / "noteagent.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)

    # Keep third-party HTTP/model libraries from drowning app logs.
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
