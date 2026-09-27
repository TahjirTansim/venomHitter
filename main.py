#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Speedy Hitter — bot entry point. Registers handlers and starts Telethon."""
import asyncio
import os
import time

from telethon import TelegramClient, events, Button

import config
from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    DEFAULT_ADMIN_IDS,
    SESSION_NAME,
    OWNER_USERNAME,
)
from storage import load_proxies, load_sites
from keys import (
    all_user_access,
    get_user_limit,
    is_access_valid,
    time_remaining,
)
from emojis import pe
from branding import SEP, dev_line, fi
from ui import raw_send, raw_edit, rows_stop
from handlers_user import (
    start_handler,
    sh_handler,
    ran_handler,
    setproxy_handler,
    clearuserproxy_handler,
    myproxies_handler,
    addproxy_handler,
    uploadproxy_handler,
    chkproxy_handler,
    setamount_handler,
    myplan_handler,
    redeem_handler,
    profile_handler,
    mysites_handler,
    mcancel_handler,
)
from handlers_admin import (
    admin_panel_handler,
    genkeys_handler,
    listkeys_handler,
    delkey_handler,
    authuser_handler,
    deauthuser_handler,
    userstatus_handler,
    addpremium_handler,
    rmpremium_handler,
    listpremium_handler,
    setadmin_handler,
    addsite_handler,
    rmsite_handler,
    listsites_handler,
    site_health_handler,
    tagsite_handler,
    getsites_handler,
    stats_handler,
    broadcast_handler,
    testcards_handler,
    addsocks_handler,
    addhttp_handler,
    rmproxy_handler,
    clearproxy_handler,
    getproxy_handler,
    proxy_health_handler,
    getworkingproxy_handler,
    clearworkingproxy_handler,
    getuserproxy_handler,
    addsub_handler,
    addsub_forward_handler,
    addsub_url_handler,
    cancel_handler,
    rmsub_handler,
    listsubs_handler,
    run_mass_check,
)
from callbacks import (
    cb_gates,
    cb_amount_select,
    cb_amount_tier,
    cb_manage_proxy,
    cb_toggle_pool,
    cb_test_proxy,
    cb_remove_proxy,
    cb_back_start,
    cb_close,
    cb_admin_panel,
    cb_admin_users,
    cb_admin_sites,
    cb_admin_proxy_pool,
    cb_admin_keys,
    cb_admin_user_status,
    cb_admin_broadcast_info,
    cb_admin_list_users,
    cb_admin_list_sites,
    cb_admin_list_proxy,
    cb_admin_genkeys_info,
    cb_admin_list_keys,
    cb_admin_delkey_info,
    cb_admin_add_user_info,
    cb_admin_rm_user_info,
    cb_admin_add_site_info,
    cb_admin_rm_site_info,
    cb_admin_add_proxy_info,
    cb_admin_clear_proxy,
    cb_admin_mandatory_sub,
    cb_addsub_start,
    cb_rmsub_inline,
    cb_stop_mass,
)


# ─── admin ID management ─────────────────────────────────────────
_ADMIN_FILE = os.path.join(os.path.dirname(__file__), "admin.json")


def load_admin_ids():
    try:
        with open(_ADMIN_FILE) as f:
            data = __import__("json").load(f)
            ids  = data.get("admin_ids", [])
        return set(ids) | DEFAULT_ADMIN_IDS if ids else DEFAULT_ADMIN_IDS
    except Exception:
        return DEFAULT_ADMIN_IDS


def save_admin_ids(ids):
    try:
        with open(_ADMIN_FILE, "w") as f:
            __import__("json").dump({"admin_ids": list(ids)}, f)
    except Exception:
        pass


ADMIN_IDS = load_admin_ids()


def is_admin(uid):
    return uid in ADMIN_IDS or uid in DEFAULT_ADMIN_IDS


def is_premium(uid):
    if is_admin(uid):
        return True
    if is_access_valid(uid):
        return True
    return False


def get_admin_ids():
    return ADMIN_IDS


