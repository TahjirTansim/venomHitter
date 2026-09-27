#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""curl_cffi-based TLS client with rotating browser fingerprints."""
import random

from curl_cffi.requests import Session

from .constants import BROWSER_PROFILES, USER_AGENTS


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
            "User-Agent":                user_agent,
            "Accept-Language":           "en-US,en;q=0.9",
            "Accept-Encoding":           "gzip, deflate, br",
            "Accept":                    "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Connection":                "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest":            "document",
            "Sec-Fetch-Mode":            "navigate",
            "Sec-Fetch-Site":            "none",
            "Sec-Fetch-User":            "?1",
            "Cache-Control":             "max-age=0",
        })

    def get(self, url, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        if self.proxy_url:
            kwargs.setdefault("proxy", self.proxy_url)
        return self.session.get(url, **kwargs)

    def post(self, url, data=None, json=None, **kwargs):
        kwargs.setdefault("timeout", self.timeout)
        if self.proxy_url:
            kwargs.setdefault("proxy", self.proxy_url)
        return self.session.post(url, data=data, json=json, **kwargs)

    def close(self):
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
