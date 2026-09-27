#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""User-facing command handlers."""
import asyncio
import json
import os
import random
from datetime import datetime

import aiofiles

from config import (
    AMOUNT_TIERS,
    BOT_BRAND,
    OWNER_USERNAME,
    SESSION_NAME,
    TIER_LIMITS,
)
from storage import (
    _save_working_proxy,
    _tokenise,
    _validate_proxy_fmt,
    add_user_proxies_bulk,
    clear_user_proxies,
    get_user_amount_tier,
    get_user_proxy,
    get_user_proxy_list,
    load_proxies,
    load_sites,
    load_sites_for_user,
    record_check,
    record_log,
    remove_user_proxy_entry,
    set_user_amount_tier,
    set_user_proxy,
    tier_range_label,
    user_pool_enabled,
)
from keys import (
    all_keys,
    all_user_access,
    get_user_limit,
    get_user_tier,
    is_access_valid,
    redeem_key,
    time_remaining,
)
from emojis import pe
from branding import SEP, checker_line, dev_line, fi
from ui import raw_send, raw_edit
from orchestrator import check_card_with_retry, test_site
from async_engine import CheckStatus


# ─── helpers ─────────────────────────────────────────────────────
def _extract_cc(text):
    import re
    matches = re.findall(r"(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})", text)
    out = []
    for card, month, year, cvv in matches:
        if len(year) == 2:
            year = "20" + year
        out.append(f"{card}|{month}|{year}|{cvv}")
    return out


async def get_display_name(bot, uid):
    try:
        entity = await bot.get_entity(uid)
        name = (entity.first_name or "").strip()
        if getattr(entity, "last_name", None):
            name = f"{name} {entity.last_name}".strip()
        return name or f"User {uid}"
    except Exception:
        return f"User {uid}"


async def get_display_info(bot, uid):
    try:
        entity = await bot.get_entity(uid)
        name = (entity.first_name or "").strip()
        if getattr(entity, "last_name", None):
            name = f"{name} {entity.last_name}".strip()
        username = getattr(entity, "username", "") or ""
        return name or f"User {uid}", username
    except Exception:
        return f"User {uid}", ""


async def get_bin_info(card_number):
    import aiohttp
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f"https://bins.antipublic.cc/bins/{card_number[:6]}") as r:
                if r.status != 200:
                    return "-", "-", "-", "-", "-", ""
                d = await r.json()
                return (d.get("brand", "-"), d.get("type", "-"), d.get("level", "-"),
                        d.get("bank", "-"), d.get("country_name", "-"),
                        d.get("country_flag", ""))
    except Exception:
        return "-", "-", "-", "-", "-", ""


def build_result_card(result, bin_info, uid, cname):
    brand, btype, level, bank, country, flag = bin_info

    if result["status"] == "Charged":
        header = f"🔥 {fi('CHARGED')} 🔥"
        status_label = f"{fi('Charged')} 🔥"
        icon = "💸"
    elif result["status"] == "Approved":
        header = f"✅ {fi('APPROVED')} ✅"
        status_label = f"{fi('Approved')} ✅"
        icon = "💸"
    elif result["status"] == "OTP":
        header = f"🔔 {fi('OTP REQUIRED')} 🔔"
        status_label = f"{fi('OTP Required')} 🔔"
        icon = '<tg-emoji emoji-id="5810108367913360444">👩‍💻</tg-emoji>'
    else:
        header = f"❌ {fi('DECLINED')} ❌"
        status_label = f"{fi('Declined')} ❌"
        icon = '<tg-emoji emoji-id="5810108367913360444">👩‍💻</tg-emoji>'

    gate = result.get("gateway", "Shopify Payments")
    price_val = result.get("price", "-")
    price_str = f"${price_val}" if price_val not in ("-", "", None) else "—"

    receipt_url = result.get("receipt_url", "")
    receipt_line = (
        f"\n🧾 <b>{fi('Receipt')}:</b> <a href=\"{receipt_url}\">View Order Receipt →</a>"
        if result["status"] == "Charged" and receipt_url else ""
    )

    return pe(
        f"<b>{header}</b>\n"
        f"<b>{SEP}</b>\n"
        f"🃏 <b>{fi('Card')}:</b> <tg-spoiler><code>{result['card']}</code></tg-spoiler>\n"
        f"{icon} <b>{fi('Status')}:</b> {status_label}\n"
        f"🖥 <b>{fi('Response')}:</b> <i>{result['message']}</i>\n"
        f"🌐 <b>{fi('Gateway')}:</b> <i>{gate}</i>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"ℹ️ <b>{fi('Info')}</b> ↬ <i>{brand} | {btype} {level}</i>\n"
        f"🏦 <b>{fi('Bank')}</b> ↬ <i>{bank}</i>\n"
        f"🌍 <b>{fi('Country')}</b> ↬ <i>{country} {flag}</i>\n"
        f"💵 <b>{fi('Price')}</b> ↬ <b><i>{price_str}</i></b>"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"{checker_line(uid, cname)}\n"
        f"{dev_line()}"
        f"{receipt_line}"
    )


