"""Track router's public/WAN IP. Records changes to DB, fires alerts."""
from __future__ import annotations

import time

import requests

from . import db as db_mod

ENDPOINTS = (
    "https://api.ipify.org",
    "https://ifconfig.me/ip",
    "https://icanhazip.com",
)


def fetch_public_ip(timeout: float = 5.0) -> str | None:
    for url in ENDPOINTS:
        try:
            r = requests.get(url, timeout=timeout)
            if r.ok and r.text.strip():
                return r.text.strip()
        except Exception:
            continue
    return None


def check_and_record() -> dict:
    """Returns {ip, changed, previous, ts}."""
    ip = fetch_public_ip()
    if ip is None:
        return {"ip": None, "changed": False, "previous": None, "ts": int(time.time())}
    with db_mod.connect() as conn:
        prev = conn.execute("SELECT ip FROM public_ip ORDER BY ts DESC LIMIT 1").fetchone()
        previous = prev["ip"] if prev else None
        changed = previous is not None and previous != ip
        ts = int(time.time())
        if previous != ip:
            conn.execute("INSERT OR REPLACE INTO public_ip(ts, ip) VALUES (?,?)", (ts, ip))
    return {"ip": ip, "changed": changed, "previous": previous, "ts": ts}
