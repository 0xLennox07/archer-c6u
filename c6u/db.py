"""SQLite snapshot logger."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshot (
  ts          INTEGER PRIMARY KEY,
  cpu         REAL,
  mem         REAL,
  wan_ip      TEXT,
  wan_uptime  INTEGER,
  clients     INTEGER,
  wired       INTEGER,
  wifi        INTEGER,
  guest       INTEGER
);

CREATE TABLE IF NOT EXISTS device_sample (
  ts         INTEGER,
  mac        TEXT,
  hostname   TEXT,
  ip         TEXT,
  type       TEXT,
  down_bps   INTEGER,
  up_bps     INTEGER,
  usage      INTEGER,
  online     INTEGER,
  active     INTEGER,
  PRIMARY KEY (ts, mac)
);
CREATE INDEX IF NOT EXISTS idx_device_mac ON device_sample(mac);

CREATE TABLE IF NOT EXISTS speedtest (
  ts        INTEGER PRIMARY KEY,
  down_mbps REAL,
  up_mbps   REAL,
  ping_ms   REAL,
  server    TEXT,
  cpu       REAL,
  mem       REAL,
  clients   INTEGER
);

CREATE TABLE IF NOT EXISTS latency_sample (
  ts       INTEGER,
  mac      TEXT,
  ip       TEXT,
  rtt_ms   REAL,
  reachable INTEGER,
  PRIMARY KEY (ts, mac)
);
CREATE INDEX IF NOT EXISTS idx_latency_mac ON latency_sample(mac);

CREATE TABLE IF NOT EXISTS public_ip (
  ts INTEGER PRIMARY KEY,
  ip TEXT
);

CREATE TABLE IF NOT EXISTS event (
  ts       INTEGER,
  kind     TEXT,
  mac      TEXT,
  payload  TEXT
);
CREATE INDEX IF NOT EXISTS idx_event_kind ON event(kind);
CREATE INDEX IF NOT EXISTS idx_event_ts   ON event(ts);
"""


@contextmanager
def connect(path: Path | str | None = None):
    if path is None:
        # read module-level so tests can monkeypatch DB_PATH
        from . import db as _self
        path = _self.DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_snapshot(status) -> int:
    ts = int(time.time())
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO snapshot VALUES (?,?,?,?,?,?,?,?,?)",
            (
                ts,
                status.cpu_usage,
                status.mem_usage,
                str(status.wan_ipv4_address) if status.wan_ipv4_address else None,
                status.wan_ipv4_uptime,
                status.clients_total,
                status.wired_total,
                status.wifi_clients_total,
                status.guest_clients_total,
            ),
        )
        for d in status.devices:
            conn.execute(
                "INSERT OR REPLACE INTO device_sample VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    ts,
                    str(d.macaddress) if d.macaddress else "",
                    d.hostname or "",
                    str(d.ipaddress) if d.ipaddress else "",
                    d.type.name if hasattr(d.type, "name") else str(d.type),
                    d.down_speed or 0,
                    d.up_speed or 0,
                    d.traffic_usage or 0,
                    int(d.online_time) if d.online_time else 0,
                    int(bool(d.active)),
                ),
            )
    return ts


def record_speedtest(result: dict) -> int:
    ts = int(time.time())
    with connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO speedtest VALUES (?,?,?,?,?,?,?,?)",
            (
                ts,
                result.get("down_mbps"),
                result.get("up_mbps"),
                result.get("ping_ms"),
                result.get("server"),
                result.get("cpu"),
                result.get("mem"),
                result.get("clients"),
            ),
        )
    return ts


def record_latency(samples: list[dict]) -> int:
    ts = int(time.time())
    with connect() as conn:
        for s in samples:
            conn.execute(
                "INSERT OR REPLACE INTO latency_sample VALUES (?,?,?,?,?)",
                (ts, s["mac"], s.get("ip"), s.get("rtt_ms"), int(bool(s.get("reachable")))),
            )
    return ts


