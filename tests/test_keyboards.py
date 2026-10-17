"""Тесты доступности вариантов форматов (честные кнопки без фикции)."""

from app.bot.keyboards.inline import media_type_keyboard, options_keyboard
from app.providers.base import MediaOption, TrackInfo


def _track(options: list[MediaOption]) -> TrackInfo:
    return TrackInfo(
        source="youtube", url="https://youtu.be/x", title="T", artist="A", options=options
    )


def test_video_options_only_real_heights() -> None:
    track = _track(
        [
            MediaOption(kind="video", label="720p", option_id="v720", ext="mp4", height=720),
            MediaOption(kind="video", label="1080p", option_id="v1080", ext="mp4", height=1080),
            MediaOption(kind="audio", label="MP3 320 kbps", option_id="mp3-320", ext="mp3"),
        ]
    )
    kb = options_keyboard("sid", track, "video")
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "720p" in texts and "1080p" in texts
    assert "4K" not in texts and "480p" not in texts  # нет фиктивных кнопок
    assert "MP3 320 kbps" not in texts  # аудио не попадает в видео-меню


def test_no_video_button_when_only_audio() -> None:
    track = _track(
        [MediaOption(kind="audio", label="MP3 192 kbps", option_id="mp3-192", ext="mp3")]
    )
    kb = media_type_keyboard("sid", track)
    texts = [b.text for row in kb.inline_keyboard for b in row]
    assert "Аудио" in texts
    assert "Видео" not in texts
    assert any(b.url for row in kb.inline_keyboard for b in row if b.url)  # оригинал есть


def test_open_original_button_for_metadata_only_sources() -> None:
    track = _track([MediaOption(kind="audio", label="Открыть в Spotify", option_id="open", ext="")])
    kb = media_type_keyboard("sid", track)
    assert not any(
        "Аудио" in b.text or "Видео" in b.text
        for row in kb.inline_keyboard
        for b in row
    )
    assert any(b.text == "Открыть оригинал" for row in kb.inline_keyboard for b in row)


def test_owner_only_state_access() -> None:
    from app.bot.state import DialogState, StateStore

    store = StateStore()
    track = _track([])
    store.set("s1", DialogState(track=track, user_id=111))
    assert store.get("s1", 111) is not None
    assert store.get("s1", 222) is None  # чужое состояние недоступно


def test_state_ttl_expiry() -> None:
    from app.bot.state import DialogState, StateStore

    store = StateStore(ttl_seconds=-1)  # любой возраст > TTL — состояние протухло
    track = _track([])
    store.set("s1", DialogState(track=track, user_id=111))
    assert store.get("s1", 111) is None
    assert store.get_flag(111) is None
