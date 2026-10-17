"""Репозиторий: все обращения к БД в одном месте."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.database.models import ErrorLog, Job, User


class Repository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    # --- пользователи ---

    async def touch_user(self, telegram_id: int) -> None:
        """Создаёт пользователя или обновляет последнюю активность."""
        user = await self._s.get(User, telegram_id)
        now = datetime.now(UTC)
        if user is None:
            self._s.add(User(telegram_id=telegram_id, last_active=now))
        else:
            user.last_active = now
        await self._s.commit()

    async def bump_jobs(self, telegram_id: int, success: bool) -> None:
        col = User.successful_jobs if success else User.failed_jobs
        await self._s.execute(
            update(User)
            .where(User.telegram_id == telegram_id)
            .values({col: col + 1})
        )
        await self._s.commit()

    # --- задания ---

    async def create_job(self, job: Job) -> None:
        self._s.add(job)
        await self._s.commit()

    async def set_job_status(
        self, job_id: str, status: str, error: str | None = None
    ) -> None:
        now = datetime.now(UTC)
        values: dict[str, Any] = {"status": status}
        if status == "running":
            values["started_at"] = now
        if status in {"done", "failed", "cancelled"}:
            values["finished_at"] = now
        if error:
            values["error"] = error[:500]
        await self._s.execute(update(Job).where(Job.id == job_id).values(values))
        await self._s.commit()

    # --- ошибки ---

    async def log_error(
        self, message: str, job_id: str | None = None, source: str | None = None
    ) -> None:
        self._s.add(ErrorLog(job_id=job_id, source=source, message=message[:500]))
        await self._s.commit()

    # --- статистика для админки ---

    async def stats(self) -> dict[str, Any]:
        one_day_ago = datetime.now(UTC) - timedelta(hours=24)

        async def scalar(stmt: Select[Any]) -> int:
            value = await self._s.scalar(stmt)
            return int(value or 0)

        total_users = await scalar(select(func.count()).select_from(User))
        active_users = await scalar(
            select(func.count()).select_from(User).where(User.last_active >= one_day_ago)
        )
        done_jobs = await scalar(select(func.count()).select_from(Job).where(Job.status == "done"))
        failed_jobs = await scalar(
            select(func.count()).select_from(Job).where(Job.status == "failed")
        )
        avg_seconds = await self._s.scalar(
            select(
                func.avg(
                    func.extract(
                        "epoch", Job.finished_at - Job.started_at
                    )
                )
            ).where(Job.started_at.isnot(None), Job.finished_at.isnot(None))
        )
        by_source: dict[str, int] = {}
        rows = await self._s.execute(
            select(Job.source, func.count()).group_by(Job.source)
        )
        for source, count in rows.all():
            by_source[str(source)] = int(count)
        return {
            "users": total_users,
            "active_24h": active_users,
            "done_jobs": done_jobs,
            "failed_jobs": failed_jobs,
            "avg_seconds": round(float(avg_seconds), 1) if avg_seconds else None,
            "by_source": by_source,
        }

    async def purge_old_errors(self, days: int = 14) -> int:
        """Удаляет старые записи об ошибках — история не копится бесконечно."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        result = await self._s.execute(
            delete(ErrorLog).where(ErrorLog.created_at < cutoff)
        )
        await self._s.commit()
        return int(getattr(result, "rowcount", None) or 0)
