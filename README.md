# Save — Telegram-бот для скачивания музыки и видео

Бот: принимает ссылку (YouTube / Shorts, SoundCloud, Spotify, Яндекс Музыка, TikTok)
или название трека → показывает карточку → выбор формата → готовый файл.

Стек: aiogram 3, yt-dlp, SQLAlchemy async (Postgres), очередь заданий, Redis (опционально),
кастомные эмодзи-иконки пакета [tgiosicons](https://t.me/addemoji/tgiosicons),
инлайн-режим (`@SaveStati_bot запрос` в любом чате).

## Установка на VPS (Ubuntu/Debian)

```bash
curl -fsSL https://raw.githubusercontent.com/sevaya-sudo/musicbot/main/install.sh | bash -s -- <BOT_TOKEN> [ADMIN_IDS]
```

Скрипт установит Docker, склонирует репозиторий, создаст `.env` с твоими
секретами (только на сервере, в git они не попадают) и запустит контейнеры.

Обновление на сервере:

```bash
cd /root/musicbot && git pull --ff-only && docker compose up -d --build
```

## Запуск для разработки

```bash
python -m venv .venv && pip install -e ".[dev]"
cp .env.example .env   # заполни BOT_TOKEN и ADMIN_IDS
pytest                 # 55 тестов
ruff check app tests
mypy app
python -m app.main
```

## Структура

- `app/bot` — handlers, клавиатуры, тексты, middlewares, инлайн-режим
- `app/providers` — адаптеры источников (yt-dlp база + Spotify/Yandex API + TikTok через tikwm)
- `app/jobqueue` — очередь заданий (memory + Redis-обёртка)
- `app/services` — скачивание, конвертация FFmpeg, поиск
- `app/worker.py` — воркер тяжёлых заданий вне polling-цикла

## Безопасность

- Секреты только в `.env` (в репозитории его нет, `.gitignore` покрывает)
- SSRF-защита: белый список доменов, блокировка приватных IP
- Внешние процессы вызываются только списком аргументов, без shell
