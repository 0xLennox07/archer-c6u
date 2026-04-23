"""Discord integration — outgoing-only (webhook-based) for simplicity.

Config (config.json):
    "discord": {"webhook": "https://discord.com/api/webhooks/..."}

Functions:
    send_text(text)
    send_embed(title, description, fields={})
    alert_on_event(event)    # one-liner used by rules/daemon
"""
from __future__ import annotations

import logging

import requests

from . import config as cfg_mod

log = logging.getLogger(__name__)


def _webhook() -> str | None:
    cfg = cfg_mod.load_config(interactive=False)
    return ((cfg.get("discord") or {}).get("webhook") or "").strip() or None


def send_text(text: str) -> bool:
    url = _webhook()
    if not url:
        return False
    try:
        r = requests.post(url, json={"content": text[:1900]}, timeout=6)
        return r.ok
    except Exception as e:
        log.warning("discord send failed: %s", e)
        return False


def send_embed(title: str, description: str = "", fields: dict | None = None,
               color: int = 0x5865F2) -> bool:
    url = _webhook()
    if not url:
        return False
    embed = {"title": title[:255], "description": description[:2000], "color": color}
    if fields:
        embed["fields"] = [{"name": str(k)[:255], "value": str(v)[:1023], "inline": True}
                           for k, v in fields.items()]
    try:
        r = requests.post(url, json={"embeds": [embed]}, timeout=6)
        return r.ok
    except Exception as e:
        log.warning("discord send failed: %s", e)
        return False


def alert_on_event(event: dict) -> bool:
    kind = event.get("kind", "event")
    title = {
        "device_joined": "Device joined",
        "device_left": "Device left",
        "public_ip_changed": "Public IP changed",
        "outage_started": "Internet outage",
        "outage_recovered": "Internet recovered",
    }.get(kind, kind)
    fields = {k: v for k, v in event.items() if k not in ("kind", "ts") and v not in (None, "")}
    return send_embed(title=title, description=kind, fields=fields)