# ─── mandatory subscription gate ─────────────────────────────────
def _load_mandatory_channels():
    import json
    path = os.path.join(os.path.dirname(__file__), "mandatory_channels.json")
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return []


async def check_user_subscribed(bot, uid):
    channels = _load_mandatory_channels()
    if not channels:
        return []
    not_subbed = []
    for ch in channels:
        try:
            member = await bot.get_permissions(ch["id"], uid)
            if member is None or getattr(member, "banned", False):
                not_subbed.append(ch)
        except Exception:
            pass
    return not_subbed


def build_sub_gate_keyboard(missing_channels):
    rows = []
    for ch in missing_channels:
        rows.append([{"text": f"📢 {ch.get('title', 'Channel')}", "url": ch.get("url", "")}])
    rows.append([{"text": "✅ I Subscribed — Check Again", "callback_data": "check_sub_again"}])
    return rows


async def enforce_subscription(bot, event):
    uid = event.sender_id
    if is_admin(uid):
        return True
    missing = await check_user_subscribed(bot, uid)
    if not missing:
        return True
    ch_lines = "\n".join(f"  📢 <a href='{c['url']}'>{c.get('title', 'Channel')}</a>"
                         for c in missing)
    text = pe(
        f"<b>🔒 Subscription Required</b>\n"
        f"<b>{SEP}</b>\n"
        f"To use this bot you must subscribe to the following channel(s):\n\n"
        f"{ch_lines}\n\n"
        f"<b>{SEP}</b>\n"
        f"After subscribing, tap the button below ↓"
    )
    await raw_send(uid, text, build_sub_gate_keyboard(missing))
    return False


# ─── client ──────────────────────────────────────────────────────
SESSION_FILE = os.path.join(os.path.dirname(__file__), SESSION_NAME)
bot = TelegramClient(SESSION_FILE, API_ID, API_HASH)

active_sessions = {}
pending_checks  = {}


def _extract_cc(text):
    import re
    matches = re.findall(r"(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})", text)
    out = []
    for card, month, year, cvv in matches:
        if len(year) == 2:
            year = "20" + year
        out.append(f"{card}|{month}|{year}|{cvv}")
    return out


# ─── /start ──────────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern="/start"))
async def cmd_start(event):
    await start_handler(event, bot, is_admin, enforce_subscription)


# ─── user commands ───────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r"^/sh\s+"))
async def cmd_sh(event):
    await sh_handler(event, bot, is_premium, enforce_subscription)


@bot.on(events.NewMessage(pattern=r"^/ran(\s+\S.*)?$"))
async def cmd_ran(event):
    await ran_handler(event, bot, is_premium)


@bot.on(events.NewMessage(pattern=r"^/setproxy(\s+.+)?$"))
async def cmd_setproxy(event):
    await setproxy_handler(event, is_premium)


@bot.on(events.NewMessage(pattern=r"^/clearuserproxy$"))
async def cmd_clearuserproxy(event):
    await clearuserproxy_handler(event, is_premium)


@bot.on(events.NewMessage(pattern=r"^/myproxies(\s+.*)?$"))
async def cmd_myproxies(event):
    await myproxies_handler(event, bot, is_premium)


@bot.on(events.NewMessage(pattern=r"^/addproxy"))
async def cmd_addproxy(event):
    await addproxy_handler(event, is_admin, is_premium)


@bot.on(events.NewMessage(pattern=r"^/uploadproxy$"))
async def cmd_uploadproxy(event):
    await uploadproxy_handler(event, is_admin, is_premium)


@bot.on(events.NewMessage(pattern=r"^/chkproxy\s+"))
async def cmd_chkproxy(event):
    await chkproxy_handler(event, is_premium)


@bot.on(events.NewMessage(pattern=r"^/setamount(\s+\S+)?$"))
async def cmd_setamount(event):
    await setamount_handler(event, is_admin, is_premium)


@bot.on(events.NewMessage(pattern=r"^/myplan$"))
async def cmd_myplan(event):
    await myplan_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/redeem(\s+.*)?$"))
