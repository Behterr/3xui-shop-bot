import json
import os
import secrets
import uuid
import re
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, LabeledPrice
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    ContextTypes,
    filters,
)

from db import (
    init_db,
    upsert_user,
    create_order,
    create_subscription,
    get_user_subscriptions,
    get_user_by_tg_id,
    set_last_message_id,
    get_balance,
    set_balance,
    add_balance,
    set_ref_code,
    set_referrer,
    set_state,
    clear_state,
    set_active_promo,
    clear_active_promo,
    create_transaction,
    update_transaction_status,
    update_transaction_by_payload,
    get_promo_code,
    has_redeemed_promo,
    redeem_promo,
    get_config,
)
from three_xui import ThreeXuiClient

load_dotenv()

BOT_TOKEN = os.environ.get("BOT_TOKEN")
XUI_BASE_URL = os.environ.get("XUI_BASE_URL")
XUI_USERNAME = os.environ.get("XUI_USERNAME")
XUI_PASSWORD = os.environ.get("XUI_PASSWORD")
XUI_WEB_BASE_PATH = os.environ.get("XUI_WEB_BASE_PATH")
XUI_INSECURE = os.environ.get("XUI_INSECURE", "false").lower() == "true"
DEFAULT_CURRENCY = os.environ.get("DEFAULT_CURRENCY", "RUB")
SUBSCRIPTION_BASE_URL = os.environ.get("SUBSCRIPTION_BASE_URL", "").strip()
ADMIN_TG_ID = os.environ.get("ADMIN_TG_ID")
SUPPORT_USERNAME = os.environ.get("SUPPORT_USERNAME", "").strip().lstrip("@")
SUPPORT_TG_ID = os.environ.get("SUPPORT_TG_ID", "").strip()
BOT_USERNAME = os.environ.get("BOT_USERNAME", "").strip().lstrip("@")

TOPUP_AMOUNTS = [100, 300, 500]

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is required")
if not XUI_BASE_URL or not XUI_USERNAME or not XUI_PASSWORD:
    raise RuntimeError("XUI_BASE_URL, XUI_USERNAME, XUI_PASSWORD are required")

with open("config/plans.json", "r", encoding="utf-8") as f:
    PLANS = json.load(f)

DB = init_db()

XUI = ThreeXuiClient(
    base_url=XUI_BASE_URL,
    web_base_path=XUI_WEB_BASE_PATH,
    username=XUI_USERNAME,
    password=XUI_PASSWORD,
    insecure=XUI_INSECURE,
)


def _format_plan(plan):
    price_line = f"{plan.get('price')} {plan.get('currency', DEFAULT_CURRENCY)}"
    period_line = f"{plan.get('expiryDays')} дней" if plan.get("expiryDays") else ""
    parts = [plan.get("title"), price_line, period_line]
    return " | ".join([p for p in parts if p])


def _main_menu():
    buttons = [
        [InlineKeyboardButton("Купить подписку", callback_data="menu:plans")],
        [
            InlineKeyboardButton("Мои подписки", callback_data="menu:subs"),
            InlineKeyboardButton("Баланс", callback_data="menu:balance"),
        ],
        [
            InlineKeyboardButton("Промокод", callback_data="menu:promo"),
            InlineKeyboardButton("Рефералка", callback_data="menu:ref"),
        ],
    ]
    support_url = None
    if SUPPORT_USERNAME:
        support_url = f"https://t.me/{SUPPORT_USERNAME}"
    elif SUPPORT_TG_ID:
        support_url = f"tg://user?id={SUPPORT_TG_ID}"
    if support_url:
        buttons.append([InlineKeyboardButton("Поддержка", url=support_url)])
    return InlineKeyboardMarkup(buttons)


def _plans_menu():
    buttons = [
        [InlineKeyboardButton(_format_plan(plan), callback_data=f"buy:{plan['id']}")]
        for plan in PLANS
    ]
    buttons.append([InlineKeyboardButton("Назад", callback_data="menu:back")])
    return InlineKeyboardMarkup(buttons)

def _back_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="menu:back")]])


def _build_sub_url(base_url, sub_id):
    if not base_url:
        return None
    base = base_url if base_url.endswith("/") else f"{base_url}/"
    return f"{base}{sub_id}"


def _format_price(value):
    return f"{value} {DEFAULT_CURRENCY}"


