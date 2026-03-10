import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "bot.db"


def _connect():
    return sqlite3.connect(DB_PATH)


def get_counts():
    conn = _connect()
    cur = conn.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM subscriptions")
    subs = cur.fetchone()[0]
    cur = conn.execute("SELECT COUNT(*) FROM orders")
    orders = cur.fetchone()[0]
    conn.close()
    return {
        "users": users,
        "subscriptions": subs,
        "orders": orders,
    }


def list_users():
    conn = _connect()
    cur = conn.execute(
        "SELECT id, tg_id, username, first_name, balance, created_at FROM users ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def update_balance(user_id, balance):
    conn = _connect()
    conn.execute("UPDATE users SET balance = ? WHERE id = ?", (balance, user_id))
    conn.commit()
    conn.close()


def list_users_for_broadcast():
    conn = _connect()
    cur = conn.execute("SELECT tg_id FROM users")
    rows = cur.fetchall()
    conn.close()
    return [r[0] for r in rows]


def get_subscription(sub_id):
    conn = _connect()
    cur = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
    row = cur.fetchone()
    conn.close()
    return row


def list_broadcasts():
    conn = _connect()
    cur = conn.execute("SELECT id, message, created_at FROM broadcasts ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return rows


def list_subscriptions():
    conn = _connect()
    cur = conn.execute(
        "SELECT id, user_id, plan_id, inbound_id, client_email, client_uuid, expires_at, created_at FROM subscriptions ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_orders():
    conn = _connect()
    cur = conn.execute(
        "SELECT id, user_id, plan_id, status, created_at FROM orders ORDER BY id DESC"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def list_promos():
    conn = _connect()
    cur = conn.execute(
        "SELECT code, discount_percent, discount_amount, usage_limit, used_count, expires_at, active FROM promo_codes ORDER BY code"
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def add_promo(code, discount_percent, discount_amount, usage_limit, expires_at, active):
    conn = _connect()
    conn.execute(
        """
        INSERT OR REPLACE INTO promo_codes
        (code, discount_percent, discount_amount, usage_limit, used_count, expires_at, active)
        VALUES (?, ?, ?, ?, COALESCE((SELECT used_count FROM promo_codes WHERE code = ?), 0), ?, ?)
        """,
        (code, discount_percent, discount_amount, usage_limit, code, expires_at, active),
    )
    conn.commit()
    conn.close()


def delete_promo(code):
    conn = _connect()
    conn.execute("DELETE FROM promo_codes WHERE code = ?", (code,))
    conn.commit()
    conn.close()
