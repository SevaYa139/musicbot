# syntax=docker/dockerfile:1
# Многоэтапная сборка: builder с компиляцией, runtime — минимальный.

FROM python:3.12-slim AS builder
WORKDIR /build
ENV PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --prefix=/install . && \
    pip install --prefix=/install pytest pytest-asyncio ruff mypy

FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/install/bin:$PATH \
    PYTHONPATH=/install/lib/python3.12/site-packages:/app

# FFmpeg для конвертации и объединения дорожек; curl для healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd -r musicbot && useradd -r -g musicbot musicbot

WORKDIR /app
COPY --from=builder /install /install
COPY app ./app
COPY assets ./assets
COPY pyproject.toml ./

RUN mkdir -p /tmp/musicbot && chown -R musicbot:musicbot /tmp/musicbot /app
USER musicbot

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -sf "https://api.telegram.org/bot${BOT_TOKEN}/getMe" > /dev/null || exit 1

CMD ["python", "-m", "app.main"]
