import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from src.admin_db import (
    get_counts,
    list_orders,
    list_subscriptions,
    list_users,
    update_balance,
    list_promos,
    add_promo,
    delete_promo,
    list_users_for_broadcast,
    get_subscription,
    list_broadcasts,
)
from src.admin_store import load_env_file, load_plans, save_plans, update_env_file
from src.db import create_subscription, create_order, set_config, get_all_config, create_broadcast
from src.three_xui import ThreeXuiClient

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(APP_DIR / "templates"))

ADMIN_WEB_USER = os.environ.get("ADMIN_WEB_USER", "admin")
ADMIN_WEB_PASSWORD = os.environ.get("ADMIN_WEB_PASSWORD", "admin")
ADMIN_WEB_SECRET = os.environ.get("ADMIN_WEB_SECRET", "change-me")

XUI_BASE_URL = os.environ.get("XUI_BASE_URL")
XUI_USERNAME = os.environ.get("XUI_USERNAME")
XUI_PASSWORD = os.environ.get("XUI_PASSWORD")
XUI_WEB_BASE_PATH = os.environ.get("XUI_WEB_BASE_PATH")
XUI_INSECURE = os.environ.get("XUI_INSECURE", "false").lower() == "true"
BOT_TOKEN = os.environ.get("BOT_TOKEN")

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=ADMIN_WEB_SECRET)


def _db():
    return sqlite3.connect("data/bot.db")


def _require_login(request: Request):
    if request.session.get("user") != ADMIN_WEB_USER:
        return RedirectResponse("/login", status_code=302)


def _xui_client():
    if not XUI_BASE_URL or not XUI_USERNAME or not XUI_PASSWORD:
        return None
    return ThreeXuiClient(
        base_url=XUI_BASE_URL,
        web_base_path=XUI_WEB_BASE_PATH,
        username=XUI_USERNAME,
        password=XUI_PASSWORD,
        insecure=XUI_INSECURE,
    )


def _panel_client_sets(plans):
    client = _xui_client()
    if not client:
        return set(), set()
    inbound_ids = sorted({int(p["inboundId"]) for p in plans if p.get("inboundId") is not None})
    emails = set()
    ids = set()
    for inbound_id in inbound_ids:
        try:
            resp = client.get_inbound(inbound_id)
            payload = resp.json() if resp.content else {}
            if not payload.get("success") or not payload.get("obj"):
                continue
            settings = json.loads(payload["obj"].get("settings") or "{}")
            for c in settings.get("clients", []) or []:
                if c.get("email"):
                    emails.add(c["email"])
                if c.get("id"):
                    ids.add(c["id"])
        except Exception:
            continue
    return emails, ids


def _find_client(inbound_id, client_id):
    client = _xui_client()
    if not client:
        return None
    resp = client.get_inbound(inbound_id)
    payload = resp.json() if resp.content else {}
    if not payload.get("success") or not payload.get("obj"):
        return None
    settings = json.loads(payload["obj"].get("settings") or "{}")
    for c in settings.get("clients", []) or []:
        if c.get("id") == client_id:
            return c
    return None


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return TEMPLATES.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == ADMIN_WEB_USER and password == ADMIN_WEB_PASSWORD:
        request.session["user"] = ADMIN_WEB_USER
        return RedirectResponse("/", status_code=302)
    return TEMPLATES.TemplateResponse(
        "login.html",
        {"request": request, "error": "Неверный логин или пароль"},
        status_code=401,
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    counts = get_counts()
    plans = load_plans()
    email_set, id_set = _panel_client_sets(plans)
    return TEMPLATES.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "title": "Админ панель",
            "active": "dashboard",
            "counts": counts,
            "panel_client_count": len(email_set) + len(id_set),
        },
    )


@app.get("/plans", response_class=HTMLResponse)
async def plans_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    return TEMPLATES.TemplateResponse(
        "plans.html",
        {"request": request, "title": "Тарифы", "active": "plans", "plans": load_plans()},
    )


