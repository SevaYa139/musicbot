"""Тесты распознавания источников и валидации ссылок."""

import pytest
from app.exceptions import SecurityError
from app.utils.urls import assert_url_allowed, detect_source, format_duration, is_url

VALID = [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ&t=30s", "youtube"),
    ("https://youtube.com/shorts/abc123", "youtube"),
    ("https://soundcloud.com/artist/track-name", "soundcloud"),
    ("https://on.soundcloud.com/xyz", "soundcloud"),
    ("https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC", "spotify"),
    ("https://music.yandex.ru/track/12345678", "yandex"),
    ("https://music.yandex.com/track/12345678", "yandex"),
    ("https://www.tiktok.com/@user/video/7283123456789", "tiktok"),
    ("https://vm.tiktok.com/ABC123/", "tiktok"),
    ("https://vt.tiktok.com/XYZ789", "tiktok"),
]

INVALID = [
    "hello world",
    "ftp://youtube.com/watch?v=x",
    "https://evil-youtube.com.evil.ru/watch?v=x",
    "https://example.com/video",
    "just some text",
]


@pytest.mark.parametrize(("url", "source"), VALID)
def test_detect_source_valid(url: str, source: str) -> None:
    assert is_url(url)
    assert detect_source(url) == source
    assert_url_allowed(url)  # не должно бросать


@pytest.mark.parametrize("text", INVALID)
def test_detect_source_invalid(text: str) -> None:
    assert detect_source(text) is None


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/admin",
        "http://127.0.0.1/x",
        "http://192.168.1.1/router",
        "http://10.0.0.5/a",
        "http://169.254.169.254/latest/meta-data",  # облачный metadata endpoint
        "file:///etc/passwd",
        "ftp://youtube.com/x",
        "http://youtube.com.evil.ru/x",
    ],
)
def test_ssrf_blocked(url: str) -> None:
    with pytest.raises(SecurityError):
        assert_url_allowed(url)


def test_duration_format() -> None:
    assert format_duration(205) == "3:25"
    assert format_duration(4328) == "1:12:08"
    assert format_duration(None) == "—"
    assert format_duration(-5) == "—"
