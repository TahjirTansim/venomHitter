#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Admin command handlers."""
import asyncio
import json
import os
import random
import time
from datetime import datetime

import aiofiles
import aiohttp

from config import (
    AMOUNT_TIERS,
    BOT_BRAND,
    DEFAULT_ADMIN_IDS,
    OWNER_USERNAME,
)
from storage import (
    _normalise_site,
    _tokenise,
    _validate_proxy_fmt,
    _validate_site_fmt,
    get_user_proxy,
    load_premium_users,
    load_proxies,
    load_sites,
    load_sites_for_user,
    load_sites_meta,
    load_user_proxies,
    normalize_proxy,
    record_log,
    record_mass_check,
    save_sites_meta,
    tag_site_tier,
    user_pool_enabled,
)
from keys import (
    all_keys,
    all_user_access,
    create_keys,
    delete_key,
    is_access_valid,
    keys_summary,
    revoke_user_access,
    set_user_access,
    time_remaining,
)
from emojis import pe
from branding import SEP, dev_line, fi
from ui import (
    raw_send,
    rows_admin,
    rows_stop,
    TG_API,
    _raw_post,
)
from handlers_user import (
    build_result_card,
    get_bin_info,
    get_display_info,
    get_proxies_for_user,
)
from orchestrator import check_card_with_retry, test_site


# ─── /admin ──────────────────────────────────────────────────────
def _admin_panel_text():
    pcount = len(load_premium_users()) + len(all_user_access())
    scount = len(load_sites())
    pxpool = len(load_proxies())
    ksum   = keys_summary()
    return pe(
        f"<b>👑 Admin Panel — {BOT_BRAND}</b>\n"
        f"<b>{SEP}</b>\n"
        f"👤 <b>Total Users:</b> {pcount}\n"
        f"🌐 <b>Sites:</b> {scount}\n"
        f"⚙️ <b>Proxy Pool:</b> {pxpool}\n"
        f"🔑 <b>Keys:</b> {ksum['total']} total | {ksum['unused']} unused\n"
        f"<b>{SEP}</b>\n"
        f"{dev_line()}"
    )


async def admin_panel_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    await raw_send(event.sender_id, _admin_panel_text(), rows_admin())


# ─── /genkeys ────────────────────────────────────────────────────
async def genkeys_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    parts = event.message.text.split()
    if len(parts) < 3:
        await event.reply(pe(
            f"❌ <b>Usage:</b> <code>/genkeys [count] [days]</code>\n"
            f"Example: <code>/genkeys 20 1</code>"
        ), parse_mode="html")
        return

    try:
        count = int(parts[1])
        days  = int(parts[2])
        if count < 1 or count > 100 or days < 1:
            raise ValueError
    except Exception:
        await event.reply(pe("❌ Invalid. Example: <code>/genkeys 20 1</code>"), parse_mode="html")
        return

    new_keys = create_keys(count, days)
    plan_label = f"{days} {'Day' if days == 1 else 'Days'} Plan"
    keys_text  = "\n".join([f"┣ 💖 <code>{k}</code>" for k in new_keys])

    msg = pe(
        f"📌🔥 <b>Keys Generated ✅</b>\n"
        f"<b>{SEP}</b>\n\n"
        f"┣ 👾 <b>Count</b> ➜ {count}\n"
        f"┣ 💎 <b>Plan</b> ➜ {plan_label}\n"
        f"┣ 💖 <b>Keys:</b>\n"
        f"{keys_text}\n\n"
        f"👿 <b>Users redeem with</b> <code>/redeem [key]</code>"
    )

    if len(msg) > 4000:
        fn = f"keys_{days}d_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        async with aiofiles.open(fn, "w") as f:
            await f.write(f"Plan: {plan_label}\n\n")
            for k in new_keys:
                await f.write(f"{k}\n")
        await event.reply(pe(f"📌 <b>Generated {count} keys ({plan_label})</b>"),
                          file=fn, parse_mode="html")
        try:
            os.remove(fn)
        except Exception:
            pass
    else:
        await event.reply(msg, parse_mode="html")


# ─── /listkeys ───────────────────────────────────────────────────
async def listkeys_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    kd = all_keys()
    if not kd:
        await event.reply(pe("📋 No keys generated yet."), parse_mode="html")
        return

    unused = [(k, v) for k, v in kd.items() if v.get("redeemed_by") is None]
    used   = [(k, v) for k, v in kd.items() if v.get("redeemed_by") is not None]

    lines = [pe(f"<b>📋 Keys Summary</b>\n<b>{SEP}</b>\n"
                f"🟢 Unused: {len(unused)} | 🔴 Used: {len(used)}\n<b>{SEP}</b>")]
    for k, v in unused[:20]:
        lines.append(f"🟢 <code>{k}</code> — {v.get('plan_days', '?')}d")
    for k, v in used[:10]:
        lines.append(f"🔴 <code>{k}</code> — redeemed by <code>{v.get('redeemed_by', '?')}</code>")

    await event.reply("\n".join(lines), parse_mode="html")


# ─── /delkey ─────────────────────────────────────────────────────
async def delkey_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    key = event.message.text.split(None, 1)[1].strip()
    if not delete_key(key):
        await event.reply(pe(f"❌ Key not found: <code>{key}</code>"), parse_mode="html")
        return
    await event.reply(pe(f"🔥 <b>Key deleted!</b>\n<code>{key}</code>"), parse_mode="html")


