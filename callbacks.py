#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Inline keyboard callback handlers."""
import asyncio
import json
import os

from config import AMOUNT_TIERS, OWNER_USERNAME
from storage import (
    get_user_amount_tier,
    get_user_proxy,
    load_proxies,
    load_premium_users,
    load_sites,
    load_sites_meta,
    remove_user_proxy,
    save_sites_meta,
    set_user_amount_tier,
    user_pool_enabled,
    save_user_pool,
)
from keys import (
    all_keys,
    all_user_access,
    get_user_limit,
    get_user_tier,
    is_access_valid,
    keys_summary,
    time_remaining,
)
from emojis import pe
from branding import SEP, dev_line, fi
from ui import (
    nav_edit,
    raw_edit,
    rows_amount_select,
    rows_admin,
    rows_admin_users,
    rows_admin_sites,
    rows_admin_proxy_pool,
    rows_admin_keys,
    rows_gates,
    rows_main,
    rows_proxy,
    rows_stop,
)


# ─── shared panel text builders ──────────────────────────────────
def _admin_panel_text():
    pcount = len(load_premium_users()) + len(all_user_access())
    ksum   = keys_summary()
    return pe(
        f"<b>👑 Admin Panel</b>\n"
        f"<b>{SEP}</b>\n"
        f"👤 <b>Total Users:</b> {pcount}\n"
        f"🌐 <b>Sites:</b> {len(load_sites())}\n"
        f"⚙️ <b>Proxy Pool:</b> {len(load_proxies())}\n"
        f"🔑 <b>Keys:</b> {ksum['total']} total | {ksum['unused']} unused\n"
        f"<b>{SEP}</b>\n"
        f"{dev_line()}"
    )


def _start_panel_text(bot_entity, uid, is_admin_fn):
    firstname = "User"
    username  = f"ID:{uid}"
    if bot_entity:
        firstname = bot_entity.first_name or "User"
        username  = f"@{bot_entity.username}" if bot_entity.username else f"ID:{uid}"

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

    return pe(
        f"<b>Speedy Hitter</b>\n"
        f"<b>{SEP}</b>\n"
        f"👤 <b>User:</b> {firstname}\n"
        f"🔗 <b>Handle:</b> {username}\n"
        f"🆔 <b>ID:</b> <code>{uid}</code>\n"
        f"<b>{SEP}</b>\n"
        f"⚡ <b>Status:</b> {status_line}\n"
        f"📋 <b>Limit:</b> {lim if lim else 'N/A'} cards/file\n"
        f"<b>{SEP}</b>\n"
        f"{dev_line()}"
    )


def _main_rows_for(uid, is_admin_fn):
    if is_admin_fn(uid):
        return [
            [{"text": "🏧  Gates",       "callback_data": "gates"},
             {"text": "👑  Admin Panel", "callback_data": "admin_panel"}],
            [{"text": "💙  Contact", "url": f"https://t.me/{OWNER_USERNAME}"},
             {"text": "❌  Close",   "callback_data": "close"}],
        ]
    return rows_main()