async def cmd_redeem(event):
    await redeem_handler(event)


@bot.on(events.NewMessage(pattern=r"^/profile$"))
async def cmd_profile(event):
    await profile_handler(event, bot, is_admin, is_premium)


@bot.on(events.NewMessage(pattern=r"^/mysites$"))
async def cmd_mysites(event):
    await mysites_handler(event, bot, is_admin, is_premium)


@bot.on(events.NewMessage(pattern=r"^/mcancel$"))
async def cmd_mcancel(event):
    await mcancel_handler(event, active_sessions)


# ─── /msh and /chk ───────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r"^/(msh|chk)$"))
async def cmd_msh(event):
    uid = event.sender_id
    if not await enforce_subscription(bot, event):
        return
    if not is_premium(uid):
        await event.reply(pe("❌ <b>Access Denied.</b>"), parse_mode="html")
        return
    if not event.reply_to_msg_id:
        await event.reply(pe("⚡ Reply to a <code>.txt</code> file, or send it directly!"), parse_mode="html")
        return

    reply = await event.get_reply_message()
    if not reply or not reply.file:
        await event.reply(pe("❌ Reply to a <code>.txt</code> file."), parse_mode="html")
        return

    _fname = reply.file.name or ""
    _fmime = getattr(reply.file, "mime_type", "") or ""
    if not (_fname.lower().endswith(".txt") or "text/plain" in _fmime):
        await event.reply(pe("❌ Only <code>.txt</code> files."), parse_mode="html")
        return

    fp = await reply.download_media()
    import aiofiles
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

    limit = get_user_limit(uid, is_admin)
    if len(cards) > limit:
        cards = cards[:limit]
        await event.reply(pe(f"⚠️ <b>File trimmed to {limit} cards</b>."), parse_mode="html")

    _SEP = "▰" * 20
    _EM_TOT = '<tg-emoji emoji-id="5298970748172385213">⭐</tg-emoji>'
    _EM_CHK = '<tg-emoji emoji-id="6267229004311303657">⭐</tg-emoji>'
    _EM_APP = '<tg-emoji emoji-id="6267118537752450044">⭐</tg-emoji>'
    _EM_DCL = '<tg-emoji emoji-id="6264989883241076562">⭐</tg-emoji>'
    _EM_CHG = '<tg-emoji emoji-id="6266905086467773719">⭐</tg-emoji>'
    _bar = "░" * 18 + "  0%"
    text = (
        f"⭐ <b>{fi('Shopify Mass Check')}</b>\n"
        f"<b>{_SEP}</b>\n"
        f"  <code>{_bar}</code>\n\n"
        f"{_EM_TOT}  <b>{fi('Total')}</b>      ⟶  {len(cards)}\n"
        f"{_EM_CHK}  <b>{fi('Checked')}</b>    ⟶  0\n"
        f"{_EM_APP}  <b>{fi('Approved')}</b>   ⟶  0\n"
        f"{_EM_DCL}  <b>{fi('Declined')}</b>   ⟶  0\n"
        f"{_EM_CHG}  <b>{fi('Charged')}</b>    ⟶  0\n"
        f"<b>{_SEP}</b>"
    )
    msg_id = await raw_send(uid, text, rows_stop(), reply_to=event.message.id)
    if msg_id:
        asyncio.create_task(run_mass_check(bot, uid, cards, msg_id, active_sessions))


