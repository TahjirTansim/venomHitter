#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Speedy Hitter — Configuration.

Every identity value comes from environment variables or .env.
Safe to commit — no real credentials, no owner residue.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def _req(name: str, default: str = "") -> str:
    val = os.environ.get(name, default)
    if not val or val in ("REPLACE_ME", "0", ""):
        print(f"[CONFIG] WARNING: env var {name} is not set")
    return val


# ─── Telegram credentials ────────────────────────────────────────
API_ID    = int(_req("API_ID", "0") or 0)
API_HASH  = _req("API_HASH")
BOT_TOKEN = _req("BOT_TOKEN")

# ─── Admin IDs ───────────────────────────────────────────────────
ADMIN_ID_RAW = _req("ADMIN_ID", "")
DEFAULT_ADMIN_IDS = {
    int(x.strip()) for x in ADMIN_ID_RAW.split(",") if x.strip().isdigit()
}

# ─── Branding ────────────────────────────────────────────────────
OWNER_NAME     = os.environ.get("OWNER_NAME", "Bot Owner")
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "")
OWNER_ID       = int(os.environ.get("OWNER_ID", "0") or 0)
BOT_BRAND      = os.environ.get("BOT_BRAND", "Speedy Hitter")
KEY_PREFIX     = os.environ.get("KEY_PREFIX", "SPEEDY")
SESSION_NAME   = os.environ.get("SESSION_NAME", "speedy_hitter")

# ─── Engine tuning ───────────────────────────────────────────────
MAX_SITE_AMOUNT      = float(os.environ.get("MAX_SITE_AMOUNT", "20.0"))
SITE_ERROR_THRESHOLD = int(os.environ.get("SITE_ERROR_THRESHOLD", "8"))
MAX_LOG_ENTRIES      = int(os.environ.get("MAX_LOG_ENTRIES", "25000"))

NOTIFY_GROUP_ID = os.environ.get("NOTIFY_GROUP_ID") or None
if NOTIFY_GROUP_ID:
    NOTIFY_GROUP_ID = int(NOTIFY_GROUP_ID)

# ─── Amount tiers ────────────────────────────────────────────────
AMOUNT_TIERS = {
    "1":  ("$1",  "~$1 sites"),
    "5":  ("$5",  "~$5 sites"),
    "10": ("$10", "~$10 sites"),
    "20": ("$20", "~$20 sites"),
    "any":("Any", "All sites"),
}

_TIER_ORDER = ["1", "5", "10", "20"]

# ─── Access tiers ────────────────────────────────────────────────
TIER_LIMITS = {
    "admin": 25000,
    "auth":  25000,
    "grant": 25000,
    "key":   25000,
}
