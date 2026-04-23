"""Retention policies + DB maintenance.

Config (config.json → retention):
    "retention": {
      "device_sample_days": 90,
      "latency_sample_days": 60,
      "dns_query_days": 30,
      "flow_sample_days": 14,
      "event_days": 365,
      "vacuum_on_sweep": true
    }

If no retention block is present, defaults below are used.
"""
from __future__ import annotations

import logging
import sqlite3
import time

from . import config as cfg_mod
from . import db as db_mod

log = logging.getLogger(__name__)

DEFAULTS = {
    "device_sample_days":   90,
    "latency_sample_days":  60,
    "ext_latency_days":     60,
    "speedtest_days":      365,
    "snapshot_days":        90,
    "event_days":          365,
    "dns_query_days":       30,
    "flow_sample_days":     14,
    "pdns_cache_days":     180,
    "vacuum_on_sweep":      True,
}

TABLES = (
    ("device_sample",   "device_sample_days"),
    ("latency_sample",  "latency_sample_days"),
    ("ext_latency",     "ext_latency_days"),
    ("speedtest",       "speedtest_days"),
    ("snapshot",        "snapshot_days"),
    ("event",           "event_days"),
    ("dns_query",       "dns_query_days"),
    ("flow_sample",     "flow_sample_days"),
)


def _config() -> dict:
    cfg = cfg_mod.load_config(interactive=False)
    out = dict(DEFAULTS)
    out.update((cfg.get("retention") or {}))
    return out


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def sweep() -> dict:
    cfg = _config()
    now = int(time.time())
    deleted: dict[str, int] = {}
    with db_mod.connect() as conn:
        for table, key in TABLES:
            days = int(cfg.get(key, 0) or 0)
            if days <= 0 or not _table_exists(conn, table):
                continue
            cutoff = now - days * 86400
            col = "ts"
            cur = conn.execute(f"DELETE FROM {table} WHERE {col} < ?", (cutoff,))
            deleted[table] = cur.rowcount
        # pdns_cache uses last_seen, not ts.
        if _table_exists(conn, "pdns_cache") and cfg.get("pdns_cache_days", 0) > 0:
            cutoff = now - int(cfg["pdns_cache_days"]) * 86400
            cur = conn.execute("DELETE FROM pdns_cache WHERE last_seen < ?", (cutoff,))
            deleted["pdns_cache"] = cur.rowcount
    if cfg.get("vacuum_on_sweep", True):
        vacuum()
    return {"deleted": deleted, "ts": now}


def vacuum() -> None:
    with db_mod.connect() as conn:
        conn.isolation_level = None  # VACUUM can't run inside a txn
        try:
            conn.execute("VACUUM")
        except Exception as e:
            log.warning("vacuum failed: %s", e)


def sizes() -> dict:
    """Report row counts per table for quick sanity checks."""
    with db_mod.connect() as conn:
        tables = [r["name"] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall() if not r["name"].startswith("sqlite_")]
        out = {}
        for t in tables:
            try:
                out[t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                out[t] = -1
    return out
