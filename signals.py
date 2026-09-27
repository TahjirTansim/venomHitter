#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Signal lists for classifying checkout outcomes.

Three families:
  - PROXY: infrastructure failures (rotate proxy, retry)
  - SITE:  store-side problems (mark site failed, rotate site)
  - CARD:  bank-level decline (card is dead, no point retrying)
Plus positive signals: CHARGED and APPROVED (OTP / 3DS / insufficient funds).
"""

# ─── proxy is broken at the network / auth level ──────────────────
PROXY_DEAD_SIGNALS = (
    "proxy dead",
    "invalid proxy format",
    "no proxy",
    "invalid proxy",
    "proxy error",
    "proxy failed",
    "cannot connect to proxy",
    "proxy connection failed",
    "bad proxy",
    "error in 1st req",
    "error in 1 req",
    "error in 2nd req",
    "error in 2 req",
)

# tighter version used by the retry loop
PROXY_ERR_SIGNALS = (
    "proxy dead",
    "proxy failed",
    "proxy error",
    "cannot connect to proxy",
    "proxy connection failed",
    "bad proxy",
    "curl: (28)",
    "curl: (7)",
    "curl: (35)",
    "curl: (56)",
    "curl: (97)",
)

# ─── store itself is dead / misconfigured / unreachable ───────────
SITE_DEAD_SIGNALS = (
    "captcha_required",
    "captcha required",
    "site dead",
    "site errors",
    "no_session_token",
    "no session token",
    "invalid url",
    "invalid_url",
    "could not resolve",
    "domain name not found",
    "name or service not known",
    "connection failed",
    "connection refused",
    "empty reply from server",
    "tlsv1 alert",
    "ssl routines",
    "openssl ssl_connect",
    "ssl error",
    "httperror504",
    "http 404",
    "http error",
    "bad gateway",
    "service unavailable",
    "gateway timeout",
    "login required",
    "address not valid",
    "no proper json",
    "receipt id is empty",
    "handle is empty",
    "product id is empty",
    "tax amount is empty",
    "payment method identifier is empty",
    "failed to detect product",
    "failed to create checkout",
    "url rejected",
    "malformed input",
    "amount_too_small",
    "amount too small",
    "delivery_delivery_line_detail_changed",
    "delivery_address2_required",
    "all products sold out",
    "tokenize_fail",
    "site not supported",
    "all_retries_failed",
    "previously proposed price",
    "order total has changed",
    "card check timed out",
    "timeout finding product",
    "step 0 failed",
    "step 1 failed",
    "step 2 failed",
    "step 3 failed",
    "stableid missing",
)

# shorter list used by retry-loop heuristics
SITE_ERR_SIGNALS = (
    "returned 404",
    "returned 403",
    "returned 401",
    "returned 410",
    "returned 429",
    "returned 503",
    "returned 502",
    "returned 500",
    "no available products",
    "all products sold out",
    "could not extract delivery handle",
    "could not extract signedhandles",
    "signedhandles",
    "could not extract shipping",
    "missing stableid",
    "missing buildid",
    "missing sourcetoken",
    "failed to detect",
    "failed to create checkout",
    "cart permalink returned",
    "permalink returned",
    "step 0 failed",
    "step 1 failed",
    "step 2 failed",
    "step 3 failed",
)

# ─── card was rejected by the bank (Status = Dead) ────────────────
CARD_DEAD_SIGNALS = (
    "do not honor",
    "card declined",
    "card_declined",
    "declined",
    "insufficient funds",
    "insufficient_funds",
    "transaction not permitted",
    "transaction not allowed",
    "invalid card",
    "invalid_card",
    "card expired",
    "card_expired",
    "expired card",
    "lost card",
    "stolen card",
    "restricted card",
    "restricted_card",
    "security violation",
    "cvv failed",
    "cvc failed",
    "cvv2 failed",
    "card not supported",
    "card_not_supported",
    "blocked",
    "fraud",
    "generic_error",
    "payment_failed",
    "payments_card_error",
    "payments_credit_card_number_invalid",
    "payments_invalid_expiry_month",
    "payments_invalid_expiry_year",
    "payments_invalid_cvv",
    "incorrect_number",
    "invalid_number",
    "card_velocity_exceeded",
    "withdrawal_limit_exceeded",
    "call_issuer",
    "pick_up_card",
    "authentication_required",
    "pickup_card",
    "revocation_of_authorization",
)

# ─── positive signals ─────────────────────────────────────────────
CHARGED_SIGNALS = (
    "order_placed",
    "order placed",
    "processedreceipt",
    "processed_receipt",
    "payment_accepted",
    "thank you for your order",
    "your order has been placed",
    "order confirmed",
    "shopify_payments",
)

APPROVED_SIGNALS = (
    "otp_required",
    "otp required",
    "actionrequiredreceipt",
    "action_required",
    "3ds_authentication",
    "3ds authentication",
    "insufficient_funds",
    "insufficient funds",
    "authentication required",
    "redirect_to_3ds",
)


# ─── helpers ──────────────────────────────────────────────────────
def is_proxy_err(msg: str) -> bool:
    m = (msg or "").lower()
    return any(s in m for s in PROXY_ERR_SIGNALS)


def is_site_err(msg: str) -> bool:
    m = (msg or "").lower()
    return any(s in m for s in SITE_ERR_SIGNALS)


def is_card_dead(msg: str) -> bool:
    m = (msg or "").lower()
    return any(s in m for s in CARD_DEAD_SIGNALS)


def is_charged(msg: str) -> bool:
    m = (msg or "").lower()
    return any(s in m for s in CHARGED_SIGNALS)


def is_approved(msg: str) -> bool:
    m = (msg or "").lower()
    return any(s in m for s in APPROVED_SIGNALS)