@app.post("/plans")
async def plans_add(
    request: Request,
    title: str = Form(...),
    price: int = Form(...),
    currency: str = Form("RUB"),
    expiry_days: int = Form(...),
    total_gb: int = Form(0),
    limit_ip: int = Form(0),
    inbound_id: int = Form(...),
    flow: str = Form(""),
):
    auth = _require_login(request)
    if auth:
        return auth
    plans = load_plans()
    plan_id = f"plan_{int(datetime.utcnow().timestamp())}"
    plans.append(
        {
            "id": plan_id,
            "title": title,
            "price": price,
            "currency": currency,
            "expiryDays": expiry_days,
            "totalGB": total_gb,
            "limitIp": limit_ip,
            "inboundId": inbound_id,
            "flow": flow,
        }
    )
    save_plans(plans)
    return RedirectResponse("/plans", status_code=302)


@app.post("/plans/{plan_id}/delete")
async def plans_delete(request: Request, plan_id: str):
    auth = _require_login(request)
    if auth:
        return auth
    plans = [p for p in load_plans() if p.get("id") != plan_id]
    save_plans(plans)
    return RedirectResponse("/plans", status_code=302)


@app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    return TEMPLATES.TemplateResponse(
        "users.html",
        {"request": request, "title": "Пользователи", "active": "users", "users": list_users()},
    )


@app.get("/users/{user_id}", response_class=HTMLResponse)
async def user_editor(request: Request, user_id: int):
    auth = _require_login(request)
    if auth:
        return auth
    conn = _db()
    cur = conn.execute(
        "SELECT id, tg_id, username, first_name, balance, ref_code, referrer_id FROM users WHERE id = ?",
        (user_id,),
    )
    user = cur.fetchone()
    subs = conn.execute(
        "SELECT id, plan_id, client_email, client_uuid, expires_at FROM subscriptions WHERE user_id = ? ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return TEMPLATES.TemplateResponse(
        "user_edit.html",
        {
            "request": request,
            "title": "Редактор пользователя",
            "active": "users",
            "user": user,
            "subs": subs,
        },
    )


@app.post("/users/{user_id}/update")
async def user_update(
    request: Request,
    user_id: int,
    balance: int = Form(...),
    username: str = Form(""),
    first_name: str = Form(""),
):
    auth = _require_login(request)
    if auth:
        return auth
    conn = _db()
    conn.execute(
        "UPDATE users SET balance = ?, username = ?, first_name = ? WHERE id = ?",
        (balance, username, first_name, user_id),
    )
    conn.commit()
    conn.close()
    return RedirectResponse(f"/users/{user_id}", status_code=302)


@app.post("/users/{user_id}/balance")
async def users_balance(request: Request, user_id: int, balance: int = Form(...)):
    auth = _require_login(request)
    if auth:
        return auth
    update_balance(user_id, balance)
    return RedirectResponse("/users", status_code=302)


@app.get("/subscriptions", response_class=HTMLResponse)
async def subscriptions_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    subs = list_subscriptions()
    plans = load_plans()
    email_set, id_set = _panel_client_sets(plans)
    return TEMPLATES.TemplateResponse(
        "subscriptions.html",
        {
            "request": request,
            "title": "Подписки",
            "active": "subscriptions",
            "subs": subs,
            "panel_emails": email_set,
            "panel_ids": id_set,
        },
    )


@app.post("/subscriptions/{sub_id}/extend")
async def subscriptions_extend(request: Request, sub_id: int, days: int = Form(...)):
    auth = _require_login(request)
    if auth:
        return auth
    sub = get_subscription(sub_id)
    if not sub:
        return RedirectResponse("/subscriptions", status_code=302)
    inbound_id = sub[3]
    client_id = sub[5]
    client = _find_client(inbound_id, client_id)
    xui = _xui_client()
    if client and xui:
        expiry = client.get("expiryTime") or 0
        added_ms = int(days) * 24 * 60 * 60 * 1000
        client["expiryTime"] = max(expiry, int(datetime.utcnow().timestamp() * 1000)) + added_ms
        xui.update_client(client_id, inbound_id, client)
    return RedirectResponse("/subscriptions", status_code=302)


