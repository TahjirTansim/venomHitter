#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Telegram UI helpers — colored buttons, raw HTTP send/edit."""
import asyncio
import copy
import json
import threading

import requests
import urllib3

from config import BOT_TOKEN, OWNER_USERNAME
from emojis import BUTTON_CUSTOM_EMOJIS, _clean_btn_text, _btn_icon_id

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ─── button styling ──────────────────────────────────────────────
_BTN_STYLES = ["primary", "success", "danger"]
_style_idx  = 0
_style_lock = threading.Lock()


def _next_style() -> str:
    global _style_idx
    with _style_lock:
        s = _BTN_STYLES[_style_idx % len(_BTN_STYLES)]
        _style_idx += 1
        return s


def _color_kb(rows: list) -> dict:
    colored = []
    for row in rows:
        colored_row = []
        for btn in row:
            b = dict(btn)
            cb       = b.get("callback_data", "")
            has_copy = "copy_text" in b
            has_url  = "url" in b
            if ((cb and cb != "noop") or has_copy or has_url) and "style" not in b:
                b["style"] = _next_style()
            if cb == "noop" and has_copy:
                b.pop("callback_data", None)
            raw_text = b.get("text", "")
            if "icon_custom_emoji_id" not in b:
                icon_id = _btn_icon_id(raw_text)
                if icon_id:
                    b["icon_custom_emoji_id"] = icon_id
            b["text"] = _clean_btn_text(raw_text)
            colored_row.append(b)
        colored.append(colored_row)
    return {"inline_keyboard": colored}


def _strip_styles(markup: dict) -> dict:
    m = copy.deepcopy(markup)
    for row in m.get("inline_keyboard", []):
        for btn in row:
            btn.pop("style", None)
    return m


def _strip_icons(markup: dict) -> dict:
    m = copy.deepcopy(markup)
    for row in m.get("inline_keyboard", []):
        for btn in row:
            btn.pop("icon_custom_emoji_id", None)
    return m


# ─── HTTP layer ──────────────────────────────────────────────────
_http_session = requests.Session()
_http_session.verify = False
_http_adapter = requests.adapters.HTTPAdapter(
    pool_connections=8, pool_maxsize=32, max_retries=1
)
_http_session.mount("https://", _http_adapter)
_http_session.mount("http://", _http_adapter)


def _raw_post(url, payload):
    p = dict(payload)
    if "reply_markup" in p and isinstance(p["reply_markup"], dict):
        p["reply_markup"] = json.dumps(p["reply_markup"], ensure_ascii=False)
    try:
        return _http_session.post(url, json=p, timeout=8).json()
    except Exception:
        return {"ok": False}


async def raw_send(chat_id, text, kb_rows, parse_mode="HTML", reply_to=None):
    kb = _color_kb(kb_rows)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": kb,
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    url = f"{TG_API}/sendMessage"
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp["result"]["message_id"]
    payload["reply_markup"] = _strip_icons(kb)
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp["result"]["message_id"]
    payload["reply_markup"] = _strip_styles(_strip_icons(kb))
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp["result"]["message_id"]
    return None


async def raw_edit(chat_id, message_id, text, kb_rows, parse_mode="HTML"):
    kb = _color_kb(kb_rows)
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": kb,
        "disable_web_page_preview": True,
    }
    url = f"{TG_API}/editMessageText"
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp
    payload["reply_markup"] = _strip_icons(kb)
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp
    payload["reply_markup"] = _strip_styles(_strip_icons(kb))
    return await asyncio.to_thread(_raw_post, url, payload)


async def nav_edit(chat_id, message_id, text, kb_rows, parse_mode="HTML"):
    kb = _color_kb(kb_rows)
    cap_payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "caption": text,
        "parse_mode": parse_mode,
        "reply_markup": kb,
    }
    resp = await asyncio.to_thread(
        _raw_post, f"{TG_API}/editMessageCaption", cap_payload
    )
    if resp.get("ok"):
        return resp

    txt_url = f"{TG_API}/editMessageText"
    txt_payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": kb,
        "disable_web_page_preview": True,
    }
    resp = await asyncio.to_thread(_raw_post, txt_url, txt_payload)
    if resp.get("ok"):
        return resp
    txt_payload["reply_markup"] = _strip_icons(kb)
    resp = await asyncio.to_thread(_raw_post, txt_url, txt_payload)
    if resp.get("ok"):
        return resp
    txt_payload["reply_markup"] = _strip_styles(_strip_icons(kb))
    return await asyncio.to_thread(_raw_post, txt_url, txt_payload)


