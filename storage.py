#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""File-backed storage: sites, proxies, per-user proxies, prefs, stats, logs."""
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import urllib.parse

from config import (
    AMOUNT_TIERS,
    MAX_LOG_ENTRIES,
    SITES_META_FILE,
    _TIER_ORDER,
)


# ─── file paths (relative to this script) ────────────────────────
BASE_DIR = Path(__file__).parent

PREMIUM_FILE        = BASE_DIR / "premium.txt"
SITES_FILE          = BASE_DIR / "sites.txt"
PROXY_FILE          = BASE_DIR / "proxy.txt"
USER_PROXY_FILE     = BASE_DIR / "user_proxies.json"
KEYS_FILE           = BASE_DIR / "keys.json"
USER_ACCESS_FILE    = BASE_DIR / "user_access.json"
WORKING_PROXY_FILE  = BASE_DIR / "working_proxies.txt"
USER_POOL_FILE      = BASE_DIR / "user_pool.json"
STATS_FILE          = BASE_DIR / "user_stats.json"
LOGS_FILE           = BASE_DIR / "card_logs.json"
SITES_META_FILE_ABS = BASE_DIR / "sites_meta.json"
USER_PREFS_FILE     = BASE_DIR / "user_prefs.json"


# ─── simple text-list helpers ────────────────────────────────────
def get_file_lines(fp) -> List[str]:
    if not os.path.exists(fp):
        return []
    try:
        with open(fp, "r", encoding="utf-8", errors="ignore") as f:
            return [ln.strip() for ln in f if ln.strip()]
    except Exception:
        return []


def load_premium_users() -> List[str]:
    return get_file_lines(PREMIUM_FILE)


def load_sites() -> List[str]:
    return get_file_lines(SITES_FILE)


def load_proxies() -> List[str]:
    return get_file_lines(PROXY_FILE)


# ─── user proxy pool ─────────────────────────────────────────────
user_proxies: Dict[int, List[str]] = {}


def load_user_proxies():
    global user_proxies
    if not os.path.exists(USER_PROXY_FILE):
        user_proxies = {}
        return
    try:
        with open(USER_PROXY_FILE, "r") as f:
            raw = json.load(f)
        migrated = {}
        for k, v in raw.items():
            uid_int = int(k)
            if isinstance(v, list):
                migrated[uid_int] = [x for x in v if isinstance(x, str) and x.strip()]
            elif isinstance(v, str) and v.strip():
                migrated[uid_int] = [v.strip()]
            else:
                migrated[uid_int] = []
        user_proxies = migrated
    except Exception:
        user_proxies = {}


def save_user_proxies():
    try:
        with open(USER_PROXY_FILE, "w") as f:
            json.dump({str(k): v for k, v in user_proxies.items()}, f, indent=2)
    except Exception:
        pass


def get_user_proxy(uid: int):
    lst = user_proxies.get(uid, [])
    return lst[0] if lst else None


def get_user_proxy_list(uid: int) -> List[str]:
    return list(user_proxies.get(uid, []))


def set_user_proxy(uid: int, proxy: str):
    user_proxies[uid] = [proxy.strip()]
    save_user_proxies()


def add_user_proxy(uid: int, proxy: str) -> bool:
    proxy = proxy.strip()
    lst   = user_proxies.setdefault(uid, [])
    if proxy in lst:
        return False
    lst.append(proxy)
    save_user_proxies()
    return True


def add_user_proxies_bulk(uid: int, proxies: List[str]) -> dict:
    lst    = user_proxies.setdefault(uid, [])
    exists = set(lst)
    added = dups = invalid = 0
    seen_batch: set = set()
    for p in proxies:
        p = p.strip()
        if not p or p.startswith("#"):
            continue
        if not _validate_proxy_fmt(p):
            invalid += 1
            continue
        if p in exists or p in seen_batch:
            dups += 1
            continue
        lst.append(p)
        seen_batch.add(p)
        added += 1
    if added:
        save_user_proxies()
    return {"added": added, "duplicates": dups, "invalid": invalid}


def remove_user_proxy(uid: int):
    user_proxies.pop(uid, None)
    save_user_proxies()