@app.post("/subscriptions/{sub_id}/disable")
async def subscriptions_disable(request: Request, sub_id: int):
    auth = _require_login(request)
    if auth:
        return auth
    sub = get_subscription(sub_id)
    if not sub:
        return RedirectResponse("/subscriptions", status_code=302)
    inbound_id = sub[3]
    client_id = sub[5]
    client = _find_client(inbound_id, client_id)
    xui = _xui_client()
    if client and xui:
        client["enable"] = False
        xui.update_client(client_id, inbound_id, client)
    return RedirectResponse("/subscriptions", status_code=302)


@app.post("/subscriptions/{sub_id}/delete")
async def subscriptions_delete(request: Request, sub_id: int):
    auth = _require_login(request)
    if auth:
        return auth
    sub = get_subscription(sub_id)
    if not sub:
        return RedirectResponse("/subscriptions", status_code=302)
    inbound_id = sub[3]
    client_id = sub[5]
    xui = _xui_client()
    if xui:
        xui.delete_client(inbound_id, client_id)
    return RedirectResponse("/subscriptions", status_code=302)


@app.post("/subscriptions/create")
async def subscriptions_create(
    request: Request,
    user_id: int = Form(...),
    plan_id: str = Form(...),
):
    auth = _require_login(request)
    if auth:
        return auth
    plans = load_plans()
    plan = next((p for p in plans if p["id"] == plan_id), None)
    if not plan:
        return RedirectResponse("/subscriptions", status_code=302)
    client_uuid = os.urandom(16).hex()
    client_email = f"{user_id}_{int(datetime.utcnow().timestamp())}@admin"
    expiry_days = plan.get("expiryDays") or 365
    expires_at = datetime.utcnow() + timedelta(days=expiry_days)
    sub_id = os.urandom(8).hex()
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
    xui = _xui_client()
    if not xui:
        return RedirectResponse("/subscriptions", status_code=302)
    response = xui.add_client(plan["inboundId"], client)
    payload = response.json() if response.content else {}
    conn = _db()
    create_order(conn, user_id, plan_id, "created", json.dumps(payload))
    create_subscription(
        conn,
        user_id,
        plan_id,
        plan["inboundId"],
        client_email,
        client_uuid,
        expires_at.isoformat(),
        json.dumps(payload),
    )
    conn.close()
    return RedirectResponse("/subscriptions", status_code=302)


@app.get("/content", response_class=HTMLResponse)
async def content_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    conn = _db()
    cfg = get_all_config(conn)
    conn.close()
    return TEMPLATES.TemplateResponse(
        "content.html",
        {"request": request, "title": "Контент", "active": "content", "cfg": cfg},
    )


@app.post("/content")
async def content_save(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    form = await request.form()
    conn = _db()
    for key, value in dict(form).items():
        set_config(conn, key, value)
    conn.close()
    return RedirectResponse("/content", status_code=302)


@app.get("/broadcast", response_class=HTMLResponse)
async def broadcast_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    return TEMPLATES.TemplateResponse(
        "broadcast.html",
        {
            "request": request,
            "title": "Рассылка",
            "active": "broadcast",
            "items": list_broadcasts(),
        },
    )


@app.post("/broadcast")
async def broadcast_send(request: Request, message: str = Form(...)):
    auth = _require_login(request)
    if auth:
        return auth
    if not BOT_TOKEN:
        return RedirectResponse("/broadcast", status_code=302)
    import httpx

    form = await request.form()
    filter_mode = form.get("filter_mode", "all")
    min_balance = int(form.get("min_balance") or 0)
    users = list_users_for_broadcast()
    if filter_mode != "all" or min_balance > 0:
        conn = _db()
        cur = conn.execute("SELECT id, tg_id, balance FROM users")
        user_rows = cur.fetchall()
        conn.close()
        allowed = set()
        for row in user_rows:
            user_id, tg_id, balance = row[0], row[1], row[2] or 0
            if min_balance and balance < min_balance:
                continue
            if filter_mode == "with_subs":
                cur = _db()
                sub = cur.execute(
                    "SELECT 1 FROM subscriptions WHERE user_id = ? LIMIT 1", (user_id,)
                ).fetchone()
                cur.close()
                if not sub:
                    continue
            if filter_mode == "without_subs":
                cur = _db()
                sub = cur.execute(
                    "SELECT 1 FROM subscriptions WHERE user_id = ? LIMIT 1", (user_id,)
                ).fetchone()
                cur.close()
                if sub:
                    continue
            allowed.add(tg_id)
        users = [u for u in users if u in allowed]
    for tg_id in users:
        try:
            httpx.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": tg_id, "text": message},
                timeout=10,
            )
        except Exception:
            continue
    conn = _db()
    create_broadcast(conn, message)
    conn.close()
    return RedirectResponse("/broadcast", status_code=302)


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    return TEMPLATES.TemplateResponse(
        "orders.html",
        {"request": request, "title": "Заказы", "active": "orders", "orders": list_orders()},
    )