def get_proxies_for_user(uid, is_admin_fn):
    personal    = get_user_proxy_list(uid)
    global_pool = load_proxies()
    pool_on     = user_pool_enabled.get(uid, True)
    if is_admin_fn(uid):
        if personal:
            return (personal + global_pool) if pool_on else personal
        return global_pool if pool_on else []
    return personal


# ─── /start ──────────────────────────────────────────────────────
async def start_handler(event, bot, is_admin_fn, enforce_subscription):
    uid      = event.sender_id
    chat_id  = event.chat_id
    in_group = (chat_id != uid)

    if not in_group:
        try:
            from telethon import Button
            rm_msg = await bot.send_message(uid, "\u200b", buttons=Button.clear())
            await asyncio.sleep(0.3)
            await bot.delete_messages(uid, rm_msg.id)
        except Exception:
            pass

    if not await enforce_subscription(event):
        return

    try:
        sender    = await bot.get_entity(uid)
        username  = f"@{sender.username}" if sender.username else f"ID:{uid}"
        firstname = sender.first_name or "User"
    except Exception:
        username  = f"ID:{uid}"
        firstname = "User"

    tier = get_user_tier(uid, is_admin_fn)
    trem = time_remaining(uid)

    if is_admin_fn(uid):
        status_line = "👑 Admin"
    elif tier == "auth":
        status_line = f"✅ Auth — {trem} left" if trem else "⚠️ Auth Expired"
    elif tier == "grant":
        status_line = f"💎 Grant — {trem} left" if trem else "⚠️ Grant Expired"
    elif tier == "key":
        status_line = f"🔑 Key — {trem} left" if trem else "⚠️ Key Expired"
    elif tier:
        status_line = "⭐ Premium"
    else:
        status_line = "🚫 No Access"

    lim = get_user_limit(uid, is_admin_fn)

    caption = pe(
        f"<b>{BOT_BRAND}</b>\n"
        f"<b>{SEP}</b>\n"
        f"👤 <b>{fi('User')}:</b> {firstname}\n"
        f"🔗 <b>{fi('Handle')}:</b> {username}\n"
        f"🆔 <b>{fi('ID')}:</b> <code>{uid}</code>\n"
        f"<b>{SEP}</b>\n"
        f"⚡ <b>{fi('Status')}:</b> {status_line}\n"
        f"📋 <b>{fi('Limit')}:</b> {lim if lim else 'N/A'} cards/file\n"
        f"<b>{SEP}</b>\n"
        f"🃏 <b>{fi('Single')}:</b> <code>/sh card|mm|yy|cvv</code>\n"
        f"🔥 <b>{fi('Mass')}:</b> Reply to .txt ➜ <code>/msh</code>\n"
        f"<b>{SEP}</b>\n"
        f"{dev_line()}"
    )

    from ui import rows_main
    kb_rows = rows_main()
    if is_admin_fn(uid):
        kb_rows = [
            [{"text": "🏧  Gates",       "callback_data": "gates"},
             {"text": "👑  Admin Panel", "callback_data": "admin_panel"}],
            [{"text": "💙  Contact", "url": f"https://t.me/{OWNER_USERNAME}"},
             {"text": "❌  Close",   "callback_data": "close"}],
        ]
    await raw_send(chat_id, caption, kb_rows)