# ─── /authuser ───────────────────────────────────────────────────
async def authuser_handler(event, bot, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    parts = event.message.text.split()
    if len(parts) < 3:
        await event.reply(pe(
            f"❌ <b>Usage:</b> <code>/authuser [user_id] [days]</code>\n"
            f"Example: <code>/authuser 123456789 30</code>"
        ), parse_mode="html")
        return

    try:
        target = int(parts[1])
        days   = int(parts[2])
        if days < 1:
            raise ValueError
    except Exception:
        await event.reply(pe("❌ Invalid. Example: <code>/authuser 123456789 30</code>"), parse_mode="html")
        return

    set_user_access(target, "auth", days, granted_by=str(event.sender_id))
    trem = time_remaining(target)

    await event.reply(pe(
        f"✅ <b>User Authorized!</b>\n<b>{SEP}</b>\n"
        f"👤 <b>User:</b> <code>{target}</code>\n"
        f"💎 <b>Tier:</b> Auth\n"
        f"📅 <b>Days:</b> {days}\n"
        f"⏳ <b>Expires in:</b> {trem}"
    ), parse_mode="html")

    try:
        await bot.send_message(target, pe(
            f"✅ <b>Access Granted!</b>\n<b>{SEP}</b>\n"
            f"💎 <b>Plan:</b> Auth — {days} days\n"
            f"⏳ <b>Expires in:</b> {trem}\n"
            f"<b>{SEP}</b>\n{dev_line()}"
        ), parse_mode="html")
    except Exception:
        pass


# ─── /deauthuser ─────────────────────────────────────────────────
async def deauthuser_handler(event, bot, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    parts = event.message.text.split()
    if len(parts) < 2:
        await event.reply(pe("❌ Usage: <code>/deauthuser [user_id]</code>"), parse_mode="html")
        return

    try:
        target = int(parts[1])
    except Exception:
        await event.reply(pe("❌ Invalid user ID."), parse_mode="html")
        return

    revoke_user_access(target)

    curr = load_premium_users()
    if str(target) in curr:
        async with aiofiles.open("premium.txt", "w") as f:
            for u in curr:
                if u != str(target):
                    await f.write(f"{u}\n")

    await event.reply(pe(f"🚫 <b>User Deauthorized!</b>\n👤 <code>{target}</code> access revoked."),
                      parse_mode="html")

    try:
        await bot.send_message(target, pe(
            f"❌ <b>Access Revoked</b>\n<b>{SEP}</b>\n"
            f"Your access has been revoked by admin."
        ), parse_mode="html")
    except Exception:
        pass


# ─── /userstatus ─────────────────────────────────────────────────
async def userstatus_handler(event, is_admin_fn, admin_ids_getter):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    admin_ids = admin_ids_getter()
    lines = [pe(f"<b>📊 Complete User Status</b>\n<b>{SEP}</b>")]

    lines.append(f"\n👑 <b>Admins ({len(admin_ids)}):</b>")
    for aid in sorted(admin_ids):
        proxy = get_user_proxy(aid) or "None"
        proxy_str = proxy[:30] if proxy != "None" else "None"
        lines.append(f"  • <code>{aid}</code> | Proxy: <code>{proxy_str}</code>")

    ua = all_user_access()
    if ua:
        lines.append(f"\n🔑 <b>Access Users ({len(ua)}):</b>")
        for uid_str, acc in ua.items():
            uid_int = int(uid_str)
            tier    = acc.get("tier", "?")
            exp     = acc.get("expires_at", "")[:10]
            trem    = time_remaining(uid_int) or "Expired"
            proxy   = get_user_proxy(uid_int) or "None"
            pool_on = user_pool_enabled.get(uid_int, True)
            valid   = "✅" if is_access_valid(uid_int) else "❌"
            proxy_str = proxy[:30] if proxy != "None" else "None"
            lines.append(
                f"  {valid} <code>{uid_str}</code>\n"
                f"     Tier: {tier} | Expires: {exp} | Left: {trem}\n"
                f"     Proxy: <code>{proxy_str}</code> | Pool: {'ON' if pool_on else 'OFF'}"
            )

    prem = load_premium_users()
    if prem:
        lines.append(f"\n⭐ <b>Legacy Premium ({len(prem)}):</b>")
        for uid_str in prem:
            proxy = get_user_proxy(int(uid_str)) if uid_str.isdigit() else None
            proxy_str = f"<code>{proxy[:30]}</code>" if proxy else "None"
            lines.append(f"  • <code>{uid_str}</code> | Proxy: {proxy_str}")

    ksum = keys_summary()
    lines.append(pe(
        f"\n<b>{SEP}</b>\n"
        f"📋 <b>Proxy Pool:</b> {len(load_proxies())}\n"
        f"🌐 <b>Sites:</b> {len(load_sites())}\n"
        f"🔑 <b>Total Keys:</b> {ksum['total']}\n"
        f"🟢 <b>Unused Keys:</b> {ksum['unused']}"
    ))

    full_text = "\n".join(lines)
    if len(full_text) > 4000:
        import re as _re
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"user_status_{ts}.txt"
        clean = _re.sub(r"<[^>]+>", "", full_text)
        with open(fn, "w") as f:
            f.write(clean)
        await event.reply(pe(f"📊 <b>User Status Report</b>"), file=fn, parse_mode="html")
        try:
            os.remove(fn)
        except Exception:
            pass
    else:
        await event.reply(full_text, parse_mode="html")


# ─── /addpremium / /rmpremium / /listpremium ─────────────────────
async def addpremium_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    new_id = event.message.text.split(" ", 1)[1].strip()
    if not new_id.isdigit():
        await event.reply(pe("❌ Usage: <code>/addpremium 123456789</code>"), parse_mode="html")
        return
    curr = load_premium_users()
    if new_id in curr:
        await event.reply(pe(f"⚠️ User <code>{new_id}</code> already premium."), parse_mode="html")
        return
    async with aiofiles.open("premium.txt", "a") as f:
        await f.write(f"{new_id}\n")
    await event.reply(pe(f"✅ <b>Premium Added!</b>\n👑 <code>{new_id}</code>"), parse_mode="html")


async def rmpremium_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    rm_id = event.message.text.split(" ", 1)[1].strip()
    curr  = load_premium_users()
    if rm_id not in curr:
        await event.reply(pe(f"❌ User <code>{rm_id}</code> not in list."), parse_mode="html")
        return
    async with aiofiles.open("premium.txt", "w") as f:
        for u in curr:
            if u != rm_id:
                await f.write(f"{u}\n")
    await event.reply(pe(f"🚫 <b>Premium Removed!</b>\n<code>{rm_id}</code>"), parse_mode="html")


async def listpremium_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    curr = load_premium_users()
    if not curr:
        await event.reply(pe("📋 No legacy premium users found."), parse_mode="html")
        return
    lines = "\n".join([f"{i+1}. <code>{u}</code>" for i, u in enumerate(curr)])
    await event.reply(pe(f"<b>📋 Legacy Premium ({len(curr)}):</b>\n\n{lines}"), parse_mode="html")


# ─── /setadmin ───────────────────────────────────────────────────
async def setadmin_handler(event, is_admin_fn, admin_ids, save_admin_ids_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    parts = event.message.text.strip().split()
    current_list = "\n".join(f"• <code>{a}</code>" for a in sorted(admin_ids))

    if len(parts) < 2:
        await event.reply(pe(
            f"<b>👑 Admin Management</b>\n<b>{SEP}</b>\n"
            f"<b>Current admins:</b>\n{current_list}\n<b>{SEP}</b>\n"
            f"<b>Add:</b> <code>/setadmin add [user_id]</code>\n"
            f"<b>Remove:</b> <code>/setadmin rm [user_id]</code>"
        ), parse_mode="html")
        return

    action = parts[1].lower()
    if action not in ("add", "rm", "remove") or len(parts) < 3:
        await event.reply(pe("❌ Usage: <code>/setadmin add|rm [user_id]</code>"), parse_mode="html")
        return

    try:
        target = int(parts[2])
    except Exception:
        await event.reply(pe("❌ Invalid user ID."), parse_mode="html")
        return

    if action == "add":
        admin_ids.add(target)
        save_admin_ids_fn(admin_ids)
        await event.reply(pe(f"✅ <b>Admin added:</b> <code>{target}</code>"), parse_mode="html")
    else:
        if target in DEFAULT_ADMIN_IDS:
            await event.reply(pe("❌ <b>Cannot remove a default admin.</b>"), parse_mode="html")
            return
        admin_ids.discard(target)
        save_admin_ids_fn(admin_ids)
        await event.reply(pe(f"✅ <b>Admin removed:</b> <code>{target}</code>"), parse_mode="html")


# ─── /addsite / /rmsite / /listsites ─────────────────────────────
async def _add_sites_bulk(event, raw_sites):
    curr_set = set(load_sites())
    added, dups, invalid = [], [], []
    seen = set()

    for u in raw_sites:
        u = _normalise_site(u.strip())
        if not u or u.startswith("#"):
            continue
        if not _validate_site_fmt(u):
            invalid.append(u)
        elif u in curr_set or u in seen:
            dups.append(u)
        else:
            added.append(u)
            seen.add(u)

    if added:
        async with aiofiles.open("sites.txt", "a") as f:
            for u in added:
                await f.write(f"{u}\n")

    total = len(curr_set) + len(added)
    lines = [
        f"📊 <b>Site Import Report</b>",
        f"<b>{SEP}</b>",
        f"✅ <b>Added:</b>      {len(added)}",
        f"⚠️ <b>Duplicates:</b> {len(dups)}",
        f"❌ <b>Invalid:</b>    {len(invalid)}",
        f"<b>{SEP}</b>",
        f"🌐 <b>Pool now:</b> {total} sites",
    ]
    if invalid and len(invalid) <= 5:
        lines.append("\n❌ <b>Invalid entries:</b>")
        for iv in invalid[:5]:
            lines.append(f"  <code>{iv[:80]}</code>")
    await event.reply(pe("\n".join(lines)), parse_mode="html")


async def addsite_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    reply = await event.get_reply_message()
    if reply and reply.document:
        buf = await reply.download_media(bytes)
        if not buf:
            await event.reply(pe("❌ Could not read file."), parse_mode="html")
            return
        tokens = _tokenise(buf.decode("utf-8", errors="ignore"))
        await _add_sites_bulk(event, tokens)
        return

    content = event.message.text[len("/addsite"):].strip()
    if not content:
        await event.reply(pe(
            f"❌ <b>Usage:</b>\n<b>{SEP}</b>\n"
            f"<code>/addsite https://shop.com</code>\n\n"
            f"📌 Space-separated or reply to a <code>.txt</code>"
        ), parse_mode="html")
        return

    tokens = _tokenise(content)
    if len(tokens) == 1:
        u = _normalise_site(tokens[0])
        if not _validate_site_fmt(u):
            await event.reply(pe("❌ URL must start with http:// or https://"), parse_mode="html")
            return
        if u in load_sites():
            await event.reply(pe("⚠️ Site already exists."), parse_mode="html")
            return
        async with aiofiles.open("sites.txt", "a") as f:
            await f.write(f"{u}\n")
        await event.reply(pe(f"✅ <b>Site Added!</b>\n<code>{u}</code>"), parse_mode="html")
    else:
        await _add_sites_bulk(event, tokens)


async def rmsite_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    url  = event.message.text.split(" ", 1)[1].strip()
    curr = load_sites()
    if url not in curr:
        await event.reply(pe("❌ Site not found."), parse_mode="html")
        return
    async with aiofiles.open("sites.txt", "w") as f:
        for s in curr:
            if s != url:
                await f.write(f"{s}\n")
    await event.reply(pe(f"✅ <b>Site removed!</b>\n<code>{url}</code>"), parse_mode="html")


async def listsites_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    curr = load_sites()
    if not curr:
        await event.reply(pe("📋 No sites found."), parse_mode="html")
        return
    if len(curr) <= 30:
        lines = "\n".join([f"{i+1}. <code>{s}</code>" for i, s in enumerate(curr)])
        await event.reply(pe(f"<b>🌐 Sites ({len(curr)}):</b>\n\n{lines}"), parse_mode="html")
    else:
        fn = f"sites_list_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        async with aiofiles.open(fn, "w") as f:
            for i, s in enumerate(curr):
                await f.write(f"{i+1}. {s}\n")
        await event.reply(pe(f"<b>🌐 Total Sites: {len(curr)}</b>"), file=fn, parse_mode="html")
        try:
            os.remove(fn)
        except Exception:
            pass


# ─── /site (health check) ────────────────────────────────────────
async def site_health_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    sites   = load_sites()
    proxies = load_proxies()
    if not sites:
        await event.reply(pe("❌ sites.txt is empty."), parse_mode="html")
        return
    if not proxies:
        await event.reply(pe("❌ No proxies available."), parse_mode="html")
        return

    smsg = await event.reply(pe(f"🔥 Checking {len(sites)} sites..."), parse_mode="html")
    alive, dead = [], []

    for i in range(0, len(sites), 10):
        batch = sites[i:i+10]
        results = await asyncio.gather(*[test_site(s, random.choice(proxies)) for s in batch])
        for r in results:
            (alive if r["status"] == "alive" else dead).append(r["site"])
        await smsg.edit(pe(f"🔥 Checking sites...\n✅ Alive: {len(alive)} | ❌ Dead: {len(dead)}"),
                        parse_mode="html")

    async with aiofiles.open("sites.txt", "w") as f:
        for s in alive:
            await f.write(f"{s}\n")

    await smsg.edit(pe(f"✅ <b>Site Check Done!</b>\n✅ Alive: {len(alive)}\n❌ Removed: {len(dead)}"),
                    parse_mode="html")


# ─── /tagsite ────────────────────────────────────────────────────
async def tagsite_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    parts = event.message.text.strip().split()
    if len(parts) < 3:
        meta  = load_sites_meta()
        sites = load_sites()
        tagged = sum(1 for s in sites if s in meta)
        tiers_count = {t: sum(1 for s in sites if meta.get(s, {}).get("tier") == t)
                       for t in AMOUNT_TIERS if t != "any"}
        lines = "\n".join(f"  {v[0]}: {tiers_count.get(k, 0)} sites"
                          for k, v in AMOUNT_TIERS.items() if k != "any")
        await event.reply(pe(
            f"<b>🏷 Site Tier Tagger</b>\n<b>{SEP}</b>\n"
            f"<b>Tagged:</b> {tagged} / {len(sites)} sites\n\n"
            f"{lines}\n\n"
            f"<b>Usage:</b> <code>/tagsite https://shop.com 1</code>"
        ), parse_mode="html")
        return

    url  = parts[1].strip().rstrip("/")
    tier = parts[2].strip().lower()

    if tier not in AMOUNT_TIERS:
        await event.reply(pe("❌ Valid tiers: 1 5 10 20 any"), parse_mode="html")
        return
    if url not in load_sites():
        await event.reply(pe(f"❌ Site not in list: <code>{url}</code>"), parse_mode="html")
        return

    if tier == "any":
        meta = load_sites_meta()
        meta.pop(url, None)
        save_sites_meta(meta)
        await event.reply(pe(f"✅ <b>Untagged</b> <code>{url}</code>"), parse_mode="html")
    else:
        tag_site_tier(url, tier)
        await event.reply(pe(f"✅ Tagged <code>{url}</code> as <b>{AMOUNT_TIERS[tier][0]}</b>"),
                          parse_mode="html")


# ─── /getsites ───────────────────────────────────────────────────
async def getsites_handler(event, bot, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    sites = load_sites()
    if not sites:
        await event.reply(pe("❌ sites.txt is empty."), parse_mode="html")
        return
    if len(sites) <= 30:
        import html as _h
        site_list = "\n".join([f"{i+1}. <code>{_h.escape(s)}</code>" for i, s in enumerate(sites)])
        await event.reply(pe(f"🌐 <b>Sites ({len(sites)}):</b>\n\n{site_list}"), parse_mode="html")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"all_sites_{ts}.txt"
        with open(fn, "w") as f:
            f.write("\n".join(sites))
        await bot.send_file(event.sender_id, fn,
                            caption=pe(f"🌐 <b>All Sites ({len(sites)})</b>"),
                            parse_mode="html")
        try:
            os.remove(fn)
        except Exception:
            pass


# ─── /stats ──────────────────────────────────────────────────────
async def stats_handler(event, is_admin_fn, active_sessions):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    try:
        with open("users.json") as f:
            users_db = json.load(f)
        total_users = len(users_db)
    except Exception:
        total_users = 0

    try:
        with open("user_stats.json") as f:
            ustats = json.load(f)
        total_checks = sum(v.get("total_checks", 0) for v in ustats.values())
        total_hits   = sum(v.get("charged", 0) + v.get("approved", 0) for v in ustats.values())
    except Exception:
        total_checks, total_hits = 0, 0

    active = len(active_sessions)
    SEP_S = "━" * 22

    await event.reply(pe(
        f"<b>{SEP_S}</b>\n"
        f"📊 <b>Bot Statistics</b>\n"
        f"<b>{SEP_S}</b>\n\n"
        f"👥 Total users   »  <b>{total_users}</b>\n"
        f"🌐 Active sites  »  <b>{len(load_sites())}</b>\n"
        f"🔌 Proxies       »  <b>{len(load_proxies())}</b>\n"
        f"💳 Total checks  »  <b>{total_checks}</b>\n"
        f"🔥 Total hits    »  <b>{total_hits}</b>\n"
        f"⚡ Active checks »  <b>{active}</b>\n\n"
        f"🤖 Status: Running ✅\n"
        f"<b>{SEP_S}</b>"
    ), parse_mode="html")


# ─── /broadcast ──────────────────────────────────────────────────
async def broadcast_handler(event, bot, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    msg   = event.message.text.split(" ", 1)[1].strip()
    users = load_premium_users()
    access_users = [str(k) for k in all_user_access().keys()]
    all_users = list(set(users + access_users))

    if not all_users:
        await event.reply(pe("❌ No users to broadcast to."), parse_mode="html")
        return

    bc = pe(
        f"<b>⚡ {BOT_BRAND}</b>\n<b>{SEP}</b>\n"
        f"<b>📡 Admin Broadcast</b>\n{msg}\n"
        f"<b>{SEP}</b>\n{dev_line()}"
    )

    smsg = await event.reply(pe(f"🚀 Broadcasting to {len(all_users)} users..."), parse_mode="html")
    sent, failed = 0, 0
    for uid in all_users:
        try:
            await bot.send_message(int(uid), bc, parse_mode="html")
            sent += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.1)

    await smsg.edit(pe(f"🚀 <b>Broadcast Done!</b>\n✅ Sent: {sent} | ❌ Failed: {failed}"),
                    parse_mode="html")


# ─── /testcards ──────────────────────────────────────────────────
async def testcards_handler(event, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    fake_bin = ("VISA", "Credit", "Classic", "Test Bank", "United States", "🇺🇸")
    statuses = [
        ("Charged",  "Payment captured successfully — $1.00 auth charge",   "Shopify Payments", "$1.00"),
        ("Approved", "Card approved — 3DS not required",                     "Shopify Payments", "$0.00"),
        ("OTP",      "3D Secure authentication required by issuing bank",    "Shopify Payments", "-"),
        ("Declined", "Your card was declined. Please try a different card.", "Shopify Payments", "-"),
    ]
    await event.reply(pe(f"<b>🧪 Test Cards Preview</b> — {len(statuses)} result types"),
                      parse_mode="html")

    for status, message, gateway, price in statuses:
        fake_result = {
            "status": status, "message": message,
            "card": "4111111111111111|12|2026|123",
            "gateway": gateway, "price": price,
        }
        card_msg = build_result_card(fake_result, fake_bin, uid, BOT_BRAND)
        await raw_send(uid, card_msg, [])
        await asyncio.sleep(0.4)


# ─── proxy management ────────────────────────────────────────────
async def _add_proxies_bulk(event, raw_proxies):
    curr_set = set(load_proxies())
    added, dups, invalid = [], [], []
    seen = set()

    for p in raw_proxies:
        p = p.strip()
        if not p or p.startswith("#"):
            continue
        if not _validate_proxy_fmt(p):
            invalid.append(p)
        elif p in curr_set or p in seen:
            dups.append(p)
        else:
            added.append(p)
            seen.add(p)

    if added:
        async with aiofiles.open("proxy.txt", "a") as f:
            for p in added:
                await f.write(f"{p}\n")

    total = len(curr_set) + len(added)
    lines = [
        f"📊 <b>Proxy Import Report</b>",
        f"<b>{SEP}</b>",
        f"✅ <b>Added:</b>      {len(added)}",
        f"⚠️ <b>Duplicates:</b> {len(dups)}",
        f"❌ <b>Invalid:</b>    {len(invalid)}",
        f"<b>{SEP}</b>",
        f"📋 <b>Pool now:</b> {total} proxies",
    ]
    if invalid and len(invalid) <= 5:
        lines.append("\n❌ <b>Invalid entries:</b>")
        for iv in invalid[:5]:
            lines.append(f"  <code>{iv[:60]}</code>")
    await event.reply(pe("\n".join(lines)), parse_mode="html")


async def addsocks_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    reply = await event.get_reply_message()
    if reply and reply.document:
        buf = await reply.download_media(bytes)
        if not buf:
            await event.reply(pe("❌ Could not read file."), parse_mode="html")
            return
        raw = _tokenise(buf.decode("utf-8", errors="ignore"))
        tokens = [t if "://" in t else f"socks5://{t}" for t in raw]
        await _add_proxies_bulk(event, tokens)
        return
    content = event.message.text[len("/addsocks"):].strip()
    if not content:
        await event.reply(pe(
            f"❌ <b>Usage:</b>\n<code>/addsocks ip:port</code>\n"
            f"<code>/addsocks ip:port:user:pass</code>\n\n"
            f"ℹ️ <b>socks5:// auto-injected</b>"
        ), parse_mode="html")
        return
    raw = _tokenise(content)
    tokens = [t if "://" in t else f"socks5://{t}" for t in raw]
    await _add_proxies_bulk(event, tokens)


async def addhttp_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    reply = await event.get_reply_message()
    if reply and reply.document:
        buf = await reply.download_media(bytes)
        if not buf:
            await event.reply(pe("❌ Could not read file."), parse_mode="html")
            return
        raw = _tokenise(buf.decode("utf-8", errors="ignore"))
        tokens = [t if "://" in t else f"http://{t}" for t in raw]
        await _add_proxies_bulk(event, tokens)
        return
    content = event.message.text[len("/addhttp"):].strip()
    if not content:
        await event.reply(pe(
            f"❌ <b>Usage:</b>\n<code>/addhttp ip:port</code>\n"
            f"<code>/addhttp ip:port:user:pass</code>\n\n"
            f"ℹ️ <b>http:// auto-injected</b>"
        ), parse_mode="html")
        return
    raw = _tokenise(content)
    tokens = [t if "://" in t else f"http://{t}" for t in raw]
    await _add_proxies_bulk(event, tokens)


async def rmproxy_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    p    = event.message.text.split(" ", 1)[1].strip()
    curr = load_proxies()
    if p not in curr:
        await event.reply(pe(f"❌ Proxy not found: <code>{p}</code>"), parse_mode="html")
        return
    async with aiofiles.open("proxy.txt", "w") as f:
        for x in curr:
            if x != p:
                await f.write(f"{x}\n")
    await event.reply(pe(f"✅ <b>Proxy removed!</b>\n<code>{p}</code>"), parse_mode="html")


async def clearproxy_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    curr = load_proxies()
    if not curr:
        await event.reply(pe("❌ proxy.txt is already empty."), parse_mode="html")
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bk = f"proxy_backup_{ts}.txt"
    async with aiofiles.open(bk, "w") as f:
        for p in curr:
            await f.write(f"{p}\n")
    await event.reply(pe(f"📋 <b>Backup — {len(curr)} proxies:</b>"), file=bk, parse_mode="html")
    try:
        os.remove(bk)
    except Exception:
        pass
    async with aiofiles.open("proxy.txt", "w") as f:
        await f.write("")
    await event.reply(pe(f"✅ <b>Cleared all {len(curr)} proxies!</b>"), parse_mode="html")


async def getproxy_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    curr = load_proxies()
    if not curr:
        await event.reply(pe("❌ No proxies in proxy.txt."), parse_mode="html")
        return
    if len(curr) <= 50:
        lines = "\n".join([f"{i+1}. <code>{p}</code>" for i, p in enumerate(curr)])
        await event.reply(pe(f"<b>📋 Proxies ({len(curr)}):</b>\n\n{lines}"), parse_mode="html")
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"proxies_{ts}.txt"
        async with aiofiles.open(fn, "w") as f:
            for i, p in enumerate(curr):
                await f.write(f"{i+1}. {p}\n")
        await event.reply(pe(f"<b>📋 Total Proxies: {len(curr)}</b>"), file=fn, parse_mode="html")
        try:
            os.remove(fn)
        except Exception:
            pass


async def proxy_health_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    proxies = load_proxies()
    if not proxies:
        await event.reply(pe("❌ proxy.txt is empty."), parse_mode="html")
        return

    smsg = await event.reply(pe(f"🔥 Checking {len(proxies)} proxies..."), parse_mode="html")
    alive, dead = [], []

    async def _test(raw):
        try:
            p_url = normalize_proxy(raw)
        except Exception:
            return raw, False
        try:
            timeout = aiohttp.ClientTimeout(total=12)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get("https://api.ipify.org", proxy=p_url) as r:
                    return raw, r.status == 200
        except Exception:
            return raw, False

    for i in range(0, len(proxies), 50):
        batch = proxies[i:i+50]
        results = await asyncio.gather(*[_test(p) for p in batch])
        for raw, ok in results:
            (alive if ok else dead).append(raw)
        await smsg.edit(pe(f"🔥 Checking proxies...\n✅ Alive: {len(alive)} | ❌ Dead: {len(dead)}"),
                        parse_mode="html")

    async with aiofiles.open("proxy.txt", "w") as f:
        for p in alive:
            await f.write(f"{p}\n")

    await smsg.edit(pe(f"✅ <b>Proxy Check Done!</b>\n✅ Alive: {len(alive)}\n❌ Removed: {len(dead)}"),
                    parse_mode="html")


async def getworkingproxy_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    if not os.path.exists("working_proxies.txt"):
        await event.reply(pe("❌ No working proxies saved yet."), parse_mode="html")
        return
    proxies = [ln.strip() for ln in open("working_proxies.txt") if ln.strip()]
    if not proxies:
        await event.reply(pe("❌ working_proxies.txt is empty."), parse_mode="html")
        return
    if len(proxies) <= 30:
        lines = "\n".join(f"<code>{p}</code>" for p in proxies)
        await event.reply(pe(f"<b>✅ Working Proxies ({len(proxies)}):</b>\n\n{lines}"), parse_mode="html")
    else:
        await event.reply(pe(f"<b>✅ Working Proxies: {len(proxies)}</b>"),
                          file="working_proxies.txt", parse_mode="html")


async def clearworkingproxy_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    try:
        open("working_proxies.txt", "w").close()
        await event.reply(pe("✅ <b>Working proxies list cleared.</b>"), parse_mode="html")
    except Exception as e:
        await event.reply(pe(f"❌ Error: {e}"), parse_mode="html")


async def getuserproxy_handler(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    parts = event.message.text.strip().split()
    if len(parts) < 2:
        load_user_proxies()
        from storage import user_proxies
        if not user_proxies:
            await event.reply(pe("❌ No user proxies saved."), parse_mode="html")
            return
        lines = "\n".join(f"{uid}: {proxy}" for uid, proxy in user_proxies.items())
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"user_proxies_{ts}.txt"
        with open(fn, "w") as f:
            f.write(lines)
        await event.reply(pe(f"<b>👤 User Proxies ({len(user_proxies)} users):</b>"),
                          file=fn, parse_mode="html")
        try:
            os.remove(fn)
        except Exception:
            pass
    else:
        target = int(parts[1])
        proxy = get_user_proxy(target)
        if proxy:
            await event.reply(pe(f"<b>👤 Proxy for <code>{target}</code>:</b>\n<code>{proxy}</code>"),
                              parse_mode="html")
        else:
            await event.reply(pe(f"❌ No proxy set for <code>{target}</code>."), parse_mode="html")


# ─── mandatory subscription channels ─────────────────────────────
_addsub_state = {}


async def addsub_handler(event, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return
    _addsub_state[uid] = {"step": 1}
    await event.reply(pe(
        f"<b>📢 Add Mandatory Channel — Step 1/2</b>\n"
        f"<b>{SEP}</b>\n"
        f"Forward any message from the channel you want to add ↓\n\n"
        f"• Make sure the bot is added as admin in the channel\n"
        f"• Send /cancel to abort"
    ), parse_mode="html")


async def addsub_forward_handler(event, bot, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        return
    state = _addsub_state.get(uid)
    if not state or state.get("step") != 1:
        return

    fwd = event.forward
    ch_id = None
    ch_title = ""

    try:
        if hasattr(fwd, "chat_id") and fwd.chat_id:
            ch_id = fwd.chat_id
        elif hasattr(fwd, "from_id") and fwd.from_id:
            peer = fwd.from_id
            if hasattr(peer, "channel_id"):
                ch_id = int(f"-100{peer.channel_id}")
    except Exception:
        pass

    if not ch_id:
        await event.reply(pe(
            "❌ Could not extract channel ID.\n"
            "Make sure you forwarded from a <b>channel</b>, not a group or user."
        ), parse_mode="html")
        return

    try:
        entity = await bot.get_entity(ch_id)
        ch_title = getattr(entity, "title", "") or ""
    except Exception:
        ch_title = f"Channel {ch_id}"

    channels = json.load(open("mandatory_channels.json")) if os.path.exists("mandatory_channels.json") else []
    if any(c["id"] == ch_id for c in channels):
        _addsub_state.pop(uid, None)
        await event.reply(pe(f"⚠️ Channel already exists: <b>{ch_title}</b>"), parse_mode="html")
        return

    _addsub_state[uid] = {"step": 2, "ch_id": ch_id, "ch_title": ch_title}
    await event.reply(pe(
        f"✅ <b>Channel detected:</b>\n📢 <b>{ch_title}</b>\n🆔 <code>{ch_id}</code>\n\n"
        f"<b>Now send the channel link:</b>\n<code>t.me/channelname</code>\n\n"
        f"Send /cancel to abort"
    ), parse_mode="html")


async def addsub_url_handler(event, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        return
    state = _addsub_state.get(uid)
    if not state or state.get("step") != 2:
        return

    raw = event.text.strip()
    if raw.startswith("@"):
        ch_url = f"https://t.me/{raw.lstrip('@')}"
    elif raw.startswith("t.me/") or raw.startswith("https://t.me/"):
        ch_url = raw if raw.startswith("https://") else f"https://{raw}"
    else:
        await event.reply(pe("❌ Invalid link. Send: <code>t.me/channelname</code>"), parse_mode="html")
        return

    ch_id    = state["ch_id"]
    ch_title = state["ch_title"]

    channels = json.load(open("mandatory_channels.json")) if os.path.exists("mandatory_channels.json") else []
    channels.append({"id": ch_id, "url": ch_url, "title": ch_title})
    with open("mandatory_channels.json", "w") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)
    _addsub_state.pop(uid, None)

    await event.reply(pe(
        f"✅ <b>Channel Added!</b>\n<b>{SEP}</b>\n"
        f"📢 <b>{ch_title}</b>\n🔗 {ch_url}\n🆔 <code>{ch_id}</code>"
    ), parse_mode="html")


async def cancel_handler(event):
    uid = event.sender_id
    if uid in _addsub_state:
        _addsub_state.pop(uid, None)
        await event.reply(pe("❌ <b>Operation cancelled.</b>"), parse_mode="html")


async def rmsub_handler(event, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    parts = event.message.text.strip().split()
    channels = json.load(open("mandatory_channels.json")) if os.path.exists("mandatory_channels.json") else []

    if len(parts) < 2:
        if not channels:
            await event.reply(pe("📋 No mandatory channels set."), parse_mode="html")
            return
        lines = "\n".join(f"{i+1}. <code>{c['id']}</code> — {c.get('title', '?')}"
                          for i, c in enumerate(channels))
        await event.reply(pe(f"<b>📢 Channels ({len(channels)}):</b>\n\n{lines}\n\n"
                            f"Remove: <code>/rmsub [channel_id]</code>"), parse_mode="html")
        return

    try:
        ch_id = int(parts[1])
    except ValueError:
        await event.reply(pe("❌ Invalid channel ID."), parse_mode="html")
        return

    before = len(channels)
    channels = [c for c in channels if c["id"] != ch_id]
    if len(channels) == before:
        await event.reply(pe(f"❌ Channel <code>{ch_id}</code> not found."), parse_mode="html")
        return

    with open("mandatory_channels.json", "w") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)
    await event.reply(pe(f"✅ Channel <code>{ch_id}</code> removed."), parse_mode="html")


async def listsubs_handler(event, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        await event.reply(pe("❌ <b>Admin only.</b>"), parse_mode="html")
        return

    channels = json.load(open("mandatory_channels.json")) if os.path.exists("mandatory_channels.json") else []
    if not channels:
        await event.reply(pe(
            f"<b>📢 Mandatory Subscriptions</b>\n<b>{SEP}</b>\nNo channels set.\n\n"
            f"<b>Add one:</b> <code>/addsub</code>"
        ), parse_mode="html")
        return

    lines = "\n".join(
        f"{i+1}. <a href='{c['url']}'>{c.get('title', 'Channel')}</a> — <code>{c['id']}</code>"
        for i, c in enumerate(channels)
    )
    await event.reply(pe(f"<b>📢 Channels ({len(channels)}):</b>\n\n{lines}"), parse_mode="html")


# ─── mass check runner ───────────────────────────────────────────
async def run_mass_check(bot, user_id, cards, progress_msg_id, active_sessions,
                         random_sites=False):
    session_key = f"{user_id}_{progress_msg_id}"
    active_sessions[session_key] = {"paused": False}

    all_results = {
        "charged": [], "approved": [], "dead": [], "errored": [],
        "total": len(cards), "start_time": time.time(),
        "last_card": "—", "last_resp": "—", "last_gate": "—",
        "auto_removed_sites": [],
    }

    try:
        queue = asyncio.Queue()
        for c in cards:
            queue.put_nowait(c)

        all_sites_pool = load_sites()
        site_err_count = {}
        active_sites = list(load_sites_for_user(user_id)[0] if not random_sites else all_sites_pool)

        async def worker():
            while not queue.empty() and session_key in active_sessions:
                sess = active_sessions.get(session_key)
                if not sess:
                    break
                while sess.get("paused", False):
                    await asyncio.sleep(1)
                    sess = active_sessions.get(session_key)
                    if not sess:
                        return
                try:
                    card = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                proxies = get_proxies_for_user(user_id, lambda _: False) or load_proxies()
                if random_sites and all_sites_pool:
                    cur_sites = [random.choice(all_sites_pool)]
                else:
                    cur_sites = list(active_sites) if active_sites else (load_sites_for_user(user_id)[0] or [])
                if not cur_sites:
                    break

                try:
                    res = await asyncio.wait_for(
                        check_card_with_retry(card, cur_sites, proxies, max_retries=2),
                        timeout=180,
                    )
                except asyncio.TimeoutError:
                    res = {"status": "Dead", "message": "Card check timed out",
                           "card": card, "gateway": "-", "price": "-",
                           "retry": True, "site": ""}
                except Exception as e:
                    res = {"status": "Dead", "message": str(e)[:80],
                           "card": card, "gateway": "-", "price": "-",
                           "retry": True, "site": ""}

                all_results["last_card"] = card
                all_results["last_resp"] = str(res.get("message", ""))[:50]
                all_results["last_gate"] = res.get("gateway", "—")

                res_site = res.get("site", "")
                if res_site and res.get("retry"):
                    site_err_count[res_site] = site_err_count.get(res_site, 0) + 1
                    if (site_err_count[res_site] >= 8
                            and res_site in active_sites
                            and res_site not in all_results["auto_removed_sites"]):
                        try:
                            active_sites.remove(res_site)
                        except ValueError:
                            pass
                        all_results["auto_removed_sites"].append(res_site)

                if res["status"] == "Charged":
                    all_results["charged"].append(res)
                elif res["status"] == "Approved":
                    all_results["approved"].append(res)
                elif res.get("retry"):
                    all_results["errored"].append(res)
                else:
                    all_results["dead"].append(res)

                queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(15)]
        while workers:
            if session_key not in active_sessions:
                for w in workers:
                    if not w.done():
                        w.cancel()
                break
            done, pending = await asyncio.wait(workers, timeout=1.0)
            workers = list(pending)
    finally:
        if session_key in active_sessions:
            del active_sessions[session_key]
        try:
            await asyncio.to_thread(_raw_post, f"{TG_API}/deleteMessage",
                                    {"chat_id": user_id, "message_id": progress_msg_id})
        except Exception:
            pass

        cname, cusername = await get_display_info(bot, user_id)
        record_mass_check(user_id, cname,
                          len(all_results["charged"]),
                          len(all_results["approved"]),
                          len(all_results["dead"]),
                          username=cusername)

        for r in all_results["charged"]:
            record_log(user_id, cname, cusername, r.get("card", ""), "Charged",
                       r.get("message", ""), r.get("site", ""),
                       r.get("gateway", "Shopify Payments"), r.get("price", "-"))
        for r in all_results["approved"]:
            record_log(user_id, cname, cusername, r.get("card", ""), "Approved",
                       r.get("message", ""), r.get("site", ""),
                       r.get("gateway", "Shopify Payments"), r.get("price", "-"))

        await bot.send_message(user_id, pe(
            f"✅ <b>Mass check finished</b>\n<b>{SEP}</b>\n"
            f"🔥 Charged: {len(all_results['charged'])}\n"
            f"✅ Approved: {len(all_results['approved'])}\n"
            f"❌ Dead: {len(all_results['dead'])}\n"
            f"⚠️ Errors: {len(all_results['errored'])}"
        ), parse_mode="html")