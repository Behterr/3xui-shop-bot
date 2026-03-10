#!/usr/bin/env bash
set -euo pipefail

clear

APP_DIR="/opt/3xui-shopbot"
REPO_URL="https://github.com/Behterr/3xui-shopbot.git"

echo "== Установщик 3X-UI ShopBot (Ubuntu) =="

echo "Папка установки: ${APP_DIR}"


read -r -p "Токен бота (BOT_TOKEN): " BOT_TOKEN
read -r -p "Юзернейм бота без @ (BOT_USERNAME): " BOT_USERNAME
read -r -p "URL панели 3X-UI (XUI_BASE_URL): " XUI_BASE_URL
read -r -p "Путь панели 3X-UI (XUI_WEB_BASE_PATH) [пусто если нет]: " XUI_WEB_BASE_PATH
read -r -p "Логин 3X-UI (XUI_USERNAME): " XUI_USERNAME
read -r -p "Пароль 3X-UI (XUI_PASSWORD): " XUI_PASSWORD
read -r -p "XUI_INSECURE (true/false) [false]: " XUI_INSECURE
XUI_INSECURE="${XUI_INSECURE:-false}"

read -r -p "Базовый URL подписки (SUBSCRIPTION_BASE_URL): " SUBSCRIPTION_BASE_URL
read -r -p "Юзернейм поддержки без @ (SUPPORT_USERNAME) [необязательно]: " SUPPORT_USERNAME
read -r -p "TG ID поддержки (SUPPORT_TG_ID) [необязательно]: " SUPPORT_TG_ID
read -r -p "TG ID администратора (ADMIN_TG_ID): " ADMIN_TG_ID

read -r -p "Устанавливать веб‑панель администратора? (y/N): " INSTALL_ADMIN_WEB
INSTALL_ADMIN_WEB="${INSTALL_ADMIN_WEB:-N}"
INSTALL_ADMIN_WEB="$(echo "$INSTALL_ADMIN_WEB" | tr '[:upper:]' '[:lower:]')"

if [ "$INSTALL_ADMIN_WEB" = "y" ] || [ "$INSTALL_ADMIN_WEB" = "yes" ]; then
  read -r -p "Логин веб‑админки (ADMIN_WEB_USER): " ADMIN_WEB_USER
  read -r -p "Пароль веб‑админки (ADMIN_WEB_PASSWORD): " ADMIN_WEB_PASSWORD
  read -r -p "Секрет сессий (ADMIN_WEB_SECRET): " ADMIN_WEB_SECRET
else
  ADMIN_WEB_USER=""
  ADMIN_WEB_PASSWORD=""
  ADMIN_WEB_SECRET=""
fi


echo "== Проверка системных пакетов =="
PACKAGES=(python3 python3-venv python3-pip git)
MISSING=()
for pkg in "${PACKAGES[@]}"; do
  if ! dpkg -s "$pkg" >/dev/null 2>&1; then
    MISSING+=("$pkg")
  fi
done

UPGRADABLE=()
if command -v apt >/dev/null 2>&1; then
  for pkg in "${PACKAGES[@]}"; do
    if apt list --upgradable 2>/dev/null | awk -F/ '{print $1}' | grep -qx "$pkg"; then
      UPGRADABLE+=("$pkg")
    fi
  done
fi

if [ ${#MISSING[@]} -eq 0 ] && [ ${#UPGRADABLE[@]} -eq 0 ]; then
  echo "Все необходимые пакеты уже установлены и обновлены."
else
  echo "== Установка/обновление пакетов =="
  sudo apt update
  sudo apt install -y "${PACKAGES[@]}"
fi

if [ -d "$APP_DIR/.git" ]; then
  echo "== Репозиторий уже есть, обновляю =="
  sudo git -C "$APP_DIR" pull
else
  echo "== Клонирую репозиторий =="
  sudo mkdir -p "$APP_DIR"
  sudo git clone "$REPO_URL" "$APP_DIR"
fi

echo "== Создание виртуального окружения =="
sudo python3 -m venv "$APP_DIR/.venv"
sudo "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "== Запись .env =="
sudo tee "$APP_DIR/.env" > /dev/null <<EOF
BOT_TOKEN=${BOT_TOKEN}
XUI_BASE_URL=${XUI_BASE_URL}
XUI_WEB_BASE_PATH=${XUI_WEB_BASE_PATH}
XUI_USERNAME=${XUI_USERNAME}
XUI_PASSWORD=${XUI_PASSWORD}
XUI_INSECURE=${XUI_INSECURE}
SUBSCRIPTION_BASE_URL=${SUBSCRIPTION_BASE_URL}
SUPPORT_USERNAME=${SUPPORT_USERNAME}
SUPPORT_TG_ID=${SUPPORT_TG_ID}
ADMIN_TG_ID=${ADMIN_TG_ID}
BOT_USERNAME=${BOT_USERNAME}
ADMIN_WEB_USER=${ADMIN_WEB_USER}
ADMIN_WEB_PASSWORD=${ADMIN_WEB_PASSWORD}
ADMIN_WEB_SECRET=${ADMIN_WEB_SECRET}
EOF

echo "== Создание systemd сервисов =="
sudo tee /etc/systemd/system/xui-bot.service > /dev/null <<EOF
[Unit]
Description=XUI Telegram Bot
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python ${APP_DIR}/src/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

if [ "$INSTALL_ADMIN_WEB" = "y" ] || [ "$INSTALL_ADMIN_WEB" = "yes" ]; then
sudo tee /etc/systemd/system/xui-admin.service > /dev/null <<EOF
[Unit]
Description=XUI Admin Panel
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/python -m uvicorn src.admin_web:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
fi

echo "== Включение сервисов =="
sudo systemctl daemon-reload
if [ "$INSTALL_ADMIN_WEB" = "y" ] || [ "$INSTALL_ADMIN_WEB" = "yes" ]; then
  sudo systemctl enable xui-bot xui-admin
  sudo systemctl restart xui-bot xui-admin
else
  sudo systemctl enable xui-bot
  sudo systemctl restart xui-bot
fi

echo "== Готово =="
echo "Бот:    sudo systemctl status xui-bot"
if [ "$INSTALL_ADMIN_WEB" = "y" ] || [ "$INSTALL_ADMIN_WEB" = "yes" ]; then
  echo "Админ:  sudo systemctl status xui-admin"
fi
echo "Logs:   sudo journalctl -u xui-bot -f"
