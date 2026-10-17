"""Изоляция и очистка временных файлов."""

from __future__ import annotations

import secrets
import shutil
from pathlib import Path


def make_job_dir(base: Path, job_id: str) -> Path:
    """Создаёт изолированную директорию задания со случайным суффиксом."""
    path = base / f"{job_id}-{secrets.token_hex(6)}"
    path.mkdir(parents=True, exist_ok=False)
    return path


def remove_tree(path: Path) -> None:
    """Безопасно удаляет дерево временных файлов; не поднимает исключений."""
    try:
        if path.is_dir() and path.parent.name != "":
            shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass  # временные файлы не должны ронять обработку


def is_within(base: Path, candidate: Path) -> bool:
    """Проверяет, что путь не выходит за пределы базовой директории."""
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False
