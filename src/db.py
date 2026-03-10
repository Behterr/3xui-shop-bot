import json
import os
import sqlite3
from pathlib import Path

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "bot.db"


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")

    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tg_id INTEGER UNIQUE NOT NULL,
          username TEXT,
          first_name TEXT,
          created_at TEXT NOT NULL,
          last_message_id INTEGER,
          balance INTEGER DEFAULT 0,
          ref_code TEXT,
          referrer_id INTEGER,
          state TEXT,
          state_data TEXT,
          active_promo_code TEXT
        );

        CREATE TABLE IF NOT EXISTS orders (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          plan_id TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          xui_response TEXT,
          FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS subscriptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          plan_id TEXT NOT NULL,
          inbound_id INTEGER NOT NULL,
          client_email TEXT NOT NULL,
          client_uuid TEXT NOT NULL,
          expires_at TEXT NOT NULL,
          created_at TEXT NOT NULL,
          xui_response TEXT,
          FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS promo_codes (
          code TEXT PRIMARY KEY,
          discount_percent INTEGER DEFAULT 0,
          discount_amount INTEGER DEFAULT 0,
          usage_limit INTEGER DEFAULT 0,
          used_count INTEGER DEFAULT 0,
          expires_at TEXT,
          active INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS promo_redemptions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          code TEXT NOT NULL,
          created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS transactions (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          user_id INTEGER NOT NULL,
          amount INTEGER NOT NULL,
          currency TEXT NOT NULL,
          status TEXT NOT NULL,
          provider TEXT NOT NULL,
          payload TEXT,
          created_at TEXT NOT NULL,
          FOREIGN KEY(user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS app_config (
          key TEXT PRIMARY KEY,
          value TEXT
        );

        CREATE TABLE IF NOT EXISTS broadcasts (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          message TEXT NOT NULL,
          created_at TEXT NOT NULL
        );
        """
    )
    # Backward compatible migrations for existing databases
    try:
        conn.execute("ALTER TABLE users ADD COLUMN last_message_id INTEGER;")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE users ADD COLUMN balance INTEGER DEFAULT 0;")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    for stmt in [
        "ALTER TABLE users ADD COLUMN ref_code TEXT;",
        "ALTER TABLE users ADD COLUMN referrer_id INTEGER;",
        "ALTER TABLE users ADD COLUMN state TEXT;",
        "ALTER TABLE users ADD COLUMN state_data TEXT;",
        "ALTER TABLE users ADD COLUMN active_promo_code TEXT;",
    ]:
        try:
            conn.execute(stmt)
            conn.commit()
        except sqlite3.OperationalError:
            pass

    return conn


def upsert_user(conn, tg_user):
    now = _iso_now()
    conn.execute(
        """
        INSERT INTO users (tg_id, username, first_name, created_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(tg_id) DO UPDATE SET
          username=excluded.username,
          first_name=excluded.first_name
        """,
        (tg_user.id, tg_user.username, tg_user.first_name, now),
    )
    conn.commit()
    cur = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_user.id,))
    return cur.fetchone()


def get_user_by_tg_id(conn, tg_id):
    cur = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
    return cur.fetchone()


def set_last_message_id(conn, user_id, message_id):
    conn.execute(
        "UPDATE users SET last_message_id = ? WHERE id = ?",
        (message_id, user_id),
    )
    conn.commit()


def get_balance(conn, user_id):
    cur = conn.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    return row[0] if row else 0


def set_balance(conn, user_id, balance):
    conn.execute("UPDATE users SET balance = ? WHERE id = ?", (balance, user_id))
    conn.commit()


def add_balance(conn, user_id, amount):
    conn.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE id = ?", (amount, user_id))
    conn.commit()


def set_ref_code(conn, user_id, ref_code):
    conn.execute("UPDATE users SET ref_code = ? WHERE id = ?", (ref_code, user_id))
    conn.commit()


def set_referrer(conn, user_id, referrer_id):
    conn.execute("UPDATE users SET referrer_id = ? WHERE id = ? AND referrer_id IS NULL", (referrer_id, user_id))
    conn.commit()


def set_state(conn, user_id, state, state_data=None):
    conn.execute(
        "UPDATE users SET state = ?, state_data = ? WHERE id = ?",
        (state, state_data, user_id),
    )
    conn.commit()


def clear_state(conn, user_id):
    conn.execute("UPDATE users SET state = NULL, state_data = NULL WHERE id = ?", (user_id,))
    conn.commit()


def set_active_promo(conn, user_id, code):
    conn.execute("UPDATE users SET active_promo_code = ? WHERE id = ?", (code, user_id))
    conn.commit()


def clear_active_promo(conn, user_id):
    conn.execute("UPDATE users SET active_promo_code = NULL WHERE id = ?", (user_id,))
    conn.commit()


def create_order(conn, user_id, plan_id, status, xui_response=None):
    now = _iso_now()
    cur = conn.execute(
        """
        INSERT INTO orders (user_id, plan_id, status, created_at, xui_response)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, plan_id, status, now, xui_response),
    )
    conn.commit()
    return cur.lastrowid


def create_transaction(conn, user_id, amount, currency, status, provider, payload=None):
    now = _iso_now()
    cur = conn.execute(
        """
        INSERT INTO transactions (user_id, amount, currency, status, provider, payload, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, amount, currency, status, provider, payload, now),
    )
    conn.commit()
    return cur.lastrowid


def update_transaction_status(conn, tx_id, status, payload=None):
    conn.execute(
        "UPDATE transactions SET status = ?, payload = ? WHERE id = ?",
        (status, payload, tx_id),
    )
    conn.commit()


def update_transaction_by_payload(conn, payload_key, status, payload=None):
    conn.execute(
        "UPDATE transactions SET status = ?, payload = ? WHERE payload = ?",
        (status, payload, payload_key),
    )
    conn.commit()


def create_subscription(
    conn,
    user_id,
    plan_id,
    inbound_id,
    client_email,
    client_uuid,
    expires_at,
    xui_response=None,
):
    now = _iso_now()
    cur = conn.execute(
        """
        INSERT INTO subscriptions (
          user_id, plan_id, inbound_id, client_email, client_uuid,
          expires_at, created_at, xui_response
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            plan_id,
            inbound_id,
            client_email,
            client_uuid,
            expires_at,
            now,
            xui_response,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_user_subscriptions(conn, user_id):
    cur = conn.execute(
        "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    return cur.fetchall()


def list_users_basic(conn):
    cur = conn.execute("SELECT id, tg_id, username, first_name, balance FROM users ORDER BY id DESC")
    return cur.fetchall()


def get_subscription_by_id(conn, sub_id):
    cur = conn.execute("SELECT * FROM subscriptions WHERE id = ?", (sub_id,))
    return cur.fetchone()


def get_plan_by_id(conn, plan_id):
    cur = conn.execute("SELECT * FROM subscriptions WHERE plan_id = ? LIMIT 1", (plan_id,))
    return cur.fetchone()


def set_config(conn, key, value):
    conn.execute(
        "INSERT INTO app_config (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()


def get_config(conn, key, default=None):
    cur = conn.execute("SELECT value FROM app_config WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else default


def get_all_config(conn):
    cur = conn.execute("SELECT key, value FROM app_config")
    rows = cur.fetchall()
    return {r[0]: r[1] for r in rows}


def create_broadcast(conn, message):
    now = _iso_now()
    conn.execute("INSERT INTO broadcasts (message, created_at) VALUES (?, ?)", (message, now))
    conn.commit()


def get_promo_code(conn, code):
    cur = conn.execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
    return cur.fetchone()


def has_redeemed_promo(conn, user_id, code):
    cur = conn.execute(
        "SELECT 1 FROM promo_redemptions WHERE user_id = ? AND code = ? LIMIT 1",
        (user_id, code),
    )
    return cur.fetchone() is not None


def redeem_promo(conn, user_id, code):
    now = _iso_now()
    conn.execute(
        "INSERT INTO promo_redemptions (user_id, code, created_at) VALUES (?, ?, ?)",
        (user_id, code, now),
    )
    conn.execute("UPDATE promo_codes SET used_count = used_count + 1 WHERE code = ?", (code,))
    conn.commit()


def _iso_now():
    return _utc_now().isoformat()


def _utc_now():
    import datetime

    return datetime.datetime.utcnow().replace(microsecond=0)
