"""Тесты временных файлов, rate limiting, конфигурации и статусов."""

from pathlib import Path

import pytest
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.bot.texts import status_line, track_card
from app.config import ConfigError, Settings
from app.exceptions import LimitExceededError
from app.providers.base import TrackInfo
from app.services import media_converter
from app.utils.tempfiles import is_within, make_job_dir, remove_tree


def test_temp_dir_isolation_and_cleanup(tmp_path: Path) -> None:
    d = make_job_dir(tmp_path, "job1")
    assert d.exists() and d.name.startswith("job1-")
    (d / "file.bin").write_bytes(b"x")
    assert is_within(tmp_path, d / "file.bin")
    assert not is_within(tmp_path, tmp_path.parent / "other" / "x")
    remove_tree(d)
    assert not d.exists()


def test_cleanup_never_raises(tmp_path: Path) -> None:
    remove_tree(tmp_path / "does-not-exist")  # не падает


async def test_rate_limit_blocks_after_n(tmp_path=None) -> None:
    mw = RateLimitMiddleware(per_minute=3)
    calls = []

    async def handler(event, data):
        calls.append(event)
        return None

    class FakeUser:
        id = 42

    class FakeMsg:
        from_user = FakeUser()

        async def answer(self, text: str) -> None:
            calls.append("blocked")

    for _ in range(5):
        await mw(handler, FakeMsg(), {})  # type: ignore[arg-type]
    assert len(calls) == 5  # 3 прошло + 2 ответа "подожди"


def test_config_requires_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    s = Settings(BOT_TOKEN="")  # type: ignore[call-arg]
    with pytest.raises(ConfigError):
        s.validate_or_raise()


def test_config_parses_admin_ids() -> None:
    s = Settings(BOT_TOKEN="x", ADMIN_IDS="1, 2,3")
    assert s.admin_ids == [1, 2, 3]


def test_config_file_size_cap() -> None:
    s = Settings(BOT_TOKEN="x", MAX_FILE_SIZE_MB=5000)
    with pytest.raises(ConfigError):
        s.validate_or_raise()


async def test_size_limit_exceeded(tmp_path: Path) -> None:
    big = tmp_path / "big.bin"
    big.write_bytes(b"0" * (2 * 1024 * 1024))  # 2 МБ
    with pytest.raises(LimitExceededError):
        await media_converter.check_limits(big, max_size_mb=1, max_duration_s=None)


def test_status_line_progress() -> None:
    s = Settings(BOT_TOKEN="x")
    line = status_line(s, "download", 35, label="Загружаю")
    assert "35%" in line and "███" in line
    assert status_line(s, "search") == "🔎 Получаю информацию о файле..."


def test_status_line_custom_emoji() -> None:
    s = Settings(BOT_TOKEN="x", CUSTOM_EMOJI_SEARCH="6032850693348399258")
    line = status_line(s, "search")
    assert '<tg-emoji emoji-id="6032850693348399258">' in line


def test_welcome_text_uses_icons() -> None:
    from app.bot.texts import welcome_text

    plain = welcome_text(Settings(BOT_TOKEN="x"))
    assert "TikTok" in plain and "🔎" not in plain
    custom = welcome_text(
        Settings(BOT_TOKEN="x", CUSTOM_EMOJI_PLAY="5773626993010546707")
    )
    assert '<tg-emoji emoji-id="5773626993010546707">' in custom


def test_track_card_escapes_html() -> None:
    track = TrackInfo(
        source="youtube",
        url="https://youtu.be/x",
        title="<script>alert(1)</script>",
        artist="A & B <C>",
        duration=65,
    )
    card = track_card(Settings(BOT_TOKEN="x"), track)
    assert "<script>" not in card
    assert "&lt;script&gt;" in card
    assert "1:05" in card


async def test_ffmpeg_missing_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _: None)
    with pytest.raises(media_converter.FFmpegNotFoundError):
        media_converter.ensure_ffmpeg()
