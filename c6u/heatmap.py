"""Per-device 24x7 presence heatmaps from device_sample history."""
from __future__ import annotations

import datetime as dt
import time

from . import db as db_mod


def _normalize(mac: str) -> list[str]:
    mac_u = mac.upper().replace("-", ":")
    return [mac_u, mac_u.replace(":", "-")]


def heatmap(mac: str, days: int = 30) -> dict:
    """Returns 7x24 integer grid: counts of samples where device was active.

    Indexed as grid[dayOfWeek][hour]. dayOfWeek 0=Mon..6=Sun (Python default).
    """
    grid = [[0] * 24 for _ in range(7)]
    candidates = _normalize(mac)
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        placeholders = ",".join("?" for _ in candidates)
        rows = conn.execute(
            f"""
            SELECT ts, active FROM device_sample
             WHERE mac IN ({placeholders}) AND ts >= ?
            """,
            (*candidates, cutoff),
        ).fetchall()
    for r in rows:
        if not r["active"]:
            continue
        t = dt.datetime.fromtimestamp(r["ts"])
        grid[t.weekday()][t.hour] += 1
    return {
        "mac": mac,
        "days": days,
        "grid": grid,
        "labels_dow": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }


def heatmap_all(days: int = 30, top: int = 20) -> list[dict]:
    """Top N devices by total samples, each with its heatmap."""
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        rows = conn.execute(
            """
            SELECT mac, MAX(hostname) AS hostname, COUNT(*) AS samples
            FROM device_sample WHERE ts >= ? AND active = 1
            GROUP BY mac ORDER BY samples DESC LIMIT ?
            """,
            (cutoff, top),
        ).fetchall()
    out = []
    for r in rows:
        h = heatmap(r["mac"], days=days)
        h["hostname"] = r["hostname"]
        h["samples"] = r["samples"]
        out.append(h)
    return out