def record_event(kind: str, mac: str | None = None, payload: str | None = None) -> int:
    ts = int(time.time())
    with connect() as conn:
        conn.execute("INSERT INTO event(ts,kind,mac,payload) VALUES (?,?,?,?)",
                     (ts, kind, mac, payload))
    return ts


def recent_events(limit: int = 100) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT ts,kind,mac,payload FROM event ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def device_history(mac: str, days: int = 7) -> dict:
    cutoff = int(time.time()) - days * 86400
    mac = mac.upper().replace("-", ":")
    with connect() as conn:
        # variants since DB stores with various separators
        candidates = [mac, mac.replace(":", "-")]
        ph = ",".join("?" for _ in candidates)
        samples = conn.execute(
            f"""SELECT ts,ip,hostname,down_bps,up_bps,usage,online,active
                FROM device_sample WHERE mac IN ({ph}) AND ts >= ?
                ORDER BY ts ASC""",
            (*candidates, cutoff),
        ).fetchall()
        latency = conn.execute(
            f"""SELECT ts,rtt_ms,reachable FROM latency_sample
                WHERE mac IN ({ph}) AND ts >= ? ORDER BY ts ASC""",
            (*candidates, cutoff),
        ).fetchall()
    return {
        "mac": mac,
        "samples": [dict(r) for r in samples],
        "latency": [dict(r) for r in latency],
    }


def history_series(days: int = 1) -> dict:
    """Time-series for the dashboard graphs."""
    cutoff = int(time.time()) - days * 86400
    with connect() as conn:
        snap = conn.execute(
            "SELECT ts,cpu,mem,clients,wired,wifi,guest FROM snapshot WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
        speed = conn.execute(
            "SELECT ts,down_mbps,up_mbps,ping_ms FROM speedtest WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
        ip = conn.execute(
            "SELECT ts,ip FROM public_ip WHERE ts >= ? ORDER BY ts ASC", (cutoff,)
        ).fetchall()
    return {
        "snapshot": [dict(r) for r in snap],
        "speedtest": [dict(r) for r in speed],
        "public_ip": [dict(r) for r in ip],
    }


def report(days: int = 7) -> dict:
    """Summary of recent activity over the last N days."""
    cutoff = int(time.time()) - days * 86400
    with connect() as conn:
        snap_cnt = conn.execute("SELECT COUNT(*) FROM snapshot WHERE ts >= ?", (cutoff,)).fetchone()[0]
        peak_clients = conn.execute(
            "SELECT MAX(clients), AVG(clients) FROM snapshot WHERE ts >= ?", (cutoff,)
        ).fetchone()
        cpu_mem = conn.execute(
            "SELECT AVG(cpu), MAX(cpu), AVG(mem), MAX(mem) FROM snapshot WHERE ts >= ?", (cutoff,)
        ).fetchone()
        per_device = conn.execute(
            """
            SELECT mac,
                   MAX(hostname) AS hostname,
                   MAX(ip)       AS ip,
                   SUM(down_bps) AS sum_down,
                   SUM(up_bps)   AS sum_up,
                   MAX(usage)    AS max_usage,
                   MAX(online)   AS max_online,
                   COUNT(*)      AS samples
            FROM device_sample
            WHERE ts >= ?
            GROUP BY mac
            ORDER BY max_usage DESC
            """,
            (cutoff,),
        ).fetchall()
        speedtests = conn.execute(
            "SELECT AVG(down_mbps), AVG(up_mbps), AVG(ping_ms), COUNT(*) FROM speedtest WHERE ts >= ?",
            (cutoff,),
        ).fetchone()
    return {
        "days": days,
        "snapshots": snap_cnt,
        "peak_clients": peak_clients[0],
        "avg_clients": peak_clients[1],
        "avg_cpu": cpu_mem[0],
        "max_cpu": cpu_mem[1],
        "avg_mem": cpu_mem[2],
        "max_mem": cpu_mem[3],
        "devices": [dict(r) for r in per_device],
        "speedtest_avg_down": speedtests[0],
        "speedtest_avg_up": speedtests[1],
        "speedtest_avg_ping": speedtests[2],
        "speedtest_count": speedtests[3],
    }
