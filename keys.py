#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Access keys + timed user access."""
import json
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import KEY_PREFIX, TIER_LIMITS

BASE_DIR = Path(__file__).parent
KEYS_FILE        = BASE_DIR / "keys.json"
USER_ACCESS_FILE = BASE_DIR / "user_access.json"


# ─── in-memory caches ────────────────────────────────────────────
_keys_data:   dict = {}
_user_access: dict = {}


def load_keys():
    global _keys_data
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE) as f:
                _keys_data = json.load(f)
        except Exception:
            _keys_data = {}


def save_keys():
    try:
        with open(KEYS_FILE, "w") as f:
            json.dump(_keys_data, f, indent=2)
    except Exception:
        pass


def load_user_access():
    global _user_access
    if os.path.exists(USER_ACCESS_FILE):
        try:
            with open(USER_ACCESS_FILE) as f:
                _user_access = {int(k): v for k, v in json.load(f).items()}
        except Exception:
            _user_access = {}


def save_user_access():
    try:
        with open(USER_ACCESS_FILE, "w") as f:
            json.dump({str(k): v for k, v in _user_access.items()}, f, indent=2)
    except Exception:
        pass


# ─── key generation & redemption ─────────────────────────────────
def generate_key() -> str:
    chars = string.ascii_letters + string.digits
    rand  = "".join(secrets.choice(chars) for _ in range(20))
    return f"{KEY_PREFIX}-{rand}"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def set_user_access(uid: int, tier: str, plan_days: int, granted_by: str = "admin"):
    expires = (_now_utc() + timedelta(days=plan_days)).isoformat()
    _user_access[uid] = {
        "tier":       tier,
        "expires_at": expires,
        "plan_days":  plan_days,
        "granted_by": granted_by,
        "granted_at": _now_utc().isoformat(),
    }
    save_user_access()


def revoke_user_access(uid: int):
    _user_access.pop(uid, None)
    save_user_access()


def is_access_valid(uid: int) -> bool:
    acc = _user_access.get(uid)
    if not acc:
        return False
    try:
        exp = datetime.fromisoformat(acc["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return _now_utc() < exp
    except Exception:
        return False


def get_user_tier(uid: int, is_admin_fn) -> Optional[str]:
    if is_admin_fn(uid):
        return "admin"
    if is_access_valid(uid):
        return _user_access[uid].get("tier", "key")
    return None


def get_user_limit(uid: int, is_admin_fn) -> int:
    tier = get_user_tier(uid, is_admin_fn)
    return TIER_LIMITS.get(tier, 0)


def time_remaining(uid: int) -> Optional[str]:
    acc = _user_access.get(uid)
    if not acc:
        return None
    try:
        exp = datetime.fromisoformat(acc["expires_at"])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = exp - _now_utc()
        if delta.total_seconds() <= 0:
            return None
        d = delta.days
        h = delta.seconds // 3600
        m = (delta.seconds % 3600) // 60
        if d > 0:
            return f"{d}d {h}h {m}m"
        if h > 0:
            return f"{h}h {m}m"
        return f"{m}m"
    except Exception:
        return None


def redeem_key(key: str, uid: int) -> dict:
    """Attempt to redeem *key* for *uid*. Returns a result dict."""
    if key not in _keys_data:
        return {"ok": False, "reason": "invalid"}
    kdata = _keys_data[key]
    if kdata.get("redeemed_by") is not None:
        return {"ok": False, "reason": "used"}
    plan_days = kdata["plan_days"]
    set_user_access(uid, "key", plan_days, granted_by="key")
    _keys_data[key]["redeemed_by"] = uid
    _keys_data[key]["redeemed_at"] = _now_utc().isoformat()
    save_keys()
    return {"ok": True, "plan_days": plan_days}


def create_keys(count: int, days: int) -> list:
    """Generate *count* fresh unused keys, each valid for *days* days."""
    new_keys = []
    for _ in range(count):
        k = generate_key()
        while k in _keys_data:
            k = generate_key()
        _keys_data[k] = {
            "plan_days":  days,
            "redeemed_by": None,
            "redeemed_at": None,
            "created_at": _now_utc().isoformat(),
        }
        new_keys.append(k)
    save_keys()
    return new_keys


def delete_key(key: str) -> bool:
    if key not in _keys_data:
        return False
    del _keys_data[key]
    save_keys()
    return True


def keys_summary() -> dict:
    total  = len(_keys_data)
    unused = sum(1 for v in _keys_data.values() if v.get("redeemed_by") is None)
    used   = total - unused
    return {"total": total, "unused": unused, "used": used}


def all_keys() -> dict:
    return _keys_data


def all_user_access() -> dict:
    return _user_access


# ─── bootstrap ───────────────────────────────────────────────────
load_keys()
load_user_access()