# ─── gates / amount ──────────────────────────────────────────────
async def cb_gates(event, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.answer("❌ Premium required!", alert=True)
        return
    text = pe(
        f"<b>💎 Shopify Gateway</b>\n\n"
        f"⚡ <b>Single Check</b>\n"
        f"<code>/sh card|mm|yy|cvv</code>\n\n"
        f"⚡ <b>Mass Check</b>\n"
        f"Reply to .txt with <code>/msh</code>\n"
        f"— or <b>send a .txt file directly!</b>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_gates())


async def cb_amount_select(event, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.answer("❌ Premium required!", alert=True)
        return
    await event.answer()
    cur   = get_user_amount_tier(uid)
    label = AMOUNT_TIERS.get(cur, ("Any",))[0]
    meta  = load_sites_meta()
    sites = load_sites()
    tagged = {t: sum(1 for s in sites if meta.get(s, {}).get("tier") == t)
              for t in AMOUNT_TIERS if t != "any"}
    lines = "\n".join(f"  {v[0]}: {tagged.get(k, 0)} tagged sites"
                      for k, v in AMOUNT_TIERS.items() if k != "any")
    text = pe(
        f"<b>💰 Amount Filter</b>\n"
        f"<b>{SEP}</b>\n"
        f"Current: <b>{label}</b>\n\n"
        f"<b>Available tiers:</b>\n{lines}\n\n"
        f"<i>Select a tier — checker will only use sites tagged for that price.</i>"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_amount_select(cur))


async def cb_amount_tier(event, is_premium_fn):
    uid  = event.sender_id
    if not is_premium_fn(uid):
        await event.answer("❌ Premium required!", alert=True)
        return
    tier = event.data.decode().split("amount_tier_", 1)[1]
    if tier not in AMOUNT_TIERS:
        await event.answer("❌ Invalid tier", alert=True)
        return
    set_user_amount_tier(uid, tier)
    label = AMOUNT_TIERS[tier][0]
    meta  = load_sites_meta()
    sites = load_sites()
    tagged = sum(1 for s in sites if meta.get(s, {}).get("tier") == tier) if tier != "any" else len(sites)
    if tagged == 0 and tier != "any":
        await event.answer(f"⚠️ No sites tagged as {label} yet", alert=True)
    else:
        await event.answer(f"✅ {label} — {tagged} sites will be used", alert=False)
    cur   = get_user_amount_tier(uid)
    cur_label = AMOUNT_TIERS.get(cur, ("Any",))[0]
    tagged_count = {t: sum(1 for s in sites if meta.get(s, {}).get("tier") == t)
                    for t in AMOUNT_TIERS if t != "any"}
    lines = "\n".join(f"  {v[0]}: {tagged_count.get(k, 0)} sites"
                      for k, v in AMOUNT_TIERS.items() if k != "any")
    active_count = tagged_count.get(cur, len(sites)) if cur != "any" else len(sites)
    status_line = (
        f"⚠️ <b>0 sites tagged as {cur_label}</b> — checks will fail until admin tags sites.\n"
        if active_count == 0 and cur != "any"
        else f"✅ Checks will run on <b>{active_count} {cur_label} site{'s' if active_count != 1 else ''}</b>.\n"
    )
    text = pe(
        f"<b>💰 Amount Filter</b>\n"
        f"<b>{SEP}</b>\n"
        f"Selected: <b>{cur_label}</b>\n"
        f"{status_line}\n"
        f"<b>Tagged sites per tier:</b>\n{lines}\n\n"
        f"<i>Tap a tier to switch.</i>"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_amount_select(cur))


# ─── proxy panel ─────────────────────────────────────────────────
async def cb_manage_proxy(event, is_premium_fn):
    uid = event.sender_id
    if not is_premium_fn(uid):
        await event.answer("❌ Premium required!", alert=True)
        return
    user_proxy = get_user_proxy(uid)
    pool       = load_proxies()
    if user_proxy:
        proxy_status = f"✅ <b>Your Proxy:</b>\n<blockquote><code>{user_proxy}</code></blockquote>"
    else:
        proxy_status = f"❌ <b>No Personal Proxy Set</b>"

    text = pe(
        f"<b>🔌 Proxy Settings</b>\n"
        f"<b>{SEP}</b>\n"
        f"{proxy_status}\n\n"
        f"📋 <b>Pool:</b> {len(pool)} proxies\n"
        f"<b>{SEP}</b>\n"
        f"<b>👩‍💻 Set Your Proxy:</b>\n"
        f"<code>/setproxy ip:port</code>\n"
        f"<code>/setproxy ip:port:user:pass</code>\n"
        f"<code>/setproxy socks5://ip:port</code>\n"
        f"<code>/setproxy http://user:pass@ip:port</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(user_pool_enabled.get(uid, True)))


async def cb_toggle_pool(event):
    uid     = event.sender_id
    current = user_pool_enabled.get(uid, True)
    user_pool_enabled[uid] = not current
    save_user_pool()
    state = "ON ✅" if not current else "OFF 🚀"
    await event.answer(f"Proxy Pool {state}", alert=False)

    user_proxy = get_user_proxy(uid)
    pool       = load_proxies()
    if user_proxy:
        proxy_status = f"✅ <b>Your Proxy:</b>\n<blockquote><code>{user_proxy}</code></blockquote>"
    else:
        proxy_status = f"❌ <b>No Personal Proxy Set</b>"

    text = pe(
        f"<b>🔌 Proxy Settings</b>\n"
        f"<b>{SEP}</b>\n"
        f"{proxy_status}\n\n"
        f"📋 <b>Pool:</b> {len(pool)} proxies\n"
        f"<b>{SEP}</b>\n"
        f"<b>👩‍💻 Set Your Proxy:</b>\n"
        f"<code>/setproxy ip:port</code>\n"
        f"<code>/setproxy ip:port:user:pass</code>\n"
        f"<code>/setproxy socks5://ip:port</code>\n"
        f"<code>/setproxy http://user:pass@ip:port</code>"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_proxy(user_pool_enabled.get(uid, True)))


async def cb_test_proxy(event):
    uid   = event.sender_id
    proxy = get_user_proxy(uid)
    if not proxy:
        proxies = load_proxies()
        if not proxies:
            await event.answer("❌ No proxies to test!", alert=True)
            return
        proxy = proxies[0]
    await event.answer("⚡ Testing proxy...", alert=False)

    from storage import normalize_proxy
    from ui import raw_send
    try:
        p_url = normalize_proxy(proxy)
    except Exception:
        p_url = None

    import aiohttp
    ip = None
    if p_url:
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get("https://api.ipify.org", proxy=p_url) as r:
                    if r.status == 200:
                        ip = (await r.text()).strip()
        except Exception:
            pass

    if ip:
        await raw_send(uid, pe(f"<b>Proxy Test:</b>\n✅ ALIVE\n🌐 IP: <code>{ip}</code>\n<code>{proxy}</code>"), [])
    else:
        await raw_send(uid, pe(f"<b>Proxy Test:</b>\n❌ DEAD\n<code>{proxy}</code>"), [])


async def cb_remove_proxy(event):
    uid = event.sender_id
    user_proxy = get_user_proxy(uid)
    if user_proxy:
        remove_user_proxy(uid)
        await event.answer("✅ Your proxy removed!", alert=False)
        from ui import raw_send
        await raw_send(uid, pe(f"🗑️ <b>Your proxy removed:</b>\n<code>{user_proxy}</code>"), [])
        return
    proxies = load_proxies()
    if not proxies:
        await event.answer("❌ No proxies!", alert=True)
        return
    removed = proxies[0]
    import aiofiles
    async with aiofiles.open("proxy.txt", "w") as f:
        for p in proxies[1:]:
            await f.write(f"{p}\n")
    await event.answer("✅ Removed!", alert=False)
    from ui import raw_send
    await raw_send(uid, pe(f"🗑️ <b>Proxy removed from pool:</b>\n<code>{removed}</code>"), [])


# ─── back / close ────────────────────────────────────────────────
async def cb_back_start(event, bot, is_admin_fn):
    uid = event.sender_id
    try:
        sender = await bot.get_entity(uid)
    except Exception:
        sender = None
    text = _start_panel_text(sender, uid, is_admin_fn)
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, _main_rows_for(uid, is_admin_fn))


async def cb_close(event):
    try:
        await event.delete()
    except Exception:
        await event.answer("✅ Closed")


# ─── admin panels ────────────────────────────────────────────────
async def cb_admin_panel(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, _admin_panel_text(), rows_admin())


async def cb_admin_users(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    pcount = len(load_premium_users()) + len(all_user_access())
    text = pe(
        f"<b>👑 User Management</b>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Total Users:</b> {pcount}\n"
        f"<b>Access Users:</b> {len(all_user_access())}\n"
        f"<b>Legacy Premium:</b> {len(load_premium_users())}\n"
        f"<b>{SEP}</b>\n"
        f"<b>Commands:</b>\n"
        f"<code>/authuser [ID] [days]</code>\n"
        f"<code>/deauthuser [ID]</code>\n"
        f"<code>/userstatus</code>\n"
        f"<code>/addpremium [ID]</code>\n"
        f"<code>/rmpremium [ID]</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_users())


async def cb_admin_sites(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    text = pe(
        f"<b>🌐 Site Management</b>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Total Sites:</b> {len(load_sites())}\n"
        f"<b>{SEP}</b>\n"
        f"<b>Commands:</b>\n"
        f"<code>/addsite [url]</code>\n"
        f"<code>/rmsite [url]</code>\n"
        f"<code>/listsites</code>\n"
        f"<code>/site</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_sites())


async def cb_admin_proxy_pool(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    pool = load_proxies()
    sample = pool[0] if pool else "None"
    text = pe(
        f"<b>⚙️ Proxy Pool Management</b>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Pool Size:</b> {len(pool)} proxies\n"
        f"<b>Sample:</b> <code>{sample}</code>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Commands:</b>\n"
        f"<code>/addproxy [proxy]</code>\n"
        f"<code>/rmproxy [proxy]</code>\n"
        f"<code>/clearproxy</code>\n"
        f"<code>/getproxy</code>\n"
        f"<code>/proxy</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_proxy_pool())


async def cb_admin_keys(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    ksum = keys_summary()
    text = pe(
        f"<b>🔑 Key Manager</b>\n"
        f"<b>{SEP}</b>\n"
        f"🟢 <b>Unused Keys:</b> {ksum['unused']}\n"
        f"🔴 <b>Used Keys:</b> {ksum['used']}\n"
        f"📋 <b>Total Keys:</b> {ksum['total']}\n"
        f"<b>{SEP}</b>\n"
        f"<b>Commands:</b>\n"
        f"<code>/genkeys [count] [days]</code>\n"
        f"<code>/listkeys</code>\n"
        f"<code>/delkey [key]</code>"
    )
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_keys())


async def cb_admin_user_status(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("📊 Use /userstatus for the full report.", alert=False)


async def cb_admin_broadcast_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    total = len(load_premium_users()) + len(all_user_access())
    await event.answer(f"📡 Send: /broadcast [message]\nWill reach {total} users.", alert=True)


async def cb_admin_list_users(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    lines = []
    for uid_str, acc in list(all_user_access().items())[:30]:
        tier  = acc.get("tier", "?")
        trem  = time_remaining(int(uid_str)) or "Expired"
        valid = "✅" if is_access_valid(int(uid_str)) else "❌"
        lines.append(f"{valid} <code>{uid_str}</code> — {tier} | {trem}")
    for u in load_premium_users()[:10]:
        lines.append(f"⭐ <code>{u}</code> — Legacy Premium")
    if not lines:
        await event.answer("📋 No users found.", alert=True)
        return
    text = pe(f"<b>👑 Users ({len(all_user_access()) + len(load_premium_users())}):</b>\n\n" + "\n".join(lines))
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_users())


async def cb_admin_list_sites(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    sites = load_sites()
    if not sites:
        await event.answer("📋 No sites.", alert=True)
        return
    lines = "\n".join([f"{i+1}. <code>{s}</code>" for i, s in enumerate(sites[:30])])
    note  = f"\n<i>...and {len(sites)-30} more.</i>" if len(sites) > 30 else ""
    text  = pe(f"<b>🌐 Sites ({len(sites)}):</b>\n\n{lines}{note}\n\n<b>{SEP}</b>\n{dev_line()}")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_sites())


async def cb_admin_list_proxy(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    pool = load_proxies()
    if not pool:
        await event.answer("📋 Pool is empty.", alert=True)
        return
    lines = "\n".join([f"{i+1}. <code>{p}</code>" for i, p in enumerate(pool[:20])])
    note  = f"\n<i>...and {len(pool)-20} more.</i>" if len(pool) > 20 else ""
    text  = pe(f"<b>⚙️ Proxy Pool ({len(pool)}):</b>\n\n{lines}{note}\n\n<b>{SEP}</b>\n{dev_line()}")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_proxy_pool())


async def cb_admin_genkeys_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("🔑 Send: /genkeys [count] [days]\nExample: /genkeys 5 30", alert=True)


async def cb_admin_list_keys(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    kd = all_keys()
    unused = [(k, v) for k, v in kd.items() if v.get("redeemed_by") is None][:15]
    if not unused:
        await event.answer("📋 No unused keys.", alert=True)
        return
    lines = "\n".join([f"🟢 <code>{k}</code> — {v.get('plan_days','?')}d" for k, v in unused])
    text  = pe(f"<b>🔑 Unused Keys ({len(unused)}):</b>\n\n{lines}\n\n<b>{SEP}</b>\n{dev_line()}")
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_keys())


async def cb_admin_delkey_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("🔥 Send: /delkey [key_string]", alert=True)


async def cb_admin_add_user_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("✅ Send: /authuser [user_id] [days]", alert=True)


async def cb_admin_rm_user_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("🔥 Send: /deauthuser [user_id]", alert=True)


async def cb_admin_add_site_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("✅ Send: /addsite [url]", alert=True)


async def cb_admin_rm_site_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("🔥 Send: /rmsite [url]", alert=True)


async def cb_admin_add_proxy_info(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    await event.answer("✅ Send: /addproxy [ip:port or ip:port:user:pass]", alert=True)


async def cb_admin_clear_proxy(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    try:
        import aiofiles
        async with aiofiles.open("proxy.txt", "w") as f:
            await f.write("")
        await event.answer("🔥 Proxy pool cleared!", alert=True)
    except Exception:
        await event.answer("❌ Failed to clear pool.", alert=True)
    pool = load_proxies()
    text = pe(
        f"<b>⚙️ Proxy Pool Management</b>\n"
        f"<b>{SEP}</b>\n"
        f"<b>Pool Size:</b> {len(pool)} proxies\n"
        f"<b>{SEP}</b>"
    )
    await nav_edit(event.chat_id, event.message_id, text, rows_admin_proxy_pool())


# ─── mandatory sub inline ────────────────────────────────────────
EM_SUB_PANEL = '<tg-emoji emoji-id="6266818250818983044">A</tg-emoji>'
EM_SUB_ADD   = '<tg-emoji emoji-id="6267115986541877538">*</tg-emoji>'


def _mandatory_sub_text_and_rows():
    channels = json.load(open("mandatory_channels.json")) if os.path.exists("mandatory_channels.json") else []
    if channels:
        ch_lines = "\n".join(
            f"  {i+1}. <a href='{c['url']}'>{c.get('title', '?')}</a> — <code>{c['id']}</code>"
            for i, c in enumerate(channels)
        )
        status = f"✅ <b>Active — {len(channels)} channel(s):</b>\n{ch_lines}"
    else:
        status = "❌ <b>Disabled</b> — No channels set"
    text = pe(f"{EM_SUB_PANEL} <b>Mandatory Subscription</b>\n<b>{SEP}</b>\n{status}\n<b>{SEP}</b>")
    rows = []
    for c in channels:
        rows.append([{"text": f"🗑  Remove: {c.get('title', 'Channel')}",
                      "callback_data": f"rmsub_{c['id']}"}])
    rows.append([{"text": "  Add Channel  ", "callback_data": "addsub_start"}])
    rows.append([{"text": "↪️  Back", "callback_data": "admin_panel"}])
    return text, rows


async def cb_admin_mandatory_sub(event, is_admin_fn):
    if not is_admin_fn(event.sender_id):
        await event.answer("❌ Admin only!", alert=True)
        return
    text, rows = _mandatory_sub_text_and_rows()
    await event.answer()
    await nav_edit(event.chat_id, event.message_id, text, rows)


async def cb_addsub_start(event, bot, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        await event.answer("❌ Admin only!", alert=True)
        return
    from handlers_admin import _addsub_state
    _addsub_state[uid] = {"step": 1}
    await event.answer()
    await bot.send_message(uid, pe(
        f"{EM_SUB_ADD} <b>Add Channel — Step 1/2</b>\n"
        f"<b>{SEP}</b>\n"
        f"Forward any message from the channel you want to add ↓\n\n"
        f"Send /cancel to abort"
    ), parse_mode="html")


async def cb_rmsub_inline(event, is_admin_fn):
    uid = event.sender_id
    if not is_admin_fn(uid):
        await event.answer("❌ Admin only!", alert=True)
        return
    ch_id    = int(event.data.decode().split("rmsub_", 1)[1])
    channels = json.load(open("mandatory_channels.json")) if os.path.exists("mandatory_channels.json") else []
    target   = next((c for c in channels if c["id"] == ch_id), None)
    if not target:
        await event.answer("⚠️ Channel not found!", alert=True)
        return
    channels = [c for c in channels if c["id"] != ch_id]
    with open("mandatory_channels.json", "w") as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)
    await event.answer(f"✅ Removed: {target.get('title', 'Channel')}", alert=False)
    text, rows = _mandatory_sub_text_and_rows()
    await nav_edit(event.chat_id, event.message_id, text, rows)


# ─── mass check stop ─────────────────────────────────────────────
async def cb_stop_mass(event, active_sessions):
    uid = event.sender_id
    sk  = f"{uid}_{event.message_id}"
    if sk in active_sessions:
        del active_sessions[sk]
        await event.answer("🛑 Stopping...")
        try:
            await event.edit(pe("🚫 <b>Check stopped by user.</b>"), parse_mode="html")
        except Exception:
            pass
    else:
        await event.answer("Already stopped.", alert=False)