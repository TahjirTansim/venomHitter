#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regex / HTML-unescaping token extractors.

Every extractor here is &quot;-tolerant: Shopify embeds a lot of state
inside <meta content="..."> attributes where quotes get HTML-escaped,
and inside <script> blobs where they get backslash-escaped.
"""
import html
import json
import re
from typing import List


def _try(pattern: str, text: str) -> str:
    """Return first capture group, or empty string."""
    if not text:
        return ""
    m = re.search(pattern, text)
    return m.group(1) if m else ""


def extract_between(text: str, start: str, end: str):
    """Plain substring slice. Returns None on miss, not an exception."""
    if not text or not start or not end:
        return None
    try:
        if start in text:
            parts = text.split(start, 1)
            if len(parts) > 1 and end in parts[1]:
                return parts[1].split(end, 1)[0] or None
        return None
    except Exception:
        return None


# ─── checkout page tokens ─────────────────────────────────────────

def extract_session_token(checkout_html: str) -> str:
    m = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"', checkout_html)
    if m:
        return html.unescape(m.group(1)).strip('"')
    m = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="&quot;([^&]+)&quot;"', checkout_html)
    return m.group(1) if m else ""


def extract_source_token(checkout_html: str) -> str:
    m = re.search(r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"', checkout_html)
    if m:
        return html.unescape(m.group(1)).strip('"')
    m = re.search(r'<meta\s+name="serialized-sourceToken"\s+content="&quot;([^&]+)&quot;"', checkout_html)
    return m.group(1) if m else ""


def extract_private_access_token_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    m = re.search(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"', unescaped)
    if m:
        return m.group(1)
    return _try(r'&quot;checkoutSessionIdentifier&quot;:&quot;([a-f0-9]+)&quot;', checkout_html)


def extract_stable_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    m = re.search(
        r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
        unescaped)
    if m:
        return m.group(1)
    return _try(
        r'&quot;stableId&quot;:&quot;([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})&quot;',
        checkout_html)


def extract_commit_sha(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    m = re.search(r'"commitSha"\s*:\s*"([a-f0-9]{40})"', unescaped)
    if m:
        return m.group(1)
    return _try(r'&quot;commitSha&quot;:&quot;([a-f0-9]{40})&quot;', checkout_html)


def extract_queue_token(proposal_json: str) -> str:
    unescaped = html.unescape(proposal_json)
    m = re.search(r'"queueToken"\s*:\s*"([^"]+)"', unescaped)
    if m:
        return m.group(1)
    return _try(r'&quot;queueToken&quot;:&quot;([^&]+)&quot;', proposal_json)


def extract_identification_signature(checkout_html: str) -> str:
    unescaped = checkout_html.replace("&quot;", '"')
    for pattern in (
        r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"',
        r'CardsinkCallerIdentificationSignature":"([^"]+)"',
        r'cardsinkCallerIdentificationSignature":"([^"]+)"',
        r'"identification_signature"\s*:\s*"([^"]+)"',
    ):
        m = re.search(pattern, unescaped)
        if m:
            return m.group(1)
    return ""


def extract_vault_url(checkout_html: str) -> str:
    decoded = checkout_html.replace("&quot;", '"')
    m = re.search(r'(https://[a-z0-9._-]*(?:shopifycs|shopifyinc)\.[a-z.]+/sessions)', decoded)
    if m:
        return m.group(1)
    hf = re.search(r'"hostedFields"[^}]*"url"\s*:\s*"(https://[^"]+)"', decoded)
    if hf:
        return hf.group(1).rsplit("/", 2)[0] + "/sessions"
    return ""


def extract_vault_domain(checkout_html: str) -> str:
    decoded = checkout_html.replace("&quot;", '"')
    return _try(r'hostedFieldsUrl[^}]+"domain"\s*:\s*"([^"]+)"', decoded)


# ─── proposal response tokens ─────────────────────────────────────

def extract_is_shipping_required(proposal_json: str) -> bool:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        return seller.get("isShippingRequired", True)
    except Exception:
        return True


def extract_running_total(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        return (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("runningTotal", {})
                    .get("value", {})
                    .get("amount", ""))
    except Exception:
        return ""


def extract_delivery_handle(proposal_body: str) -> str:
    try:
        data   = json.loads(proposal_body)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        sds = seller.get("selectedDeliveryStrategy", {})
        if isinstance(sds, dict) and sds.get("handle"):
            return sds["handle"]
        de = seller.get("deliveryExpectations", {})
        if isinstance(de, dict):
            for exp in de.get("deliveryExpectations", []):
                if isinstance(exp, dict) and exp.get("handle"):
                    return exp["handle"]
        for dg in seller.get("deliveryGroups", []):
            if isinstance(dg, dict):
                for opt in dg.get("deliveryOptions", []):
                    if isinstance(opt, dict) and opt.get("handle"):
                        return opt["handle"]
    except Exception:
        pass

    for pattern in (
        r'"selectedDeliveryStrategy"\s*:\s*\{[^{}]*"handle"\s*:\s*"([^"]+)"',
        r'"handle"\s*:\s*"([^"]+)"[^}]{0,120}"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        r'"__typename"\s*:\s*"CompleteDeliveryStrategy"[^}]{0,120}"handle"\s*:\s*"([^"]+)"',
        r'"handle"\s*:\s*"([A-Za-z0-9+/=_\-]{20,})"',
    ):
        m = re.search(pattern, proposal_body)
        if m:
            return m.group(1)
    return ""


def extract_signed_handles(proposal_json: str) -> List[str]:
    try:
        data   = json.loads(proposal_json)
        seller = (data.get("data", {})
                      .get("session", {})
                      .get("negotiate", {})
                      .get("result", {})
                      .get("sellerProposal", {}))
        de          = seller.get("deliveryExpectations", {})
        de_typename = de.get("__typename", "")

        if de_typename == "FilledDeliveryExpectationTerms":
            return [x["signedHandle"] for x in de.get("deliveryExpectations", []) if x.get("signedHandle")]

        if "deliveryExpectations" in de:
            exp = de.get("deliveryExpectations", [])
            if isinstance(exp, list):
                handles = [x.get("signedHandle") for x in exp if x.get("signedHandle")]
                if handles:
                    return handles

        if de_typename in ("UnfilledDeliveryExpectationTerms", "UnavailableTerms"):
            return []
    except Exception:
        pass
    return []


def extract_tax_amount(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        return (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("tax", {})
                    .get("totalTaxAmount", {})
                    .get("value", {})
                    .get("amount", "0.0"))
    except Exception:
        return "0.0"


def extract_pci_session_id(pci_body: str) -> str:
    return _try(r'"id"\s*:\s*"([^"]+)"', pci_body)


# ─── submit / poll response tokens ────────────────────────────────

def extract_receipt_id(submit_body: str) -> str:
    return _try(r'"id"\s*:\s*"(gid://shopify/\w+Receipt/[A-Za-z0-9]+)"', submit_body)


def extract_receipt_session_token(submit_body: str) -> str:
    return _try(r'"sessionToken"\s*:\s*"([^"]+)"', submit_body)


def extract_any_error(submit_body: str) -> str:
    for pattern in (
        r'"nonLocalizedMessage"\s*:\s*"([^"]+)"',
        r'"localizedMessage"\s*:\s*"([^"]+)"',
        r'"code"\s*:\s*"([^"]+)"',
        r'"message"\s*:\s*"([^"]+)"',
    ):
        m = re.search(pattern, submit_body)
        if m:
            return m.group(1)
    return ""


def detect_shipping_restriction(proposal_body: str) -> bool:
    signals = (
        "SHIPPING_ADDRESS_UNDELIVERABLE",
        "no_delivery_options_available",
        "noDeliveryOptionsAvailable",
        "delivery is not available",
        "does not ship to",
    )
    lower = (proposal_body or "").lower()
    return any(s.lower() in lower for s in signals)


def is_captcha_required(response_text: str) -> bool:
    if not response_text:
        return False
    upper = response_text.upper()
    return any(ind.upper() in upper for ind in (
        "CAPTCHA_REQUIRED",
        '"CODE":"CAPTCHA_REQUIRED"',
        "'CODE':'CAPTCHA_REQUIRED'",
        '"MESSAGE":"CAPTCHA_REQUIRED"',
        "CAPTCHA REQUIRED",
        "CAPTCHA CHALLENGE",
        "HCAPTCHA",
        "H-CAPTCHA",
    ))