def _calc_discounted_price(price, promo):
    if not promo:
        return price, None
    discount_percent = promo.get("discount_percent") or 0
    discount_amount = promo.get("discount_amount") or 0
    discounted = price - int(price * discount_percent / 100) - discount_amount
    if discounted < 0:
        discounted = 0
    return discounted, promo


async def _show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, user=None):
    if user is None:
        user = _ensure_user(update)
    subs = get_user_subscriptions(DB, user[0])
    panel_emails, panel_ids = _load_panel_clients()
    active_count = len(
        [s for s in subs if (s[4] in panel_emails) or (s[5] in panel_ids)]
    )
    balance = user[6] if user[6] is not None else 0
    banner = get_config(DB, "menu_banner_text", "")
    header = get_config(DB, "menu_header_text", "Главное меню")
    text = (
        f"{header}\n"
        f"ID: {update.effective_user.id}\n"
        f"Баланс: {_format_price(balance)}\n"
        f"Подписок: {active_count}"
    )
    if banner:
        text = f"{banner}\n\n{text}"
    await _send_or_edit(update, context, text, reply_markup=_main_menu())


def _ensure_user(update: Update):
    user = upsert_user(DB, update.effective_user)
    if user[7] is None:
        ref_code = secrets.token_hex(4)
        set_ref_code(DB, user[0], ref_code)
        user = get_user_by_tg_id(DB, update.effective_user.id)
    return user


