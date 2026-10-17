"""Обертки над FFmpeg/FFprobe.

Все вызовы — списком аргументов, без shell (защита от инъекций).
Тайм-ауты обязательны. Работа выполняется в потоке, event loop не блокируется.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

from app.exceptions import ConversionError, FFmpegNotFoundError, LimitExceededError

log = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 900
FFPROBE_TIMEOUT = 60


def ensure_ffmpeg() -> None:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise FFmpegNotFoundError(
            "FFmpeg не установлен. Установите ffmpeg и ffprobe (в Docker он уже включён)."
        )


async def _run(cmd: list[str], timeout_s: int) -> None:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise ConversionError("FFmpeg превысил лимит времени.") from exc
    if proc.returncode != 0:
        tail = (stderr or b"").decode("utf-8", "replace")[-400:]
        log.warning("ffmpeg rc=%s: %s", proc.returncode, tail)
        raise ConversionError("Ошибка обработки медиафайла.")


async def probe_duration(path: Path) -> float | None:
    """Длительность файла в секундах; None при сбое ffprobe."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=FFPROBE_TIMEOUT)
        data = json.loads(out.decode("utf-8", "replace"))
        return float(data["format"]["duration"])
    except (OSError, ValueError, KeyError, TimeoutError):
        return None


async def merge_streams(video: Path, audio: Path, out: Path) -> Path:
    """Объединяет раздельные видео- и аудиодорожки в один файл."""
    await _run(
        [
            "ffmpeg", "-y", "-i", str(video), "-i", str(audio),
            "-c", "copy", "-movflags", "+faststart", str(out),
        ],
        timeout_s=FFMPEG_TIMEOUT,
    )
    return out


async def convert_to_mp3(src: Path, out: Path, bitrate: str = "192") -> Path:
    await _run(
        [
            "ffmpeg", "-y", "-i", str(src),
            "-vn", "-codec:a", "libmp3lame", "-b:a", f"{bitrate}k", str(out),
        ],
        timeout_s=FFMPEG_TIMEOUT,
    )
    return out


async def make_telegram_thumbnail(src: Path, dest_dir: Path) -> Path | None:
    """Конвертирует обложку в JPEG 320x320 — формат миниатюр Telegram.

    Возвращает None при сбое: отправка без миниатюры лучше, чем ошибка.
    """
    if not await asyncio.to_thread(src.exists):
        return None
    out = dest_dir / "thumb.jpg"
    try:
        await _run(
            [
                "ffmpeg", "-y", "-i", str(src),
                "-vf", "scale='min(320,iw)':-1", "-frames:v", "1",
                "-q:v", "3", str(out),
            ],
            timeout_s=120,
        )
    except ConversionError:
        return None
    return out if out.exists() else None


async def check_limits(path: Path, max_size_mb: int, max_duration_s: int | None) -> None:
    """Проверяет размер и (опционально) длительность готового файла."""
    size_bytes = await asyncio.to_thread(lambda: path.stat().st_size)
    size_mb = size_bytes / (1024 * 1024)
    if size_mb > max_size_mb:
        raise LimitExceededError(
            f"Файл слишком большой ({size_mb:.0f} МБ при лимите {max_size_mb} МБ)."
        )
    if max_duration_s:
        duration = await probe_duration(path)
        if duration and duration > max_duration_s:
            raise LimitExceededError(
                f"Контент слишком длинный ({int(duration)} сек при лимите {max_duration_s})."
            )