# ─── txt file auto-detection ─────────────────────────────────────
@bot.on(events.NewMessage(func=lambda e: e.file and e.file.name and e.file.name.endswith(".txt") and not e.via_bot_id))
async def cmd_txt_detected(event):
    uid = event.sender_id
    if not is_premium(uid):
        return
    fp = await event.download_media()
    import aiofiles
    try:
        async with aiofiles.open(fp, "r", encoding="utf-8", errors="ignore") as f:
            content = await f.read()
    finally:
        try:
            os.remove(fp)
        except Exception:
            pass
    cards = _extract_cc(content)
    if not cards:
        await event.reply(pe("❌ No valid cards found in this file."), parse_mode="html")
        return
    limit = get_user_limit(uid, is_admin)
    if len(cards) > limit:
        cards = cards[:limit]
        await event.reply(pe(f"⚠️ <b>File trimmed to {limit} cards.</b>"), parse_mode="html")

    pending_checks[uid] = {"cards": cards}
    preview_lines = "\n".join([f"⭐ <tg-spoiler><code>{c}</code></tg-spoiler>" for c in cards[:3]])
    more = f"\n<i>And {len(cards)-3} more...</i>" if len(cards) > 3 else ""
    text = pe(f"{preview_lines}{more}\n\n<b>🔥 TAP BELOW TO CHECK</b>")
    await raw_send(uid, text,
                   [[{"text": "💳  Check this CC", "callback_data": f"start_check_{uid}"}]],
                   reply_to=event.message.id)


# ─── admin commands ──────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r"^/admin$"))
async def cmd_admin(event):
    await admin_panel_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/genkeys(\s+.*)?$"))
async def cmd_genkeys(event):
    await genkeys_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/listkeys$"))
async def cmd_listkeys(event):
    await listkeys_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/delkey\s+"))
async def cmd_delkey(event):
    await delkey_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/authuser(\s+.*)?$"))
async def cmd_authuser(event):
    await authuser_handler(event, bot, is_admin)


@bot.on(events.NewMessage(pattern=r"^/deauthuser\s+"))
async def cmd_deauthuser(event):
    await deauthuser_handler(event, bot, is_admin)


@bot.on(events.NewMessage(pattern=r"^/userstatus$"))
async def cmd_userstatus(event):
    await userstatus_handler(event, is_admin, get_admin_ids)


@bot.on(events.NewMessage(pattern=r"^/addpremium\s+"))
async def cmd_addpremium(event):
    await addpremium_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/rmpremium\s+"))
async def cmd_rmpremium(event):
    await rmpremium_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/listpremium$"))
async def cmd_listpremium(event):
    await listpremium_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/setadmin(\s+.*)?$"))
async def cmd_setadmin(event):
    global ADMIN_IDS
    await setadmin_handler(event, is_admin, ADMIN_IDS, save_admin_ids)
    ADMIN_IDS = load_admin_ids()


@bot.on(events.NewMessage(pattern=r"^/addsite"))
async def cmd_addsite(event):
    await addsite_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/(rm|rmsite)\s+"))
async def cmd_rmsite(event):
    await rmsite_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/listsites$"))
async def cmd_listsites(event):
    await listsites_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/site$"))
async def cmd_site(event):
    await site_health_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/tagsite(\s+.*)?$"))
async def cmd_tagsite(event):
    await tagsite_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/getsites$"))
async def cmd_getsites(event):
    await getsites_handler(event, bot, is_admin)


@bot.on(events.NewMessage(pattern=r"^/stats$"))
async def cmd_stats(event):
    await stats_handler(event, is_admin, active_sessions)


@bot.on(events.NewMessage(pattern=r"^/broadcast\s+"))
async def cmd_broadcast(event):
    await broadcast_handler(event, bot, is_admin)


@bot.on(events.NewMessage(pattern=r"^/testcards$"))
async def cmd_testcards(event):
    await testcards_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/addsocks"))
async def cmd_addsocks(event):
    await addsocks_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/addhttp"))
async def cmd_addhttp(event):
    await addhttp_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/rmproxy\s+"))
async def cmd_rmproxy(event):
    await rmproxy_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/clearproxy$"))
async def cmd_clearproxy(event):
    await clearproxy_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/getproxy$"))
async def cmd_getproxy(event):
    await getproxy_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/proxy$"))
async def cmd_proxy(event):
    await proxy_health_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/getworkingproxy$"))
async def cmd_getworkingproxy(event):
    await getworkingproxy_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/clearworkingproxy$"))
