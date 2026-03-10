import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ENV_PATH = Path(".env")
PLANS_PATH = Path("config/plans.json")

ALLOWED_ENV_KEYS = {
    "BOT_TOKEN",
    "XUI_BASE_URL",
    "XUI_WEB_BASE_PATH",
    "XUI_USERNAME",
    "XUI_PASSWORD",
    "XUI_INSECURE",
    "DEFAULT_CURRENCY",
    "SUBSCRIPTION_BASE_URL",
    "SUPPORT_USERNAME",
    "SUPPORT_TG_ID",
    "ADMIN_TG_ID",
    "BOT_USERNAME",
    "ADMIN_WEB_USER",
    "ADMIN_WEB_PASSWORD",
    "ADMIN_WEB_SECRET",
}


def load_env_file():
    values = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def update_env_file(updates):
    updates = {k: v for k, v in updates.items() if k in ALLOWED_ENV_KEYS}
    lines = []
    existing = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, _ = line.split("=", 1)
                key = key.strip()
                existing[key] = line
            lines.append(line)
    else:
        ENV_PATH.write_text("", encoding="utf-8")

    for key, value in updates.items():
        new_line = f"{key}={value}"
        if key in existing:
            lines = [new_line if l.startswith(f"{key}=") else l for l in lines]
        else:
            lines.append(new_line)

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_plans():
    if not PLANS_PATH.exists():
        return []
    return json.loads(PLANS_PATH.read_text(encoding="utf-8"))


def save_plans(plans):
    PLANS_PATH.write_text(
        json.dumps(plans, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
