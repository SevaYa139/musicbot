"""Очередь заданий: единый интерфейс, две реализации.

- MemoryJobQueue — локальная, asyncio-only (dev/один контейнер);
- RedisJobQueue — распределённая блокировка и дедупликация (production).

Worker тяжёлых задач запускается отдельно от polling-цикла бота.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.providers.base import MediaOption, TrackInfo


@dataclass(slots=True)
class JobRequest:
    """Всё необходимое для выполнения задания вне обработчика сообщения."""

    job_id: str
    user_id: int
    chat_id: int
    status_message_id: int
    track: TrackInfo
    option: MediaOption
    enqueued_at: float = field(default_factory=time.monotonic)


class JobQueue(ABC):
    @abstractmethod
    async def enqueue(self, job: JobRequest) -> int:
        """Ставит задание в очередь. Возвращает позицию (0 — выполняется сразу)."""

    @abstractmethod
    async def get(self) -> JobRequest | None:
        """Забирает следующее задание; None при закрытии очереди."""

    @abstractmethod
    async def task_done(self, job: JobRequest) -> None:
        """Отмечает завершение задания."""

    @abstractmethod
    async def position_of(self, job_id: str) -> int:
        """Текущая позиция задания в очереди (-1 если не найдено)."""

    @abstractmethod
    async def size(self) -> int:
        """Текущая длина очереди."""

    @abstractmethod
    async def cancel(self, job_id: str, user_id: int) -> bool:
        """Отмена задания (только владельцем). True при успехе."""

    @abstractmethod
    async def close(self) -> None:
        """Graceful shutdown: прекращает приём, дожидается завершения."""

    def is_cancelled(self, job_id: str) -> bool:
        """Флаг отмены задания (worker проверяет между этапами)."""
        return False
