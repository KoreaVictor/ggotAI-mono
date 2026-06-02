"""콘솔 + 회전 파일 로깅 구성."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def setup_logging(level: int = logging.INFO) -> None:
    """루트 로거에 콘솔 + 회전 파일 핸들러를 1회 구성한다."""
    root = logging.getLogger()
    if root.handlers:  # 중복 구성 방지
        return
    root.setLevel(level)

    formatter = logging.Formatter(_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        _LOG_DIR / "ggotaiorder.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
