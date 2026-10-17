"""Тесты TikTok-провайдера (tikwm API, без сети — моки)."""

from pathlib import Path

from app.providers.tiktok import TikTokProvider, _ext_of, _save_name

_FAKE = {
    "title": "Test video / тест",
    "author": {"nickname": "author_name"},
    "duration": 15,
    "cover": "https://example.com/cover.jpg",
    "play": "https://example.com/play.mp4",
    "hdplay": "https://example.com/hd.mp4",
    "music": "https://example.com/music.mp3",
}


def test_build_options_from_tikwm() -> None:
    p = TikTokProvider()
    p._tikwm_api = lambda url: dict(_FAKE)  # type: ignore[method-assign]
    track = p._via_tikwm("https://www.tiktok.com/@a/video/1")
    assert track.source == "tiktok"
    assert track.artist == "author_name"
    assert track.duration == 15
    kinds = {(o.kind, o.option_id) for o in track.options}
    assert ("video", "vsd") in kinds and ("video", "vhd") in kinds
    assert ("audio", "orig") in kinds
    assert "tikwm" in track.extra


def test_build_options_without_hd_and_music() -> None:
    p = TikTokProvider()
    data = {k: v for k, v in _FAKE.items() if k not in ("hdplay", "music")}
    p._tikwm_api = lambda url: data  # type: ignore[method-assign]
    track = p._via_tikwm("https://vm.tiktok.com/x/")
    ids = [o.option_id for o in track.options]
    assert "vhd" not in ids and "orig" not in ids and "vsd" in ids


def test_ext_and_filename() -> None:
    assert _ext_of("https://a/b/file.mp4?x=1", "mp4") == "mp4"
    assert _ext_of("https://a/b/noext", "mp3") == "mp3"
    assert _save_name('Bad / name: * ? " <>', "mp4").endswith(".mp4")
    assert "/" not in _save_name("a/b", "mp4")


def test_download_tikwm_writes_file(tmp_path: Path) -> None:
    """Скачивание подменяется локальным файлом — проверяем выбор URL и MIME."""
    import base64

    from app.providers.base import MediaOption, TrackInfo

    p = TikTokProvider()
    media_b64 = base64.b64encode(b"fake-media").decode()
    cover_b64 = base64.b64encode(b"fake-cover").decode()

    def fake_fetch(url: str, dest: Path, cb: object) -> None:
        import base64 as b64

        dest.write_bytes(b64.b64decode(media_b64 if "play" in url else cover_b64))

    p._fetch_file = fake_fetch  # type: ignore[method-assign]
    info = TrackInfo(
        source="tiktok",
        url="https://www.tiktok.com/@a/video/1",
        title="Track",
        artist="A",
        options=[],
        extra={"tikwm": _FAKE},
    )
    result = p._download_tikwm(
        info,
        MediaOption(kind="audio", label="M", option_id="orig", ext="mp3"),
        tmp_path,
        _FAKE,
        None,
    )
    assert result.mime_hint == "audio/mpeg"
    assert result.file_path.suffix == ".mp3"
    assert result.cover_path is not None
