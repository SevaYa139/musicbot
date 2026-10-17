"""Безопасная работа со ссылками: распознавание источника, SSRF-защита."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from app.exceptions import SecurityError

# Домены, с которыми бот вообще работает. Прямые скачивания по произвольным URL запрещены.
ALLOWED_HOSTS: frozenset[str] = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
        "soundcloud.com",
        "on.soundcloud.com",
        "spotify.com",
        "open.spotify.com",
        "music.yandex.ru",
        "music.yandex.com",
        "tiktok.com",
        "www.tiktok.com",
        "m.tiktok.com",
        "vm.tiktok.com",
        "vt.tiktok.com",
    }
)

_YOUTUBE_HOSTS = {"youtube.com", "youtu.be", "music.youtube.com"}
_SOUNDCLOUD_HOSTS = {"soundcloud.com"}
_SPOTIFY_HOSTS = {"spotify.com"}
_YANDEX_HOSTS = {"music.yandex.ru", "music.yandex.com"}
_TIKTOK_HOSTS = {"tiktok.com", "vm.tiktok.com", "vt.tiktok.com", "m.tiktok.com"}


def is_url(text: str) -> bool:
    """Похоже ли текст на http(s)-ссылку."""
    text = text.strip()
    if not text.startswith(("http://", "https://")):
        return False
    parsed = urlparse(text)
    return bool(parsed.netloc) and "." in parsed.netloc


def host_of(url: str) -> str:
    return (urlparse(url.strip()).hostname or "").lower()


def detect_source(url: str) -> str | None:
    """Определяет источник по домену ссылки.

    Возвращает одно из: youtube, soundcloud, spotify, yandex — или None.
    """
    if not is_url(url):
        return None
    host = host_of(url)
    if any(host == h or host.endswith("." + h) for h in _YOUTUBE_HOSTS):
        return "youtube"
    if any(host == h or host.endswith("." + h) for h in _SOUNDCLOUD_HOSTS):
        return "soundcloud"
    if any(host == h or host.endswith("." + h) for h in _SPOTIFY_HOSTS):
        return "spotify"
    if host in _YANDEX_HOSTS:
        return "yandex"
    if any(host == h or host.endswith("." + h) for h in _TIKTOK_HOSTS):
        return "tiktok"
    return None


def assert_url_allowed(url: str) -> str:
    """Проверяет, что ссылка ведёт на разрешённый публичный хост.

    Блокирует localhost, приватные/зарезервированные IP, схемы без http(s)
    и любые домены вне белого списка. Используется для всех URL,
    которые бот собирается обрабатывать или скачивать.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise SecurityError("Поддерживаются только http(s)-ссылки.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SecurityError("В ссылке отсутствует домен.")
    # Прямой IP-адрес: запрещаем локальные/приватные сети (SSRF)
    try:
        ip = ipaddress.ip_address(host)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise SecurityError("Доступ к локальным и приватным адресам запрещён.")
    except ValueError:
        pass  # не IP — ок
    if host in {"localhost", "0.0.0.0", "::1"} or host.endswith(".local"):  # noqa: S104
        raise SecurityError("Доступ к локальным адресам запрещён.")
    if host not in ALLOWED_HOSTS and not any(
        host.endswith("." + h) for h in ALLOWED_HOSTS
    ):
        raise SecurityError("Этот домен не поддерживается ботом.")
    return url.strip()


def format_duration(seconds: int | float | None) -> str:
    """Человекочитаемая длительность: 3:25, 1:12:08."""
    if seconds is None or seconds < 0:
        return "—"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
