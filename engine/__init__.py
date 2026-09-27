#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTTP fingerprints, browser profiles, email/name pools, shipping fallback order."""

BROWSER_PROFILES = [
    "chrome124", "chrome120", "chrome116", "chrome110",
    "chrome107", "edge101", "safari15_5", "safari17_0",
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) "
    "Gecko/20100101 Firefox/123.0",
]

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "protonmail.com", "icloud.com", "aol.com", "mail.com",
    "yandex.com", "proton.me",
]

FIRST_NAMES = [
    "james", "john", "robert", "michael", "william", "david", "richard",
    "joseph", "thomas", "charles", "mary", "patricia", "jennifer", "linda",
    "elizabeth", "barbara", "susan", "jessica", "sarah", "karen",
]

LAST_NAMES = [
    "smith", "johnson", "williams", "brown", "jones", "garcia", "miller",
    "davis", "rodriguez", "martinez", "anderson", "taylor", "thomas",
    "moore", "jackson", "martin", "lee", "white", "harris", "clark",
]

# Countries tried in order when a store rejects the default US shipping address
SHIPPING_FALLBACK_ORDER = ["CA", "GB", "AU", "DE", "FR", "NL", "IE", "SE", "NO", "DK"]
