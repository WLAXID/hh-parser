import enum
import logging
import re
from logging.handlers import RotatingFileHandler
from os import PathLike
from typing import Callable

# 10MB
MAX_LOG_SIZE = 10 << 20


class Color(enum.Enum):
    BLACK = 30
    RED = enum.auto()
    GREEN = enum.auto()
    YELLOW = enum.auto()
    BLUE = enum.auto()
    PURPLE = enum.auto()
    CYAN = enum.auto()
    WHITE = enum.auto()

    def __str__(self) -> str:
        return str(self.value)


class ColorHandler(logging.StreamHandler):
    _color_map = {
        "CRITICAL": Color.RED,
        "ERROR": Color.RED,
        "WARNING": Color.RED,
        "INFO": Color.GREEN,
        "DEBUG": Color.BLUE,
    }

    def format(self, record: logging.LogRecord) -> str:
        orig_exc_info = record.exc_info

        if self.level > logging.DEBUG:
            record.exc_info = None

        message = super().format(record)

        record.exc_info = orig_exc_info
        color_code = self._color_map[record.levelname]
        return f"\033[{color_code}m{message}\033[0m"


class RedactingFilter(logging.Filter):
    def __init__(
        self,
        patterns: list[str],
        # По умолчанию количество звездочек равно оригинальной строке
        placeholder: str | Callable = lambda m: "*" * len(m.group(0)),
    ):
        super().__init__()
        self.pattern = re.compile(f"({'|'.join(patterns)})") if patterns else None
        self.placeholder = placeholder

    def filter(self, record: logging.LogRecord) -> bool:
        if self.pattern:
            msg = record.getMessage()
            msg = self.pattern.sub(self.placeholder, msg)
            record.msg, record.args = msg, ()

        return True


def setup_logger(
    logger: logging.Logger,
    verbosity_level: int,
    log_file: PathLike,
) -> None:

    logger.setLevel(logging.DEBUG)
    color_handler = ColorHandler()

    color_handler.setFormatter(logging.Formatter("[%(levelname).1s] %(message)s"))
    color_handler.setLevel(verbosity_level)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=MAX_LOG_SIZE,
        backupCount=1,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    file_handler.setLevel(logging.DEBUG)

    redactor = RedactingFilter(
        [
            r"\b[A-Z0-9]{64,}\b",
            r"\b[a-fA-F0-9]{32,}\b",  # request_id, resume_id
        ]
    )

    file_handler.addFilter(redactor)

    for h in [color_handler, file_handler]:
        logger.addHandler(h)
