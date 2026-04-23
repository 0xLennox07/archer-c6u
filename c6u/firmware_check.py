"""Compare current router firmware version to TP-Link's published download page."""
from __future__ import annotations

import re

import requests

UA = "Mozilla/5.0 (compatible; c6u/0.3)"


def latest_for_model(model: str, region: str = "us") -> str | None:
    """Best-effort scrape of the TP-Link download page.

    Returns the most recent firmware version string we can find, or None.
    Note: TP-Link's site layout changes; if this stops working, just use the
    URL printed by `firmware-check --url` to eyeball it manually.
    """
    slug = model.lower().replace(" ", "-")
    url = f"https://www.tp-link.com/{region}/support/download/{slug}/"
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=10)
        if not r.ok:
            return None
        m = re.search(r"(\d+\.\d+\.\d+\s+Build\s+\d+)", r.text)
        return m.group(1) if m else None
    except Exception:
        return None


def published_url(model: str, region: str = "us") -> str:
    slug = model.lower().replace(" ", "-")
    return f"https://www.tp-link.com/{region}/support/download/{slug}/"
