# Дисклеймер

Проект сделан для фана и полностью с помощью ИИ. Автор не несёт ответственности за стабильность работы или возможные последствия использования.

# 3X-UI ShopBot (Telegram)

Телеграм‑бот для продаж подписок из 3X‑UI с админ‑панелью. Поддерживает баланс, оплату Telegram Stars (XTR), промокоды, рефералку, рассылки и управление подписками.

## Возможности

- Покупка подписки из 3X‑UI через API
- Баланс пользователя и пополнение через Telegram Stars (XTR)
- Промокоды и скидки
- Реферальные ссылки
- Админ‑панель: тарифы, пользователи, подписки, рассылки, контент
- Ручная выдача подписок и управление ими (продлить/отключить/удалить)

## Быстрый старт (Ubuntu VPS)

1. Установить зависимости:
   ```
   sudo apt update
   sudo apt install -y python3 python3-venv python3-pip git
   ```

2. Клонировать проект:
   ```
   git clone https://github.com/Behterr/3xui-shopbot.git
   cd 3xui-shopbot
   ```

3. Установить Python зависимости:
   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

4. Настроить `.env`:
   ```
   cp .env.example .env
   nano .env
   ```

5. Запустить бота:
   ```
   python src/main.py
   ```

## Авто‑установщик (Ubuntu VPS)

Запуск одной командой:
```
bash install.sh
```

Если файл не исполняется:
```
chmod +x install.sh
./install.sh
```

Скрипт задаст вопросы (токен, домен, логин/пароль панели и т.д.), установит зависимости, создаст `.env` и настроит systemd.

## Настройка .env

Обязательные:
- `BOT_TOKEN` — токен BotFather
- `XUI_BASE_URL` — URL панели 3X‑UI (например, `https://panel.example.com:54321`)
- `XUI_USERNAME` / `XUI_PASSWORD`

Опциональные:
- `XUI_WEB_BASE_PATH` — путь панели (например, `/xui`)
- `XUI_INSECURE=true` — если самоподписанный TLS
- `SUBSCRIPTION_BASE_URL` — базовый URI подписки за прокси (например, `https://srv1.example.com/abc/`)
- `SUPPORT_USERNAME` или `SUPPORT_TG_ID` — кнопка “Поддержка”
- `BOT_USERNAME` — юзернейм бота для рефералки
- `DEFAULT_CURRENCY` — валюта (для Stars используйте `XTR`)

Админ‑панель:
- `ADMIN_WEB_USER`
- `ADMIN_WEB_PASSWORD`
- `ADMIN_WEB_SECRET`

## Тарифы

Тарифы хранятся в `config/plans.json`.
Важно: `inboundId` должен совпадать с inbound ID в 3X‑UI.

## Быстрое обновление на VPS

```
cd /opt/3xui-shopbot
git pull
sudo systemctl restart xui-bot
sudo systemctl restart xui-admin
```

## Примечания по оплате Telegram Stars

Оплата Stars использует валюту `XTR`. Цены в тарифах и баланс считаются в XTR.
