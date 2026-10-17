#!/usr/bin/env bash
# Деплой musicbot на чистый Ubuntu/Debian VPS в один заход.
# Использование:  bash deploy.sh <VPS_IP> [SSH_USER]
set -euo pipefail

IP="${1:?Укажи IP сервера: bash deploy.sh 1.2.3.4 root}"
USER="${2:-root}"
ARCHIVE="musicbot-deploy.tar.gz"

if [ ! -f "$ARCHIVE" ]; then
    echo "Архив $ARCHIVE не найжен — сначала запакуй проект." >&2
    exit 1
fi

echo "==> Копирую проект на $IP..."
scp -o StrictHostKeyChecking=accept-new "$ARCHIVE" "$USER@$IP:/root/musicbot-deploy.tar.gz"

echo "==> Устанавливаю Docker и запускаю бота на сервере..."
ssh -o StrictHostKeyChecking=accept-new "$USER@$IP" 'bash -s' <<'REMOTE'
set -euo pipefail
cd /root

# Docker (официальный скрипт get.docker.com — короче и надёжнее apt-репозиториев)
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi

mkdir -p musicbot && tar xzf musicbot-deploy.tar.gz -C musicbot
cd musicbot

# Секреты: создай .env ДО этого шага или отредактируй после
if [ ! -f .env ]; then
    cp .env.example .env
    echo "!!! ЗАПОЛНИ /root/musicbot/.env (BOT_TOKEN, ADMIN_IDS) и перезапусти:"
    echo "    cd /root/musicbot && docker compose up -d --build"
    exit 0
fi

docker compose up -d --build
sleep 10
docker compose ps
docker compose logs --tail 20 bot
echo "==> Готово. Логи: docker compose logs -f bot"
REMOTE