# ─── /sh — single card check ─────────────────────────────────────
async def sh_handler(event, bot, is_premium_fn, enforce_subscription):
    uid = event.sender_id
    if not await enforce_subscription(event):
        return
    if not is_premium_fn(uid):
        await event.reply(pe("❌ <b>Access Denied.</b> Use /redeem to activate a key."), parse_mode="html")
        return

    card_raw = event.message.text.split(None, 1)[1].strip()
    cards    = _extract_cc(card_raw)
    if not cards:
        await event.reply(pe("❌ <b>Invalid card format.</b>\n\nUse: <code>/sh 4111111111111111|12|2026|123</code>"), parse_mode="html")
        return

    card    = cards[0]
    sites, _eff_tier = load_sites_for_user(uid)
    proxies = get_proxies_for_user(uid, is_admin_fn) if False else load_proxies()
    proxies = get_proxies_for_user(uid, lambda _: False) or load_proxies()

    if not sites:
        await event.reply(pe("❌ <b>No sites configured.</b> Contact admin."), parse_mode="html")
        return
    if not proxies:
        await event.reply(pe("❌ <b>No proxy set!</b>\n\nSet your proxy:\n<code>/setproxy ip:port</code>"), parse_mode="html")
        return

    _tier = get_user_amount_tier(uid)
    _filter_line = f"💰 <b>Filter:</b> {tier_range_label(_eff_tier)}\n" if _eff_tier != "any" else ""

    smsg = await event.reply(pe(
        f"<b>⚡ {fi('Checking')}...</b>\n"
        f"<b>{SEP}</b>\n"
        f"🃏 <code>{card}</code>\n"
        f"{_filter_line}"
    ), parse_mode="html")

    try:
        result, bin_info, (cname, cusername) = await asyncio.gather(
            check_card_with_retry(card, sites, proxies, max_retries=1, max_proxy_tries=2),
            get_bin_info(card.split("|")[0]),
            get_display_info(bot, uid),
        )
        resp = build_result_card(result, bin_info, uid, cname)
        await smsg.edit(resp, parse_mode="html")
        record_check(uid, cname, result.get("status", "Dead"), username=cusername)
        record_log(uid, cname, cusername,
                   result.get("card", card),
                   result.get("status", "Dead"),
                   result.get("message", ""),
                   result.get("site", ""),
                   result.get("gateway", "Shopify Payments"),
                   result.get("price", "-"))
        if result.get("status") == "Charged":
            try:
                await bot.pin_message(uid, smsg.id, notify=True)
            except Exception:
                pass
    except Exception as e:
        await smsg.edit(pe(f"❌ Error: {e}"), parse_mode="html")
      # ─── /ran — random site check ────────────────────────────────────
