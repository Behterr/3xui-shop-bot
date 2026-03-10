# 3X-UI Telegram Bot (Python MVP)

Этот бот продает подписки: создает клиентов в вашей 3X-UI панели через API и сохраняет все действия в SQLite.

## Установка

1. Создайте виртуальное окружение и установите зависимости:
   python -m venv .venv
   .\.venv\Scripts\activate
   pip install -r requirements.txt

2. Скопируйте `.env.example` в `.env` и заполните значения:
   - `BOT_TOKEN` из BotFather
   - `XUI_BASE_URL` например `https://panel.example.com:54321`
   - `XUI_WEB_BASE_PATH`, если панель на нестандартном пути (например, `/xui`)
   - `XUI_USERNAME` / `XUI_PASSWORD`
   - `XUI_INSECURE=true`, если используется самоподписанный TLS
   - `SUBSCRIPTION_BASE_URL` базовый URI подписки (например, `https://srv1.palachsrv.mooo.com/m8eYzJF/`)
   - `SUPPORT_USERNAME` (например, `my_support`) или `SUPPORT_TG_ID` для кнопки “Поддержка”
   - `BOT_USERNAME` для реферальной ссылки (без @)

3. Отредактируйте тарифы в `config/plans.json`.
   - `inboundId` должен совпадать с вашим inbound ID в 3X-UI.
   - `subscriptionUrlTemplate` опционален и может использовать `{email}` или `{uuid}`.

4. Запуск бота:
   python src/main.py

## Админ‑панель (локально)

1. Установите зависимости:
   pip install -r requirements.txt

2. В `.env` добавьте:
   - `ADMIN_WEB_USER` (логин)
   - `ADMIN_WEB_PASSWORD` (пароль)
   - `ADMIN_WEB_SECRET` (любая строка для сессий)

3. Запуск админки:
   python -m uvicorn src.admin_web:app --host 127.0.0.1 --port 8000

Откройте http://127.0.0.1:8000 и войдите в панель.

## Хранение данных

SQLite база хранится в `data/bot.db`.
Таблицы: users, orders, subscriptions.

## Команды

- `/start` или `/plans` — показать тарифы
- `/status` — показать ваши подписки

## Примечания

Бот создает клиента в 3X-UI и отправляет детали подписки. Для пополнения баланса используется Telegram Stars (XTR).

## Оплата Telegram Stars

Для пополнения баланса используются Telegram Stars (валюта `XTR`). Задайте цены тарифов в XTR.