@app.get("/promos", response_class=HTMLResponse)
async def promos_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    return TEMPLATES.TemplateResponse(
        "promos.html",
        {"request": request, "title": "Промокоды", "active": "promos", "promos": list_promos()},
    )


@app.post("/promos")
async def promos_add(
    request: Request,
    code: str = Form(...),
    discount_percent: int = Form(0),
    discount_amount: int = Form(0),
    usage_limit: int = Form(0),
    expires_at: str = Form(""),
    active: int = Form(1),
):
    auth = _require_login(request)
    if auth:
        return auth
    add_promo(code.upper(), discount_percent, discount_amount, usage_limit, expires_at or None, active)
    return RedirectResponse("/promos", status_code=302)


@app.post("/promos/{code}/delete")
async def promos_delete(request: Request, code: str):
    auth = _require_login(request)
    if auth:
        return auth
    delete_promo(code)
    return RedirectResponse("/promos", status_code=302)


@app.get("/settings", response_class=HTMLResponse)
async def settings_page(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    meta_map = {
        "BOT_TOKEN": {
            "label": "Токен бота",
            "help": "Токен, выданный BotFather. Нужен для работы Telegram‑бота.",
        },
        "XUI_BASE_URL": {
            "label": "Адрес панели 3X‑UI",
            "help": "Полный URL панели, например https://panel.example.com:54321",
        },
        "XUI_WEB_BASE_PATH": {
            "label": "Путь панели",
            "help": "Если панель доступна по пути, укажите его, например /xui",
        },
        "XUI_USERNAME": {
            "label": "Логин панели",
            "help": "Логин администратора 3X‑UI.",
        },
        "XUI_PASSWORD": {
            "label": "Пароль панели",
            "help": "Пароль администратора 3X‑UI.",
        },
        "XUI_INSECURE": {
            "label": "TLS проверка",
            "help": "false — проверять сертификат. true — отключить проверку (самоподписанный).",
        },
        "DEFAULT_CURRENCY": {
            "label": "Валюта по умолчанию",
            "help": "Например RUB или USD.",
        },
        "SUBSCRIPTION_BASE_URL": {
            "label": "Базовый URI подписки",
            "help": "Префикс подписки за прокси, например https://srv1.example.com/abc/",
        },
        "SUPPORT_USERNAME": {
            "label": "Юзернейм поддержки",
            "help": "Ник поддержки в Telegram без @.",
        },
        "SUPPORT_TG_ID": {
            "label": "ID поддержки",
            "help": "Числовой Telegram ID, если нет юзернейма.",
        },
        "BOT_USERNAME": {
            "label": "Юзернейм бота",
            "help": "Ник бота без @ для реферальной ссылки.",
        },
        "ADMIN_TG_ID": {
            "label": "ID админа бота",
            "help": "Куда отправлять ошибки панели (числовой Telegram ID).",
        },
        "ADMIN_WEB_USER": {
            "label": "Логин админ‑панели",
            "help": "Логин для входа в веб‑админку.",
        },
        "ADMIN_WEB_PASSWORD": {
            "label": "Пароль админ‑панели",
            "help": "Пароль для входа в веб‑админку.",
        },
        "ADMIN_WEB_SECRET": {
            "label": "Секрет сессий",
            "help": "Любая длинная случайная строка для подписи cookie.",
        },
    }
    return TEMPLATES.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "title": "Настройки",
            "active": "settings",
            "env": load_env_file(),
            "meta_map": meta_map,
        },
    )


@app.post("/settings")
async def settings_save(request: Request):
    auth = _require_login(request)
    if auth:
        return auth
    form = await request.form()
    update_env_file(dict(form))
    return RedirectResponse("/settings", status_code=302)