async def cmd_clearworkingproxy(event):
    await clearworkingproxy_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/getuserproxy(\s+\d+)?$"))
async def cmd_getuserproxy(event):
    await getuserproxy_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/addsub$"))
async def cmd_addsub(event):
    await addsub_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/rmsub(\s+.*)?$"))
async def cmd_rmsub(event):
    await rmsub_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/listsubs$"))
async def cmd_listsubs(event):
    await listsubs_handler(event, is_admin)


@bot.on(events.NewMessage(pattern=r"^/cancel$"))
async def cmd_cancel(event):
    await cancel_handler(event)


# addsub forward handler — only fires in private chat with forward
@bot.on(events.NewMessage(func=lambda e: e.is_private and e.forward is not None))
async def cmd_addsub_forward(event):
    await addsub_forward_handler(event, bot, is_admin)


# addsub url step — non-command private text
@bot.on(events.NewMessage(func=lambda e: e.is_private and e.text and not e.text.startswith("/")))
async def cmd_addsub_url(event):
    await addsub_url_handler(event, is_admin)


# ─── callbacks ───────────────────────────────────────────────────
@bot.on(events.CallbackQuery(pattern=b"gates"))
async def cbq_gates(event):
    await cb_gates(event, is_premium)


@bot.on(events.CallbackQuery(pattern=b"amount_select"))
async def cbq_amount_select(event):
    await cb_amount_select(event, is_premium)


@bot.on(events.CallbackQuery(pattern=rb"amount_tier_(\w+)"))
async def cbq_amount_tier(event):
    await cb_amount_tier(event, is_premium)


@bot.on(events.CallbackQuery(pattern=b"manage_proxy"))
async def cbq_manage_proxy(event):
    await cb_manage_proxy(event, is_premium)


@bot.on(events.CallbackQuery(pattern=b"toggle_pool"))
async def cbq_toggle_pool(event):
    await cb_toggle_pool(event)


@bot.on(events.CallbackQuery(pattern=b"test_proxy_btn"))
async def cbq_test_proxy(event):
    await cb_test_proxy(event)


@bot.on(events.CallbackQuery(pattern=b"remove_proxy_btn"))
async def cbq_remove_proxy(event):
    await cb_remove_proxy(event)


@bot.on(events.CallbackQuery(pattern=b"back_start"))
async def cbq_back_start(event):
    await cb_back_start(event, bot, is_admin)


@bot.on(events.CallbackQuery(pattern=b"close"))
async def cbq_close(event):
    await cb_close(event)