async def _send_or_edit(update: Update, context: ContextTypes.DEFAULT_TYPE, text, reply_markup=None):
    if update.callback_query and update.callback_query.message:
        msg = await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
        )
        user = get_user_by_tg_id(DB, update.effective_user.id)
        if user and msg:
            set_last_message_id(DB, user[0], msg.message_id)
        return

    user = _ensure_user(update)
    last_message_id = user[5] if len(user) > 5 else None
    if last_message_id:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=last_message_id,
            )
        except Exception:
            pass

    msg = await update.effective_message.reply_text(text, reply_markup=reply_markup)
    set_last_message_id(DB, user[0], msg.message_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_user(update)
    if context.args:
        ref = context.args[0]
        if ref.startswith("ref_"):
            ref_code = ref.replace("ref_", "", 1)
            if ref_code and ref_code != user[7]:
                cur = DB.execute("SELECT id FROM users WHERE ref_code = ?", (ref_code,))
                row = cur.fetchone()
                if row and row[0] != user[0]:
                    set_referrer(DB, user[0], row[0])

    await _show_main_menu(update, context, user)


async def plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ensure_user(update)
    await _send_or_edit(
        update,
        context,
        "Доступные тарифы:",
        reply_markup=_plans_menu(),
    )


def _parse_clients(settings_text):
    try:
        settings = json.loads(settings_text or "{}")
    except Exception:
        return []
    return settings.get("clients", []) or []


def _load_panel_clients():
    inbound_ids = sorted({int(p["inboundId"]) for p in PLANS if p.get("inboundId") is not None})
    email_set = set()
    id_set = set()
    for inbound_id in inbound_ids:
        try:
            resp = XUI.get_inbound(inbound_id)
            payload = resp.json() if resp.content else {}
            if not payload.get("success") or not payload.get("obj"):
                continue
            clients = _parse_clients(payload["obj"].get("settings"))
            for client in clients:
                if client.get("email"):
                    email_set.add(client["email"])
                if client.get("id"):
                    id_set.add(client["id"])
        except Exception:
            continue
    return email_set, id_set


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_user(update)
    subs = get_user_subscriptions(DB, user[0])
    panel_emails, panel_ids = _load_panel_clients()
    subs = [
        sub
        for sub in subs
        if (sub[4] in panel_emails) or (sub[5] in panel_ids)
    ]

    if not subs:
        await _send_or_edit(
            update,
            context,
            "У вас пока нет подписок в панели.",
            reply_markup=_back_menu(),
        )
        return

    lines = []
    for sub in subs:
        expires_dt = datetime.fromisoformat(sub[6])
        expires = expires_dt.strftime("%d.%m.%Y")
        lines.append(f"{sub[2]} | до: {expires} | email: {sub[4]}")

    await _send_or_edit(
        update,
        context,
        "\n".join(lines),
        reply_markup=_back_menu(),
    )


async def my_subscriptions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await status(update, context)


async def show_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_user(update)
    balance = get_balance(DB, user[0])
    buttons = [
        [InlineKeyboardButton(f"Пополнить {amt} XTR", callback_data=f"topup:{amt}")]
        for amt in TOPUP_AMOUNTS
    ]
    buttons.append([InlineKeyboardButton("Назад", callback_data="menu:back")])
    text = f"Баланс: {_format_price(balance)}\nПополнение через Telegram Stars."
    await _send_or_edit(update, context, text, reply_markup=InlineKeyboardMarkup(buttons))


async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_user(update)
    ref_code = user[7]
    bot_username = BOT_USERNAME or (context.bot.username if context and context.bot else "")
    link = f"https://t.me/{bot_username}?start=ref_{ref_code}" if bot_username else f"ref_{ref_code}"
    text = f"Реферальная ссылка:\n{link}"
    await _send_or_edit(update, context, text, reply_markup=_back_menu())


async def ask_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_user(update)
    set_state(DB, user[0], "awaiting_promo")
    await _send_or_edit(
        update,
        context,
        "Введите промокод одним сообщением.",
        reply_markup=_back_menu(),
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_user(update)
    state = user[9] if len(user) > 9 else None
    if state != "awaiting_promo":
        return
    code = (update.message.text or "").strip().upper()
    clear_state(DB, user[0])
    if not re.match(r"^[A-Z0-9_\\-]{3,32}$", code):
        await _send_or_edit(update, context, "Некорректный промокод.", reply_markup=_back_menu())
        return
    promo_row = get_promo_code(DB, code)
    if not promo_row:
        await _send_or_edit(update, context, "Промокод не найден.", reply_markup=_back_menu())
        return
    promo = {
        "code": promo_row[0],
        "discount_percent": promo_row[1],
        "discount_amount": promo_row[2],
        "usage_limit": promo_row[3],
        "used_count": promo_row[4],
        "expires_at": promo_row[5],
        "active": promo_row[6],
    }
    if promo["active"] != 1:
        await _send_or_edit(update, context, "Промокод неактивен.", reply_markup=_back_menu())
        return
    if promo["usage_limit"] and promo["used_count"] >= promo["usage_limit"]:
        await _send_or_edit(update, context, "Лимит промокода исчерпан.", reply_markup=_back_menu())
        return
    if promo["expires_at"]:
        try:
            expires = datetime.fromisoformat(promo["expires_at"])
            if datetime.utcnow() > expires:
                await _send_or_edit(update, context, "Промокод истек.", reply_markup=_back_menu())
                return
        except Exception:
            pass
    if has_redeemed_promo(DB, user[0], code):
        await _send_or_edit(update, context, "Промокод уже использован.", reply_markup=_back_menu())
        return
    set_active_promo(DB, user[0], code)
    await _send_or_edit(update, context, f"Промокод применен: {code}", reply_markup=_back_menu())


async def precheckout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.pre_checkout_query.answer(ok=True)


async def successful_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = _ensure_user(update)
    payment = update.message.successful_payment
    amount = payment.total_amount
    currency = payment.currency
    add_balance(DB, user[0], amount)
    update_transaction_by_payload(DB, payment.invoice_payload, "paid", json.dumps(payment.to_dict()))
    await _send_or_edit(
        update,
        context,
        f"Платеж успешен. Баланс пополнен на {amount} {currency}.",
        reply_markup=_back_menu(),
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data.startswith("menu:") and data != "menu:promo":
        user = _ensure_user(update)
        clear_state(DB, user[0])
    if data == "menu:plans":
        await _send_or_edit(update, context, "Доступные тарифы:", reply_markup=_plans_menu())
        return
    if data == "menu:subs":
        await _send_or_edit(update, context, "Ваши подписки:", reply_markup=_back_menu())
        await status(update, context)
        return
    if data == "menu:balance":
        await show_balance(update, context)
        return
    if data == "menu:promo":
        await ask_promo(update, context)
        return
    if data == "menu:ref":
        await show_referral(update, context)
        return
    if data == "menu:back":
        user = _ensure_user(update)
        clear_state(DB, user[0])
        await _show_main_menu(update, context, user)
        return

    if data.startswith("topup:"):
        amount = int(data.split(":", 1)[1])
        user = _ensure_user(update)
        payload = f"topup:{user[0]}:{amount}:{int(datetime.now(tz=timezone.utc).timestamp())}"
        create_transaction(DB, user[0], amount, "XTR", "pending", "stars", payload)
        await context.bot.send_invoice(
            chat_id=update.effective_chat.id,
            title="Пополнение баланса",
            description=f"Пополнение на {amount} XTR",
            payload=payload,
            currency="XTR",
            prices=[LabeledPrice("Баланс", amount)],
            provider_token=None,
        )
        return

    if not data.startswith("buy:"):
        return

    plan_id = data.split(":", 1)[1]
    plan = next((p for p in PLANS if p["id"] == plan_id), None)
    if not plan:
        await _send_or_edit(update, context, "Тариф не найден", reply_markup=_plans_menu())
        return

    user = _ensure_user(update)
    price = plan.get("price") or 0
    promo = None
    active_promo = user[11] if len(user) > 11 else None
    if active_promo:
        promo_row = get_promo_code(DB, active_promo)
        if promo_row:
            promo = {
                "code": promo_row[0],
                "discount_percent": promo_row[1],
                "discount_amount": promo_row[2],
                "usage_limit": promo_row[3],
                "used_count": promo_row[4],
                "expires_at": promo_row[5],
                "active": promo_row[6],
            }
    final_price, promo = _calc_discounted_price(price, promo)
    balance = get_balance(DB, user[0])
    if final_price > 0 and balance < final_price:
        await _send_or_edit(
            update,
            context,
            f"Недостаточно средств. Баланс: {balance}, нужно: {final_price}.",
            reply_markup=_back_menu(),
        )
        return

    await _send_or_edit(update, context, "Создаю подписку...")

    client_uuid = str(uuid.uuid4())
    client_email = f"{user[1]}_{int(datetime.now(tz=timezone.utc).timestamp())}@tg"

    expiry_days = plan.get("expiryDays") or 365
    expires_at = datetime.now(tz=timezone.utc) + timedelta(days=expiry_days)

    sub_id = secrets.token_hex(8)
    client = {
        "id": client_uuid,
        "email": client_email,
        "enable": True,
        "flow": plan.get("flow", ""),
        "totalGB": plan.get("totalGB", 0),
        "expiryTime": int(expires_at.timestamp() * 1000),
        "limitIp": plan.get("limitIp", 0),
        "subId": sub_id,
    }

    try:
        response = XUI.add_client(plan["inboundId"], client)
    except Exception as exc:
        create_order(
            DB,
            user[0],
            plan_id,
            "xui_error",
            json.dumps({"message": str(exc)}),
        )
        await _send_or_edit(update, context, "Не удалось создать подписку в панели.")
        return

    payload = response.json() if response.content else {}
    success = payload.get("success") is True or payload.get("obj") is not None

    create_order(
        DB,
        user[0],
        plan_id,
        "created" if success else "xui_failed",
        json.dumps(payload),
    )

    if not success:
        await _send_or_edit(
            update,
            context,
            "Панель отклонила запрос. Пожалуйста, обратитесь в поддержку."
        )
        if ADMIN_TG_ID:
            await context.bot.send_message(
                int(ADMIN_TG_ID),
                f"3X-UI error for user {user[1]}: {payload}",
            )
        return

    create_subscription(
        DB,
        user[0],
        plan_id,
        plan["inboundId"],
        client_email,
        client_uuid,
        expires_at.isoformat(),
        json.dumps(payload),
    )
    if final_price > 0:
        set_balance(DB, user[0], balance - final_price)
    if promo:
        redeem_promo(DB, user[0], promo["code"])
        clear_active_promo(DB, user[0])

    sub_url = _build_sub_url(SUBSCRIPTION_BASE_URL, sub_id)

    message_lines = [
        "Подписка создана.",
        f"Тариф: {_format_plan(plan)}",
        f"Действует до: {expires_at.strftime('%d.%m.%Y')}",
        f"Email клиента: {client_email}",
    ]
    if promo:
        message_lines.append(f"Промокод применен: {promo['code']}")
    if sub_url:
        message_lines.append(f"Ссылка на подписку: {sub_url}")
    else:
        message_lines.append(
            "Ссылка на подписку не настроена. Обратитесь в поддержку."
        )

    await _send_or_edit(update, context, "\n".join(message_lines), reply_markup=_back_menu())


def main():
    import asyncio

    asyncio.set_event_loop(asyncio.new_event_loop())
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("plans", plans))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("mysubscriptions", my_subscriptions))
    app.add_handler(CommandHandler("menu", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(PreCheckoutQueryHandler(precheckout_handler))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
