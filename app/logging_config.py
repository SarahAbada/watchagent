"""Central logging configuration with rotation and sanitization helpers."""

from __future__ import annotations

import html
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DEFAULT_LOG_DIR = "logs"
DEFAULT_LOG_FILE = "watchagent.log"


def sanitize_log_value(value: object) -> str:
    """Strip log-injection characters and neutralize script/SQL-sensitive symbols."""
    text = html.escape(str(value), quote=True)
    return text.replace("\n", "").replace("\r", "")


def configure_logging() -> None:
    log_dir = Path(os.environ.get("LOG_DIR", DEFAULT_LOG_DIR))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / os.environ.get("LOG_FILE", DEFAULT_LOG_FILE)

    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    root_logger.setLevel(logging.INFO)

    formatter = logging.Formatter(LOG_FORMAT)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    file_handler = RotatingFileHandler(
        filename=str(log_path),
        maxBytes=10 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)
