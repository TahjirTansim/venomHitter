#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime-composed branding — reads from config, nothing hard-coded."""
from config import BOT_BRAND, KEY_PREFIX, OWNER_NAME, OWNER_USERNAME


def fi(text: str) -> str:
    """Convert ASCII letters to Unicode Sans-Serif Bold Italic."""
    out = []
    for c in text:
        if "A" <= c <= "Z":
            out.append(chr(0x1D63C + ord(c) - 65))
        elif "a" <= c <= "z":
            out.append(chr(0x1D656 + ord(c) - 97))
        else:
            out.append(c)
    return "".join(out)


def dev_line() -> str:
    """Footer line for result cards. Built at runtime from env."""
    if OWNER_USERNAME and OWNER_USERNAME != "your_handle":
        return f'[DEV] -> <a href="https://t.me/{OWNER_USERNAME}">{OWNER_NAME}</a>'
    return f"[DEV] -> {OWNER_NAME}"


def checker_line(uid: int, display_name: str) -> str:
    return f'<b>Checked by</b> -> <a href="tg://user?id={uid}">{display_name}</a>'


def brand_title() -> str:
    return f"<b>{BOT_BRAND}</b>"


def key_example() -> str:
    return f"{KEY_PREFIX}-XXXXXXXXXXXXXXXXXXXX"


SEP  = "━━━━━━━━━━━━━━━━━━━━"
LINE = "─" * 24
