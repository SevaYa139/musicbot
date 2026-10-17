"""Настройка логирования: без секретов, с ротацией при запуске через Docker."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if root.handlers:  # idempotent при повторном вызове (тесты)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Библиотеки шумят на DEBUG — приглушаем по умолчанию
    for noisy in ("aiogram", "aiohttp", "yt_dlp", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