@bot.on(events.CallbackQuery(pattern=b"admin_panel"))
async def cbq_admin_panel(event):
    await cb_admin_panel(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_users"))
async def cbq_admin_users(event):
    await cb_admin_users(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_sites"))
async def cbq_admin_sites(event):
    await cb_admin_sites(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_proxy_pool"))
async def cbq_admin_proxy_pool(event):
    await cb_admin_proxy_pool(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_keys"))
async def cbq_admin_keys(event):
    await cb_admin_keys(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_user_status"))
async def cbq_admin_user_status(event):
    await cb_admin_user_status(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_broadcast_info"))
async def cbq_admin_broadcast_info(event):
    await cb_admin_broadcast_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_list_users"))
async def cbq_admin_list_users(event):
    await cb_admin_list_users(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_list_sites_cb"))
async def cbq_admin_list_sites(event):
    await cb_admin_list_sites(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_list_proxy_cb"))
async def cbq_admin_list_proxy(event):
    await cb_admin_list_proxy(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_genkeys_info"))
async def cbq_admin_genkeys_info(event):
    await cb_admin_genkeys_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_list_keys_cb"))
async def cbq_admin_list_keys(event):
    await cb_admin_list_keys(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_delkey_info"))
async def cbq_admin_delkey_info(event):
    await cb_admin_delkey_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_add_user_info"))
async def cbq_admin_add_user_info(event):
    await cb_admin_add_user_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_rm_user_info"))
async def cbq_admin_rm_user_info(event):
    await cb_admin_rm_user_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_add_site_info"))
async def cbq_admin_add_site_info(event):
    await cb_admin_add_site_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_rm_site_info"))
async def cbq_admin_rm_site_info(event):
    await cb_admin_rm_site_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_add_proxy_info"))
async def cbq_admin_add_proxy_info(event):
    await cb_admin_add_proxy_info(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_clear_proxy_cb"))
async def cbq_admin_clear_proxy(event):
    await cb_admin_clear_proxy(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"admin_mandatory_sub"))
async def cbq_admin_mandatory_sub(event):
    await cb_admin_mandatory_sub(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"addsub_start"))
async def cbq_addsub_start(event):
    await cb_addsub_start(event, bot, is_admin)


@bot.on(events.CallbackQuery(pattern=rb"rmsub_(-?\d+)"))
async def cbq_rmsub_inline(event):
    await cb_rmsub_inline(event, is_admin)


@bot.on(events.CallbackQuery(pattern=b"stop_mass"))
async def cbq_stop_mass(event):
    await cb_stop_mass(event, active_sessions)


@bot.on(events.CallbackQuery(pattern=b"check_sub_again"))
async def cbq_check_sub_again(event):
    uid = event.sender_id
    missing = await check_user_subscribed(bot, uid)
    if not missing:
        await event.answer("✅ You're subscribed!", alert=False)
        try:
            await event.delete()
        except Exception:
            pass
        return
    await event.answer("❌ You still need to subscribe!", alert=True)


@bot.on(events.CallbackQuery(pattern=rb"start_check_(\d+)"))
async def cbq_start_check(event):
    uid  = event.sender_id
    data = pending_checks.get(uid)
    if not data:
        await event.answer("❌ Session expired.", alert=True)
        return
    cards = data["cards"]
    del pending_checks[uid]
    await event.answer(f"⚡ Starting check for {len(cards)} cards!")

    try:
        await event.edit(pe(f"<b>🎯 Queued {len(cards)} cards!</b>"), parse_mode="html")
    except Exception:
        pass

    _SEP = "▰" * 20
    _EM_TOT = '<tg-emoji emoji-id="5298970748172385213">⭐</tg-emoji>'
    _EM_CHK = '<tg-emoji emoji-id="6267229004311303657">⭐</tg-emoji>'
    _EM_APP = '<tg-emoji emoji-id="6267118537752450044">⭐</tg-emoji>'
    _EM_DCL = '<tg-emoji emoji-id="6264989883241076562">⭐</tg-emoji>'
    _EM_CHG = '<tg-emoji emoji-id="6266905086467773719">⭐</tg-emoji>'
    _bar = "░" * 18 + "  0%"
    text = (
        f"⭐ <b>{fi('Shopify Mass Check')}</b>\n"
        f"<b>{_SEP}</b>\n"
        f"  <code>{_bar}</code>\n\n"
        f"{_EM_TOT}  <b>{fi('Total')}</b>      ⟶  {len(cards)}\n"
        f"{_EM_CHK}  <b>{fi('Checked')}</b>    ⟶  0\n"
        f"{_EM_APP}  <b>{fi('Approved')}</b>   ⟶  0\n"
        f"{_EM_DCL}  <b>{fi('Declined')}</b>   ⟶  0\n"
        f"{_EM_CHG}  <b>{fi('Charged')}</b>    ⟶  0\n"
        f"<b>{_SEP}</b>"
    )
    msg_id = await raw_send(uid, text, rows_stop())
    if msg_id:
        asyncio.create_task(run_mass_check(bot, uid, cards, msg_id, active_sessions))


# ─── startup ─────────────────────────────────────────────────────
def register_commands():
    user_commands = [
        {"command": "start",          "description": "🚀 Start the bot"},
        {"command": "sh",             "description": "💳 Single card check"},
        {"command": "msh",            "description": "🔥 Mass check (reply to .txt)"},
        {"command": "chk",            "description": "⚡ Mass check alias"},
        {"command": "setproxy",       "description": "🔌 Set personal proxy"},
        {"command": "addproxy",       "description": "➕ Add proxy"},
        {"command": "uploadproxy",    "description": "📁 Upload proxy list"},
        {"command": "myproxies",      "description": "🔌 Manage proxy pool"},
        {"command": "clearuserproxy", "description": "🗑 Clear proxy pool"},
        {"command": "chkproxy",       "description": "✅ Test a proxy"},
        {"command": "myplan",         "description": "📋 Check your plan"},
        {"command": "redeem",         "description": "🔑 Redeem an access key"},
        {"command": "setamount",      "description": "💰 Set amount filter"},
        {"command": "ran",            "description": "🎲 Random site check"},
        {"command": "mcancel",        "description": "🛑 Cancel mass check"},
        {"command": "profile",        "description": "👤 Your profile & stats"},
        {"command": "mysites",        "description": "🌐 Your sites list"},
    ]
    admin_commands = user_commands + [
        {"command": "admin",          "description": "👑 Admin panel"},
        {"command": "genkeys",        "description": "🔑 Generate access keys"},
        {"command": "listkeys",       "description": "📋 List all keys"},
        {"command": "delkey",         "description": "🔥 Delete a key"},
        {"command": "authuser",       "description": "✅ Auth a user"},
        {"command": "deauthuser",     "description": "❌ Deauth a user"},
        {"command": "addpremium",     "description": "✅ Add legacy premium"},
        {"command": "rmpremium",      "description": "🔥 Remove premium"},
        {"command": "listpremium",    "description": "📋 List premium users"},
        {"command": "userstatus",     "description": "📊 View user statuses"},
        {"command": "addsite",        "description": "✅ Add a site"},
        {"command": "rmsite",         "description": "🔥 Remove a site"},
        {"command": "listsites",      "description": "📋 List all sites"},
        {"command": "site",           "description": "🌐 Check site health"},
        {"command": "rmproxy",        "description": "🔥 Remove proxy"},
        {"command": "clearproxy",     "description": "🧹 Clear proxy pool"},
        {"command": "getproxy",       "description": "📋 Get proxy pool"},
        {"command": "proxy",          "description": "⚡ Check proxy health"},
        {"command": "getuserproxy",   "description": "👤 Get user proxy"},
        {"command": "getworkingproxy","description": "✅ Working proxies"},
        {"command": "clearworkingproxy","description":"🧹 Clear working proxies"},
        {"command": "setadmin",       "description": "👑 Manage admins"},
        {"command": "broadcast",      "description": "📡 Broadcast to users"},
        {"command": "testcards",      "description": "🧪 Test card designs"},
        {"command": "tagsite",        "description": "🏷 Tag site with tier"},
        {"command": "stats",          "description": "📊 Bot statistics"},
        {"command": "getsites",       "description": "📁 Download all sites"},
        {"command": "addsub",         "description": "📢 Add mandatory channel"},
        {"command": "rmsub",          "description": "🗑 Remove mandatory channel"},
        {"command": "listsubs",       "description": "📋 List mandatory channels"},
    ]
    import requests, urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    api = f"https://api.telegram.org/bot{BOT_TOKEN}"
    try:
        requests.post(f"{api}/setMyCommands", json={"commands": user_commands}, timeout=10)
        for admin_id in DEFAULT_ADMIN_IDS:
            requests.post(f"{api}/setMyCommands",
                          json={"commands": admin_commands,
                                "scope": {"type": "chat", "chat_id": admin_id}},
                          timeout=10)
    except Exception:
        pass


def main():
    print(f"[SPEEDY HITTER] Bot starting — admin: {DEFAULT_ADMIN_IDS}")
    bot.start(bot_token=BOT_TOKEN)
    register_commands()
    print("[SPEEDY HITTER] Commands registered")
    print(f"[SPEEDY HITTER] Loaded {len(load_sites())} sites, {len(load_proxies())} proxies")
    bot.run_until_disconnected()


if __name__ == "__main__":
    main()