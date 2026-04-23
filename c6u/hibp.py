"""haveibeenpwned.com breach / password check.

Breach list by email is paywalled, so we use:
  - Pwned Passwords (free, k-anonymity, SHA1-prefix)
  - Domain-scoped breach search (paywalled; skipped unless api_key in config.hibp)

Usage:
    from c6u import hibp
    hibp.check_password("hunter2")          -> count seen
    hibp.check_email("you@example.com")     -> list[breach]  (requires api key)
"""
from __future__ import annotations

import hashlib
import logging

import requests

from . import config as cfg_mod

log = logging.getLogger(__name__)

PWN_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
BREACHED_EMAIL_URL = "https://haveibeenpwned.com/api/v3/breachedaccount/{email}?truncateResponse=false"


def check_password(password: str, timeout: float = 6.0) -> int:
    """Returns the number of times this password appears in breaches, 0 if clean."""
    sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
    prefix, suffix = sha1[:5], sha1[5:]
    try:
        r = requests.get(PWN_RANGE_URL.format(prefix=prefix),
                         headers={"Add-Padding": "true", "User-Agent": "c6u-hibp/1.0"},
                         timeout=timeout)
        r.raise_for_status()
    except Exception as e:
        log.warning("HIBP pwned-passwords fetch failed: %s", e)
        return -1
    for line in r.text.splitlines():
        s, _, count = line.partition(":")
        if s.strip().upper() == suffix:
            try:
                return int(count.strip())
            except ValueError:
                return 0
    return 0


def check_email(email: str, timeout: float = 8.0) -> list[dict] | None:
    """Requires config.json -> hibp.api_key. Returns None if not configured."""
    cfg = cfg_mod.load_config(interactive=False)
    api_key = ((cfg.get("hibp") or {}).get("api_key") or "").strip()
    if not api_key:
        return None
    try:
        r = requests.get(
            BREACHED_EMAIL_URL.format(email=email),
            headers={"hibp-api-key": api_key, "User-Agent": "c6u-hibp/1.0"},
            timeout=timeout,
        )
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        log.warning("HIBP breach fetch for %s failed: %s", email, e)
        return []


def check_config_emails() -> dict:
    """Check every email-like string in config.json."""
    cfg = cfg_mod.load_config(interactive=False)
    emails: list[str] = []
    def walk(v):
        if isinstance(v, str) and "@" in v and "." in v.split("@")[-1]:
            emails.append(v)
        elif isinstance(v, dict):
            for x in v.values(): walk(x)
        elif isinstance(v, list):
            for x in v: walk(x)
    walk(cfg)
    emails = sorted(set(emails))
    return {
        "emails": emails,
        "results": [{"email": e, "breaches": check_email(e)} for e in emails],
    }
