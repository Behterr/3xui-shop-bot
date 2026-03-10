#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/opt/3xui-shopbot"
REPO_URL="https://github.com/Behterr/3xui-shopbot.git"

echo "== 3X-UI ShopBot installer (Ubuntu) =="

read -r -p "Install directory [/opt/3xui-shopbot]: " input_dir
APP_DIR="${input_dir:-$APP_DIR}"

read -r -p "Git repo URL [${REPO_URL}]: " input_repo
REPO_URL="${input_repo:-$REPO_URL}"

read -r -p "Bot token (BOT_TOKEN): " BOT_TOKEN
read -r -p "Bot username without @ (BOT_USERNAME): " BOT_USERNAME
read -r -p "3X-UI base URL (XUI_BASE_URL): " XUI_BASE_URL
read -r -p "3X-UI web base path (XUI_WEB_BASE_PATH) [empty if none]: " XUI_WEB_BASE_PATH
read -r -p "3X-UI username (XUI_USERNAME): " XUI_USERNAME
read -r -p "3X-UI password (XUI_PASSWORD): " XUI_PASSWORD
read -r -p "XUI_INSECURE (true/false) [false]: " XUI_INSECURE
XUI_INSECURE="${XUI_INSECURE:-false}"

read -r -p "Subscription base URL (SUBSCRIPTION_BASE_URL): " SUBSCRIPTION_BASE_URL
read -r -p "Support username without @ (SUPPORT_USERNAME) [optional]: " SUPPORT_USERNAME
read -r -p "Support TG ID (SUPPORT_TG_ID) [optional]: " SUPPORT_TG_ID

read -r -p "Install admin web panel? (y/N): " INSTALL_ADMIN_WEB
INSTALL_ADMIN_WEB="${INSTALL_ADMIN_WEB:-N}"
INSTALL_ADMIN_WEB="$(echo "$INSTALL_ADMIN_WEB" | tr '[:upper:]' '[:lower:]')"

if [ "$INSTALL_ADMIN_WEB" = "y" ] || [ "$INSTALL_ADMIN_WEB" = "yes" ]; then
  read -r -p "Admin web login (ADMIN_WEB_USER): " ADMIN_WEB_USER
  read -r -p "Admin web password (ADMIN_WEB_PASSWORD): " ADMIN_WEB_PASSWORD
  read -r -p "Admin web session secret (ADMIN_WEB_SECRET): " ADMIN_WEB_SECRET
else
  ADMIN_WEB_USER=""
  ADMIN_WEB_PASSWORD=""
  ADMIN_WEB_SECRET=""
fi

read -r -p "Default currency (DEFAULT_CURRENCY) [XTR]: " DEFAULT_CURRENCY
DEFAULT_CURRENCY="${DEFAULT_CURRENCY:-XTR}"

echo "== Installing system packages =="
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

if [ -d "$APP_DIR/.git" ]; then
  echo "== Repo exists, pulling latest =="
  sudo git -C "$APP_DIR" pull
else
  echo "== Cloning repo =="
  sudo mkdir -p "$APP_DIR"
  sudo git clone "$REPO_URL" "$APP_DIR"
fi

echo "== Setting up virtualenv =="
sudo python3 -m venv "$APP_DIR/.venv"
sudo "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "== Writing .env =="
sudo tee "$APP_DIR/.env" > /dev/null <<EOF
BOT_TOKEN=${BOT_TOKEN}
XUI_BASE_URL=${XUI_BASE_URL}
XUI_WEB_BASE_PATH=${XUI_WEB_BASE_PATH}
XUI_USERNAME=${XUI_USERNAME}
XUI_PASSWORD=${XUI_PASSWORD}
XUI_INSECURE=${XUI_INSECURE}
DEFAULT_CURRENCY=${DEFAULT_CURRENCY}
SUBSCRIPTION_BASE_URL=${SUBSCRIPTION_BASE_URL}
SUPPORT_USERNAME=${SUPPORT_USERNAME}
SUPPORT_TG_ID=${SUPPORT_TG_ID}
ADMIN_TG_ID=
BOT_USERNAME=${BOT_USERNAME}
ADMIN_WEB_USER=${ADMIN_WEB_USER}
ADMIN_WEB_PASSWORD=${ADMIN_WEB_PASSWORD}
ADMIN_WEB_SECRET=${ADMIN_WEB_SECRET}
EOF

echo "== Creating systemd services =="
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

echo "== Enabling services =="
sudo systemctl daemon-reload
if [ "$INSTALL_ADMIN_WEB" = "y" ] || [ "$INSTALL_ADMIN_WEB" = "yes" ]; then
  sudo systemctl enable xui-bot xui-admin
  sudo systemctl restart xui-bot xui-admin
else
  sudo systemctl enable xui-bot
  sudo systemctl restart xui-bot
fi

echo "== Done =="
echo "Bot:    sudo systemctl status xui-bot"
if [ "$INSTALL_ADMIN_WEB" = "y" ] || [ "$INSTALL_ADMIN_WEB" = "yes" ]; then
  echo "Admin:  sudo systemctl status xui-admin"
fi
echo "Logs:   sudo journalctl -u xui-bot -f"
