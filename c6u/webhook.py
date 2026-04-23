"""Generic event webhooks — POST JSON to one or more URLs (Zapier, Discord, Slack, IFTTT)."""
from __future__ import annotations

import json
import logging
import time

import requests

from . import db as db_mod

log = logging.getLogger(__name__)


def fire(urls: list[str], event: dict, timeout: float = 5.0) -> None:
    """Best-effort POST. Failures logged but never raised."""
    if not urls:
        return
    payload = json.dumps(event)
    for url in urls:
        try:
            requests.post(url, data=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
        except Exception as e:
            log.warning("webhook to %s failed: %s", url, e)


def emit(urls: list[str], kind: str, **fields) -> None:
    """Build a standard event envelope, fire webhooks AND record to DB."""
    event = {"kind": kind, "ts": int(time.time()), **fields}
    db_mod.record_event(kind, fields.get("mac"), json.dumps(fields))
    if urls:
        fire(urls, event)