async def ran_handler(event, bot, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return

    all_sites = load_sites()
    proxies   = get_proxies_for_user(uid, lambda _: False) or load_proxies()

    if not all_sites:
        await event.reply(pe("❌ <b>No sites configured.</b>"), parse_mode="html")
        return
    if not proxies:
        await event.reply(pe("❌ <b>No proxy set!</b>\n\n<code>/setproxy ip:port</code>"), parse_mode="html")
        return

    text_after = event.message.text[4:].strip()
    if text_after:
        cards = _extract_cc(text_after)
        if not cards:
            await event.reply(pe(
                "❌ <b>Invalid card.</b>\n\n"
                "<b>Single:</b> <code>/ran 4111111111111111|12|2026|123</code>\n"
                "<b>Mass:</b> Reply to a .txt with <code>/ran</code>"
            ), parse_mode="html")
            return

        card     = cards[0]
        ran_site = random.choice(all_sites)

        smsg = await event.reply(pe(
            f"<b>🎲 {fi('Random Check')}...</b>\n"
            f"<b>{SEP}</b>\n"
            f"🃏 <code>{card}</code>\n"
            f"🌐 <b>Site:</b> {len(all_sites)} in pool (random)"
        ), parse_mode="html")

        try:
            result, bin_info, (cname, cusername) = await asyncio.gather(
                check_card_with_retry(card, [ran_site], proxies, max_retries=1, max_proxy_tries=2),
                get_bin_info(card.split("|")[0]),
                get_display_info(bot, uid),
            )
            resp = build_result_card(result, bin_info, uid, cname)
            await smsg.edit(resp, parse_mode="html")
            record_check(uid, cname, result.get("status", "Dead"), username=cusername)
            record_log(uid, cname, cusername,
                       result.get("card", card),
                       result.get("status", "Dead"),
                       result.get("message", ""),
                       result.get("site", ""),
                       result.get("gateway", "Shopify Payments"),
                       result.get("price", "-"))
            if result.get("status") == "Charged":
                try:
                    await bot.pin_message(uid, smsg.id, notify=True)
                except Exception:
                    pass
        except Exception as e:
            await smsg.edit(pe(f"❌ Error: {e}"), parse_mode="html")
        return

    # mass mode — reply to a .txt file
    if not event.reply_to_msg_id:
        await event.reply(pe(
            f"<b>🎲 /ran — Random Site Checker</b>\n"
            f"<b>{SEP}</b>\n"
            f"Each card is tested on a <b>random site</b> from all "
            f"{len(all_sites)} in the pool.\n\n"
            f"<b>Single:</b> <code>/ran card|mm|yy|cvv</code>\n"
            f"<b>Mass:</b> Reply to a .txt with <code>/ran</code>"
        ), parse_mode="html")
        return

    reply = await event.get_reply_message()
    if not reply or not reply.file:
        await event.reply(pe("❌ Reply to a <code>.txt</code> file."), parse_mode="html")
        return

    _fname = reply.file.name or ""
    _fmime = getattr(reply.file, "mime_type", "") or ""
    if not (_fname.lower().endswith(".txt") or "text/plain" in _fmime):
        await event.reply(pe("❌ Reply to a <code>.txt</code> file."), parse_mode="html")
        return

    fp = await reply.download_media()
    async with aiofiles.open(fp, "r", encoding="utf-8", errors="ignore") as f:
        content = await f.read()
    try:
        os.remove(fp)
    except Exception:
        pass

    cards = _extract_cc(content)
    if not cards:
        await event.reply(pe("❌ No valid cards found."), parse_mode="html")
        return

    limit = get_user_limit(uid, lambda _: False)
    if len(cards) > limit:
        cards = cards[:limit]
        await event.reply(pe(f"⚠️ <b>File trimmed to {limit} cards</b> (your plan limit)."), parse_mode="html")

    # TODO: hook into run_mass_check from handlers_admin / mass module
    await event.reply(pe(f"⚡ <b>Queued {len(cards)} cards for random-site check.</b>"), parse_mode="html")


# ─── /setproxy ────────────────────────────────────────────────────
async def setproxy_handler(event, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return

    args = event.message.text.split(None, 1)
    if len(args) < 2 or not args[1].strip():
        curr = get_user_proxy(uid) or "Not set"
        await event.reply(pe(
            f"<b>⚙️ Your Proxy</b>\n<b>{SEP}</b>\n"
            f"🔌 <b>Current:</b> <code>{curr}</code>\n\n"
            f"👩‍💻 <b>To Set:</b>\n"
            f"<code>/setproxy ip:port</code>\n"
            f"<code>/setproxy ip:port:user:pass</code>\n"
            f"<code>/setproxy socks5://ip:port</code>\n\n"
            f"📁 <b>Upload file:</b> Reply to a <code>.txt</code> with <code>/uploadproxy</code>\n"
            f"To clear: <code>/clearuserproxy</code>"
        ), parse_mode="html")
        return

    proxy = args[1].strip()
    set_user_proxy(uid, proxy)
    await event.reply(pe(f"✅ <b>Proxy Set!</b>\n🔌 <code>{proxy}</code>"), parse_mode="html")


# ─── /clearuserproxy ─────────────────────────────────────────────
async def clearuserproxy_handler(event, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return
    count = len(get_user_proxy_list(uid))
    clear_user_proxies(uid)
    await event.reply(pe(
        f"✅ <b>Your proxy pool cleared!</b>\n"
        f"🗑 Removed <b>{count}</b> {'proxy' if count == 1 else 'proxies'}."
    ), parse_mode="html")


# ─── /myproxies ───────────────────────────────────────────────────
async def myproxies_handler(event, bot, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return

    parts = event.message.text.strip().split(None, 2)
    sub   = parts[1].lower() if len(parts) > 1 else None

    if sub == "rm" and len(parts) > 2:
        target = parts[2].strip()
        removed = remove_user_proxy_entry(uid, target)
        total_now = len(get_user_proxy_list(uid))
        if removed:
            import html as _h
            await event.reply(pe(
                f"✅ <b>Proxy removed!</b>\n<code>{_h.escape(target)}</code>\n"
                f"🔌 <b>Pool now:</b> {total_now} proxies"
            ), parse_mode="html")
        else:
            import html as _h
            await event.reply(pe(f"❌ Not found:\n<code>{_h.escape(target)}</code>"), parse_mode="html")
        return

    if sub == "clear":
        count = len(get_user_proxy_list(uid))
        clear_user_proxies(uid)
        await event.reply(pe(f"🗑 <b>Cleared {count} {'proxy' if count == 1 else 'proxies'}.</b>"), parse_mode="html")
        return

    lst = get_user_proxy_list(uid)
    if not lst:
        await event.reply(pe(
            f"❌ <b>Your proxy pool is empty.</b>\n\n"
            f"Add proxies:\n<code>/addproxy ip:port</code>\n"
            f"Or reply to a <code>.txt</code> with <code>/addproxy</code>"
        ), parse_mode="html")
        return

    import html as _h
    if len(lst) <= 20:
        lines = "\n".join(f"{i+1}. <code>{_h.escape(p)}</code>" for i, p in enumerate(lst))
        await event.reply(pe(
            f"🔌 <b>Your Proxy Pool ({len(lst)}):</b>\n"
            f"<b>{SEP}</b>\n{lines}\n<b>{SEP}</b>\n"
            f"<code>/myproxies rm ip:port</code> — remove one\n"
            f"<code>/myproxies clear</code> — wipe all"
        ), parse_mode="html")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"my_proxies_{uid}_{ts}.txt"
        async with aiofiles.open(fn, "w") as f:
            for i, p in enumerate(lst, 1):
                await f.write(f"{i}. {p}\n")
        await event.reply(pe(f"🔌 <b>Your Proxy Pool ({len(lst)} proxies)</b>"),
                          file=fn, parse_mode="html")
        try:
            os.remove(fn)
        except Exception:
            pass


# ─── /addproxy ────────────────────────────────────────────────────
async def addproxy_handler(event, is_admin_fn, is_premium_fn):
    uid = event.sender_id
    if not (is_admin_fn(uid) or is_premium_fn(uid)):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return

    # reply to .txt mode
    reply = await event.get_reply_message()
    doc_msg = None
    if reply and reply.document:
        doc_msg = reply
    elif event.message.document:
        doc_msg = event.message

    if doc_msg:
        if is_admin_fn(uid):
            await event.reply(pe("✅ <b>Admin mode: file will be merged into the global pool. Use /uploadproxy for that.</b>"), parse_mode="html")
            return
        buf = await doc_msg.download_media(bytes)
        tokens = _tokenise(buf.decode("utf-8", errors="ignore"))
        result = add_user_proxies_bulk(uid, tokens)
        total_now = len(get_user_proxy_list(uid))
        await event.reply(pe(
            f"✅ <b>Added to your pool!</b>\n"
            f"<b>{SEP}</b>\n"
            f"➕ <b>Added:</b> {result['added']}\n"
            f"♻️ <b>Duplicates:</b> {result['duplicates']}\n"
            f"❌ <b>Invalid:</b> {result['invalid']}\n"
            f"<b>{SEP}</b>\n"
            f"🔌 <b>Pool now:</b> {total_now}"
        ), parse_mode="html")
        return

    content = event.message.text[len("/addproxy"):].strip()
    if not content:
        await event.reply(pe(
            f"<b>➕ Add Proxy</b>\n<b>{SEP}</b>\n"
            f"<code>/addproxy ip:port</code>\n"
            f"<code>/addproxy ip:port:user:pass</code>\n"
            f"<code>/addproxy socks5://ip:port</code>\n\n"
            f"📁 Or reply to a <code>.txt</code> file"
        ), parse_mode="html")
        return

    tokens = _tokenise(content)
    result = add_user_proxies_bulk(uid, tokens)
    total_now = len(get_user_proxy_list(uid))
    if result["added"] == 0:
        await event.reply(pe("⚠️ <b>Nothing added.</b>"), parse_mode="html")
        return
    await event.reply(pe(
        f"✅ <b>Added to your pool!</b>\n"
        f"➕ {result['added']} · ♻️ {result['duplicates']} dup · ❌ {result['invalid']} invalid\n"
        f"🔌 <b>Pool now:</b> {total_now}"
    ), parse_mode="html")


# ─── /uploadproxy ─────────────────────────────────────────────────
async def uploadproxy_handler(event, is_admin_fn, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return

    doc_msg = None
    reply = await event.get_reply_message()
    if reply and reply.document:
        doc_msg = reply
    elif event.message.document:
        doc_msg = event.message

    if not doc_msg:
        await event.reply(pe(
            f"<b>📁 Upload Proxy File</b>\n<b>{SEP}</b>\n"
            f"Send a <code>.txt</code> file (one proxy per line), then reply with <code>/uploadproxy</code>."
        ), parse_mode="html")
        return

    buf = await doc_msg.download_media(bytes)
    tokens = _tokenise(buf.decode("utf-8", errors="ignore"))
    result = add_user_proxies_bulk(uid, tokens)
    total_now = len(get_user_proxy_list(uid))
    await event.reply(pe(
        f"✅ <b>Proxy pool updated!</b>\n"
        f"➕ {result['added']} · ♻️ {result['duplicates']} · ❌ {result['invalid']}\n"
        f"🔌 <b>Pool now:</b> {total_now}"
    ), parse_mode="html")


# ─── /chkproxy ─────────────────────────────────────────────────────
async def chkproxy_handler(event, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return
    proxy = event.message.text.split(" ", 1)[1].strip()
    smsg = await event.reply(pe(f"⚡ Testing <code>{proxy}</code>..."), parse_mode="html")

    from storage import normalize_proxy
    try:
        p_url = normalize_proxy(proxy)
    except Exception as e:
        await smsg.edit(pe(f"❌ Invalid proxy: {e}"), parse_mode="html")
        return

    import aiohttp
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get("https://api.ipify.org", proxy=p_url) as r:
                if r.status == 200:
                    ip = (await r.text()).strip()
                    await smsg.edit(pe(f"✅ <b>Proxy ALIVE</b>\n🌐 IP: <code>{ip}</code>"), parse_mode="html")
                    return
    except Exception:
        pass
    await smsg.edit(pe(f"❌ <b>Proxy DEAD</b>\n<code>{proxy}</code>"), parse_mode="html")


# ─── /setamount ───────────────────────────────────────────────────
async def setamount_handler(event, is_admin_fn, is_premium_fn):
    uid = event.sender_id
    if not (is_admin_fn(uid) or is_premium_fn(uid)):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return

    parts = event.message.text.strip().split()
    if len(parts) == 1:
        cur = get_user_amount_tier(uid)
        label = AMOUNT_TIERS.get(cur, ("Any",))[0]
        await event.reply(pe(
            f"<b>💰 Amount Filter</b>\n<b>{SEP}</b>\n"
            f"Current: <b>{label}</b>\n\n"
            f"<code>/setamount 1</code>  <code>/setamount 5</code>  "
            f"<code>/setamount 10</code>  <code>/setamount 20</code>  "
            f"<code>/setamount any</code>"
        ), parse_mode="html")
        return

    tier = parts[1].lower()
    if tier not in AMOUNT_TIERS:
        await event.reply(pe("❌ <b>Invalid tier.</b> Valid: 1, 5, 10, 20, any"), parse_mode="html")
        return
    set_user_amount_tier(uid, tier)
    await event.reply(pe(f"✅ <b>Amount filter → {AMOUNT_TIERS[tier][0]}</b>"), parse_mode="html")


# ─── /myplan ──────────────────────────────────────────────────────
async def myplan_handler(event, is_admin_fn):
    uid  = event.sender_id
    tier = get_user_tier(uid, is_admin_fn)
    trem = time_remaining(uid)
    lim  = get_user_limit(uid, is_admin_fn)

    if is_admin_fn(uid):
        await event.reply(pe(f"<b>👑 Admin</b>\n<b>{SEP}</b>\n⭐ Unlimited access"), parse_mode="html")
        return
    if not tier:
        await event.reply(pe(f"❌ <b>No Active Plan</b>\n\nRedeem a key: <code>/redeem KEY-XXXX</code>"), parse_mode="html")
        return

    acc = all_user_access().get(uid, {})
    exp = acc.get("expires_at", "")[:10]
    await event.reply(pe(
        f"<b>📋 My Plan</b>\n<b>{SEP}</b>\n"
        f"💎 <b>Tier:</b> {tier.capitalize()}\n"
        f"📅 <b>Expires:</b> {exp}\n"
        f"⏳ <b>Remaining:</b> {trem or 'Expired'}\n"
        f"📋 <b>Limit:</b> {lim} cards/file\n"
        f"<b>{SEP}</b>\n{dev_line()}"
    ), parse_mode="html")


# ─── /redeem ──────────────────────────────────────────────────────
async def redeem_handler(event):
    uid   = event.sender_id
    parts = event.message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await event.reply(pe("❌ Usage: <code>/redeem YOUR-KEY</code>"), parse_mode="html")
        return

    res = redeem_key(parts[1].strip(), uid)
    if not res["ok"]:
        msg = "❌ <b>Invalid key!</b>" if res["reason"] == "invalid" else "❌ <b>Key already redeemed!</b>"
        await event.reply(pe(msg), parse_mode="html")
        return

    trem = time_remaining(uid)
    await event.reply(pe(
        f"✅ <b>Key Redeemed!</b>\n<b>{SEP}</b>\n"
        f"💎 <b>Plan:</b> {res['plan_days']} day(s)\n"
        f"⏳ <b>Expires in:</b> {trem}\n"
        f"<b>{SEP}</b>\n{dev_line()}"
    ), parse_mode="html")


# ─── /profile ─────────────────────────────────────────────────────
async def profile_handler(event, bot, is_admin_fn, is_premium_fn):
    uid = event.sender_id
    if not (is_admin_fn(uid) or is_premium_fn(uid)):
        await event.reply(pe("❌ <b>Access required.</b>"), parse_mode="html")
        return

    try:
        sender = await event.get_sender()
        uname  = f"@{sender.username}" if sender.username else f"user_{uid}"
        fname  = sender.first_name or "User"
    except Exception:
        uname, fname = f"user_{uid}", "User"

    import html as _h
    try:
        with open("user_stats.json") as _f:
            ustats = json.load(_f)
        u = ustats.get(str(uid), {})
        total_checks = u.get("total_checks", 0)
        hits         = u.get("charged", 0) + u.get("approved", 0)
        joined       = u.get("first_seen", "-")[:10] if isinstance(u.get("first_seen"), str) else "-"
    except Exception:
        total_checks, hits, joined = 0, 0, "-"

    sites_cnt   = len(load_sites())
    proxies_cnt = len(load_proxies())
    plan = "Admin" if is_admin_fn(uid) else "Premium"

    text = (
        f"<b>{'━' * 22}</b>\n"
        f"👤 <b>Profile</b>\n"
        f"<b>{'━' * 22}</b>\n\n"
        f"<b>ID        »</b>  <code>{uid}</code>\n"
        f"<b>Name      »</b>  {_h.escape(fname)}\n"
        f"<b>Username  »</b>  {_h.escape(uname)}\n"
        f"<b>Plan      »</b>  {plan}\n"
        f"<b>Joined    »</b>  {joined}\n"
        f"<b>Checks    »</b>  {total_checks}\n"
        f"<b>Hits      »</b>  {hits}\n"
        f"<b>Sites     »</b>  {sites_cnt}\n"
        f"<b>Proxies   »</b>  {proxies_cnt}\n\n"
        f"<b>{'━' * 22}</b>"
    )
    await event.reply(pe(text), parse_mode="html")


# ─── /mysites ─────────────────────────────────────────────────────
async def mysites_handler(event, bot, is_admin_fn, is_premium_fn):
    uid = event.sender_id
    if not (is_admin_fn(uid) or is_premium_fn(uid)):
        await event.reply(pe("❌ <b>Access required.</b>"), parse_mode="html")
        return

    sites = load_sites()
    if not sites:
        await event.reply(pe("❌ <b>No sites saved.</b>"), parse_mode="html")
        return

    ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"sites_{uid}_{ts}.txt"
    try:
        async with aiofiles.open(fname, "w") as f:
            await f.write(f"SITES ({len(sites)})\n")
            await f.write("=" * 60 + "\n\n")
            for i, s in enumerate(sites, 1):
                await f.write(f"{i:>3}. {s}\n")
        await bot.send_file(
            uid, fname,
            caption=pe(f"🌐 <b>Your Sites ({len(sites)})</b>"),
            parse_mode="html"
        )
    except Exception as e:
        await event.reply(pe(f"❌ Error: <code>{e}</code>"), parse_mode="html")
    finally:
        try:
            os.remove(fname)
        except Exception:
            pass


# ─── /mcancel ─────────────────────────────────────────────────────
async def mcancel_handler(event, active_sessions):
    uid = event.sender_id
    canceled = False
    for k in list(active_sessions):
        if k.startswith(f"{uid}_"):
            del active_sessions[k]
            canceled = True
    await event.reply(
        pe("✅ <b>Mass check cancelled.</b>" if canceled else "❌ <b>No active mass check.</b>"),
        parse_mode="html"
  )