# ─── button row builders ─────────────────────────────────────────
def rows_main():
    return [
        [{"text": "🏧  Gates", "callback_data": "gates"}],
        [{"text": "💙  Contact", "url": f"https://t.me/{OWNER_USERNAME}"},
         {"text": "❌  Close",   "callback_data": "close"}],
    ]


def rows_gates():
    return [
        [{"text": "®️  Manage Proxy",  "callback_data": "manage_proxy"}],
        [{"text": "💰  Amount Filter", "callback_data": "amount_select"}],
        [{"text": "↪️  Back",           "callback_data": "back_start"}],
    ]


def rows_admin():
    return [
        [{"text": "👑  Users",       "callback_data": "admin_users"},
         {"text": "🌐  Sites",       "callback_data": "admin_sites"}],
        [{"text": "📡  Broadcast",   "callback_data": "admin_broadcast_info"},
         {"text": "⚙️  Proxy Pool",  "callback_data": "admin_proxy_pool"}],
        [{"text": "🔑  Key Manager", "callback_data": "admin_keys"},
         {"text": "📊  User Status", "callback_data": "admin_user_status"}],
        [{"text": "  Mandatory Sub  ", "callback_data": "admin_mandatory_sub"}],
        [{"text": "❌  Close",       "callback_data": "close"}],
    ]


def rows_stop():
    return [
        [{"text": "✋  Stop Check", "callback_data": "stop_mass"}],
    ]


def rows_admin_users():
    return [
        [{"text": "📋  List Users",  "callback_data": "admin_list_users"}],
        [{"text": "✅  Auth User",   "callback_data": "admin_add_user_info"},
         {"text": "🔥  Deauth User", "callback_data": "admin_rm_user_info"}],
        [{"text": "↪️  Back",         "callback_data": "admin_panel"}],
    ]


def rows_admin_sites():
    return [
        [{"text": "📋  List Sites",   "callback_data": "admin_list_sites_cb"}],
        [{"text": "✅  Add Site",     "callback_data": "admin_add_site_info"},
         {"text": "🔥  Remove Site",  "callback_data": "admin_rm_site_info"}],
        [{"text": "↪️  Back",         "callback_data": "admin_panel"}],
    ]


def rows_admin_proxy_pool():
    return [
        [{"text": "📋  View Pool",   "callback_data": "admin_list_proxy_cb"}],
        [{"text": "✅  Add Proxies", "callback_data": "admin_add_proxy_info"},
         {"text": "🔥  Clear Pool",  "callback_data": "admin_clear_proxy_cb"}],
        [{"text": "↪️  Back",        "callback_data": "admin_panel"}],
    ]


def rows_admin_keys():
    return [
        [{"text": "🔑  Generate Keys", "callback_data": "admin_genkeys_info"}],
        [{"text": "📋  List Keys",     "callback_data": "admin_list_keys_cb"}],
        [{"text": "🔥  Delete Key",    "callback_data": "admin_delkey_info"}],
        [{"text": "↪️  Back",          "callback_data": "admin_panel"}],
    ]


def rows_amount_select(current: str):
    tiers = [("1", "$1"), ("5", "$5"), ("10", "$10"), ("20", "$20"), ("any", "Any")]
    row1 = [{"text": f"{'✅ ' if current == t else ''}{label}",
             "callback_data": f"amount_tier_{t}"} for t, label in tiers[:3]]
    row2 = [{"text": f"{'✅ ' if current == t else ''}{label}",
             "callback_data": f"amount_tier_{t}"} for t, label in tiers[3:]]
    return [row1, row2, [{"text": "↪️  Back", "callback_data": "gates"}]]


def rows_proxy(pool_on: bool = True):
    pool_label = "✅  Use Proxy Pool (ON)" if pool_on else "🚀  Use Proxy Pool (OFF)"
    return [
        [{"text": pool_label, "callback_data": "toggle_pool"}],
        [{"text": "✅  Test Proxy",   "callback_data": "test_proxy_btn"},
         {"text": "✋  Remove Proxy", "callback_data": "remove_proxy_btn"}],
        [{"text": "↪️  Back",          "callback_data": "gates"}],
  ]
