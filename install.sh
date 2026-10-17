#!/usr/bin/env bash
# Установка musicbot на чистый VPS (Ubuntu/Debian) прямо из GitHub.
#
# Использование:
#   curl -fsSL https://raw.githubusercontent.com/sevaya-sudo/musicbot/main/install.sh | bash -s -- <BOT_TOKEN> [ADMIN_IDS]
# или интерактивно:
#   bash install.sh
#
# Секреты (токен, id админов) никогда не хранятся в репозитории —
# скрипт получает их только как аргументы/ввод и пишет в .env на сервере.
set -euo pipefail

REPO="https://github.com/sevaya-sudo/musicbot.git"
DIR="/root/musicbot"

BOT_TOKEN="${1:-}"
ADMIN_IDS="${2:-}"

if [ -z "$BOT_TOKEN" ]; then
    read -r -p "Введи токен бота (от @BotFather): " BOT_TOKEN
fi
if [ -z "$ADMIN_IDS" ]; then
    read -r -p "Введи свой Telegram ID (через @userinfobot; можно через запятую): " ADMIN_IDS
fi
if [ -z "$BOT_TOKEN" ]; then
    echo "Токен обязателен." >&2
    exit 1
fi

echo "==> Устанавливаю Docker..."
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
fi

echo "==> Клонирую репозиторий в $DIR..."
if [ -d "$DIR/.git" ]; then
    git -C "$DIR" pull --ff-only
else
    rm -rf "$DIR"
    git clone "$REPO" "$DIR"
fi
cd "$DIR"

echo "==> Подготавливаю .env (секреты только локально на сервере)..."
if [ ! -f .env ]; then
    cp .env.example .env
fi
# Обновляем/добавляем ключи, не трогая остальное
set_kv() {
    local key="$1" val="$2"
    if grep -q "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${val}|" .env
    else
        echo "${key}=${val}" >> .env
    fi
}
set_kv "BOT_TOKEN" "$BOT_TOKEN"
set_kv "ADMIN_IDS" "$ADMIN_IDS"
chmod 600 .env

echo "==> Собираю и запускаю контейнеры..."
docker compose up -d --build

echo "==> Готово. Статус:"
docker compose ps
echo
echo "Логи:   cd $DIR && docker compose logs -f bot"
echo "Первая команда боту в Telegram: /start"
