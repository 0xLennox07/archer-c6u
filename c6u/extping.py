"""External latency map. Pings a set of targets, records to ext_latency table."""
from __future__ import annotations

import time

from . import config as cfg_mod
from . import db as db_mod
from . import latency as latency_mod

DEFAULT_TARGETS = (
    ("cloudflare",   "1.1.1.1"),
    ("google",       "8.8.8.8"),
    ("quad9",        "9.9.9.9"),
    ("opendns",      "208.67.222.222"),
    ("google_dns2",  "8.8.4.4"),
)


EXT_SCHEMA = """
CREATE TABLE IF NOT EXISTS ext_latency (
  ts     INTEGER,
  name   TEXT,
  target TEXT,
  rtt_ms REAL,
  ok     INTEGER,
  PRIMARY KEY (ts, target)
);
CREATE INDEX IF NOT EXISTS idx_ext_lat_target ON ext_latency(target);
"""


def _ensure_schema():
    with db_mod.connect() as conn:
        conn.executescript(EXT_SCHEMA)


def probe(targets=None) -> list[dict]:
    _ensure_schema()
    cfg = cfg_mod.load_config(interactive=False)
    tgts = targets or cfg.get("ext_targets") or DEFAULT_TARGETS
    pairs = [(t, ip) if isinstance(t, str) else t for t, ip in (
        (x if isinstance(x, (tuple, list)) else (x, x)) for x in tgts)]
    ts = int(time.time())
    out = []
    with db_mod.connect() as conn:
        for name, target in pairs:
            rtt = latency_mod.ping_once(target, timeout=2.0)
            ok = rtt is not None
            conn.execute(
                "INSERT OR REPLACE INTO ext_latency VALUES (?,?,?,?,?)",
                (ts, name, target, rtt, int(ok)),
            )
            out.append({"name": name, "target": target, "rtt_ms": rtt, "ok": ok})
    return out


def series(days: int = 1, target: str | None = None) -> list[dict]:
    _ensure_schema()
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        if target:
            rows = conn.execute(
                "SELECT ts,name,target,rtt_ms,ok FROM ext_latency "
                "WHERE ts >= ? AND target = ? ORDER BY ts",
                (cutoff, target),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT ts,name,target,rtt_ms,ok FROM ext_latency WHERE ts >= ? ORDER BY ts",
                (cutoff,),
            ).fetchall()
    return [dict(r) for r in rows]
