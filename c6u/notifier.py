"""Unified notification router with dedup / rate limit.

Every alert path — rules engine, daemon events, watchdog, anomaly loop —
should flow through `notifier.emit(kind, key, title, body, ...)` instead of
calling pushnotify / Discord / Telegram directly. That way a flapping device
can't spam you because we remember `(kind, key)` and suppress repeats inside
a cooldown window.
"""
from __future__ import annotations

import json
import time

from . import config as cfg_mod
from . import db as db_mod
from . import discordbot
from . import pushnotify as push_mod

NOTIFY_SCHEMA = """
CREATE TABLE IF NOT EXISTS notify_sent (
  kind      TEXT,
  key       TEXT,
  last_ts   INTEGER,
  count     INTEGER DEFAULT 1,
  PRIMARY KEY (kind, key)
);
CREATE INDEX IF NOT EXISTS idx_notify_last ON notify_sent(last_ts);
"""

DEFAULT_COOLDOWNS = {
    # kind → seconds between repeat alerts for the same key
    "device_joined": 300,
    "device_left": 300,
    "public_ip_changed": 60,
    "outage_started": 300,
    "outage_recovered": 60,
    "anomaly_traffic_spike": 900,
    "anomaly_unusual_hour": 3600,
    "anomaly_latency_spike": 900,
    "cve_check": 86400,
    "default": 120,
}


def _ensure_schema() -> None:
    with db_mod.connect() as conn:
        conn.executescript(NOTIFY_SCHEMA)


def _cooldown(kind: str, cfg: dict) -> int:
    overrides = ((cfg.get("notify") or {}).get("cooldowns") or {})
    if kind in overrides:
        return int(overrides[kind])
    if "default" in overrides:
        return int(overrides["default"])
    return DEFAULT_COOLDOWNS.get(kind, DEFAULT_COOLDOWNS["default"])


def should_send(kind: str, key: str, cooldown_s: int | None = None) -> bool:
    _ensure_schema()
    cfg = cfg_mod.load_config(interactive=False)
    cd = cooldown_s if cooldown_s is not None else _cooldown(kind, cfg)
    now = int(time.time())
    with db_mod.connect() as conn:
        row = conn.execute(
            "SELECT last_ts FROM notify_sent WHERE kind = ? AND key = ?",
            (kind, key or ""),
        ).fetchone()
        if row and now - row["last_ts"] < cd:
            conn.execute(
                "UPDATE notify_sent SET count = count + 1 WHERE kind = ? AND key = ?",
                (kind, key or ""),
            )
            return False
        conn.execute(
            """INSERT INTO notify_sent(kind,key,last_ts,count) VALUES (?,?,?,1)
               ON CONFLICT(kind,key) DO UPDATE
                 SET last_ts = excluded.last_ts, count = 1""",
            (kind, key or "", now),
        )
    return True


def emit(kind: str, key: str, title: str, body: str = "",
         priority: int | None = None, tags: list[str] | None = None,
         force: bool = False) -> dict:
    """Send via every configured channel, respecting (kind, key) cooldown."""
    cfg = cfg_mod.load_config(interactive=False)
    if not force and not should_send(kind, key):
        return {"sent": False, "reason": "cooldown", "kind": kind, "key": key}
    fired_push = push_mod.push(cfg.get("push"), title, body, priority=priority, tags=tags)
    sent_discord = discordbot.send_embed(title=title, description=body,
                                          fields={"kind": kind, "key": key})
    return {
        "sent": True, "kind": kind, "key": key,
        "push": fired_push, "discord": sent_discord,
    }


def recent(limit: int = 50) -> list[dict]:
    _ensure_schema()
    with db_mod.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notify_sent ORDER BY last_ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]