def remove_user_proxy_entry(uid: int, proxy: str) -> bool:
    lst   = user_proxies.get(uid, [])
    proxy = proxy.strip()
    if proxy not in lst:
        return False
    lst.remove(proxy)
    if not lst:
        user_proxies.pop(uid, None)
    save_user_proxies()
    return True


def clear_user_proxies(uid: int):
    user_proxies.pop(uid, None)
    save_user_proxies()


# ─── user pool toggle ────────────────────────────────────────────
user_pool_enabled: Dict[int, bool] = {}


def load_user_pool():
    global user_pool_enabled
    if os.path.exists(USER_POOL_FILE):
        try:
            with open(USER_POOL_FILE, "r") as f:
                user_pool_enabled = {int(k): v for k, v in json.load(f).items()}
        except Exception:
            user_pool_enabled = {}


def save_user_pool():
    try:
        with open(USER_POOL_FILE, "w") as f:
            json.dump({str(k): v for k, v in user_pool_enabled.items()}, f)
    except Exception:
        pass


# ─── amount prefs ────────────────────────────────────────────────
def get_user_amount_tier(uid: int) -> str:
    try:
        with open(USER_PREFS_FILE) as f:
            prefs = json.load(f)
        return prefs.get(str(uid), {}).get("amount_tier", "any")
    except Exception:
        return "any"


def set_user_amount_tier(uid: int, tier: str):
    try:
        try:
            with open(USER_PREFS_FILE) as f:
                prefs = json.load(f)
        except Exception:
            prefs = {}
        prefs.setdefault(str(uid), {})["amount_tier"] = tier
        with open(USER_PREFS_FILE, "w") as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass


def tier_range_label(tier: str) -> str:
    if tier == "any" or tier not in _TIER_ORDER:
        return "Any"
    idx = _TIER_ORDER.index(tier)
    if idx == 0:
        return f"${tier}"
    return f"$1–${tier}"


def load_sites_for_user(uid: int) -> Tuple[List[str], str]:
    all_sites = load_sites()
    tier = get_user_amount_tier(uid)
    if tier == "any":
        return all_sites, "any"
    meta = load_sites_meta()
    if tier in _TIER_ORDER:
        cutoff = _TIER_ORDER.index(tier)
        allowed = set(_TIER_ORDER[:cutoff + 1])
    else:
        allowed = {tier}
    matched = [s for s in all_sites if meta.get(s, {}).get("tier") in allowed]
    if matched:
        return matched, tier
    return all_sites, "any"


# ─── sites meta ──────────────────────────────────────────────────
def load_sites_meta() -> dict:
    try:
        with open(SITES_META_FILE_ABS) as f:
            return json.load(f)
    except Exception:
        return {}


def save_sites_meta(data: dict):
    try:
        with open(SITES_META_FILE_ABS, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def tag_site_tier(site_url: str, tier: str):
    meta = load_sites_meta()
    meta.setdefault(site_url, {})["tier"] = tier
    save_sites_meta(meta)


def price_to_tier(price: float) -> str:
    if price < 3.0:  return "1"
    if price < 8.0:  return "5"
    if price < 15.0: return "10"
    return "20"


# ─── stats / logs ────────────────────────────────────────────────
_stats_lock = threading.Lock()
_logs_lock  = threading.Lock()


def _load_stats() -> dict:
    try:
        with open(STATS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_stats(data: dict):
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def record_check(uid: int, name: str, status: str, username: str = ""):
    with _stats_lock:
        data = _load_stats()
        key  = str(uid)
        entry = data.get(key, {"charged": 0, "approved": 0, "declined": 0, "files": 0, "first_seen": 0})
        if not entry.get("first_seen"):
            entry["first_seen"] = int(time.time())
        entry["name"] = name
        if username:
            entry["username"] = username
        entry["last_seen"] = int(time.time())
        if status == "Charged":
            entry["charged"] = entry.get("charged", 0) + 1
        elif status == "Approved":
            entry["approved"] = entry.get("approved", 0) + 1
        elif status in ("Dead", "Declined"):
            entry["declined"] = entry.get("declined", 0) + 1
        data[key] = entry
        _save_stats(data)


def record_mass_check(uid: int, name: str, charged: int, approved: int,
                      declined: int, username: str = ""):
    with _stats_lock:
        data = _load_stats()
        key  = str(uid)
        entry = data.get(key, {"charged": 0, "approved": 0, "declined": 0, "files": 0, "first_seen": 0})
        if not entry.get("first_seen"):
            entry["first_seen"] = int(time.time())
        entry["name"] = name
        if username:
            entry["username"] = username
        entry["last_seen"] = int(time.time())
        entry["charged"]  = entry.get("charged", 0) + charged
        entry["approved"] = entry.get("approved", 0) + approved
        entry["declined"] = entry.get("declined", 0) + declined
        entry["files"]    = entry.get("files", 0) + 1
        data[key] = entry
        _save_stats(data)


def record_log(uid: int, name: str, username: str,
               card: str, status: str, message: str,
               site: str, gateway: str, price: str):
    with _logs_lock:
        try:
            logs = json.loads(open(LOGS_FILE).read()) if os.path.exists(LOGS_FILE) else []
        except Exception:
            logs = []
        entry = {
            "ts":       int(time.time()),
            "uid":      str(uid),
            "name":     name,
            "username": username,
            "card":     card,
            "status":   status,
            "message":  message,
            "site":     site,
            "gateway":  gateway,
            "price":    price,
        }
        logs.insert(0, entry)
        if len(logs) > MAX_LOG_ENTRIES:
            logs = logs[:MAX_LOG_ENTRIES]
        try:
            with open(LOGS_FILE, "w") as f:
                json.dump(logs, f)
        except Exception:
            pass


# ─── proxy format validation ─────────────────────────────────────
def _validate_proxy_fmt(p: str) -> bool:
    p = p.strip()
    if not p or ":" not in p:
        return False
    if "://" in p:
        try:
            r = urllib.parse.urlparse(p)
            return bool(r.hostname) and r.port is not None and 1 <= r.port <= 65535
        except Exception:
            return False
    parts = p.split(":")
    try:
        port = int(parts[1])
        return bool(parts[0]) and 1 <= port <= 65535
    except (ValueError, IndexError):
        return False


def _validate_site_fmt(u: str) -> bool:
    u = u.strip()
    if not u:
        return False
    try:
        r = urllib.parse.urlparse(u)
        return r.scheme in ("http", "https") and bool(r.netloc)
    except Exception:
        return False


def _normalise_site(u: str) -> str:
    return u.rstrip("/")


def _tokenise(text: str) -> List[str]:
    tokens = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tokens.extend(line.split())
    return tokens


# ─── proxy normalisation (socks/http + base64 creds) ─────────────
def _is_base64url(s: str) -> bool:
    if len(s) < 16:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9\-_]+=*", s))


def _decode_base64url(s: str) -> str:
    import base64 as _b64
    try:
        b = s.replace("-", "+").replace("_", "/")
        b += "=" * ((4 - len(b) % 4) % 4)
        return _b64.b64decode(b).decode("utf-8", errors="replace")
    except Exception:
        return s


def normalize_proxy(raw: str) -> str:
    p = raw.strip()
    if not p:
        raise Exception("empty proxy")
    if "://" in p:
        parsed = urllib.parse.urlparse(p)
        if not parsed.netloc:
            raise Exception(f"invalid proxy URL: {raw}")
        return p
    parts = p.split(":")
    if len(parts) == 4:
        ip, port, user, pwd = parts
        if _is_base64url(user):
            user = _decode_base64url(user)
        if _is_base64url(pwd):
            pwd = _decode_base64url(pwd)
        return f"http://{user}:{pwd}@{ip}:{port}"
    if len(parts) == 2:
        return f"http://{p}"
    raise Exception(f"unrecognised proxy format: {raw!r}")


# ─── working-proxy log ───────────────────────────────────────────
def _save_working_proxy(proxy: str, user_id: int, card: str):
    if not proxy:
        return
    try:
        existing = set()
        if os.path.exists(WORKING_PROXY_FILE):
            with open(WORKING_PROXY_FILE) as f:
                existing = {ln.strip() for ln in f if ln.strip()}
        if proxy not in existing:
            with open(WORKING_PROXY_FILE, "a") as f:
                f.write(proxy + "\n")
    except Exception:
        pass


# ─── bootstrap on import ─────────────────────────────────────────
load_user_proxies()
load_user_pool()
