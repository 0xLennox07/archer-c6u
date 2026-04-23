"""Anomaly detection on per-device history.

For each device, compare recent behavior against a longer baseline:
  - traffic (usage bytes) z-score
  - presence hour: new-time-of-day active?
  - latency spike (rtt_ms IQR outlier)
Returns a list of anomalies as dicts.
"""
from __future__ import annotations

import statistics
import time
from typing import Iterable

from . import db as db_mod


def _safe_stats(values: Iterable[float]) -> tuple[float, float]:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return 0.0, 0.0
    return statistics.mean(vals), statistics.pstdev(vals) or 0.0


def scan(baseline_days: int = 14, recent_minutes: int = 60,
         z_threshold: float = 3.0) -> list[dict]:
    now = int(time.time())
    cutoff_base = now - baseline_days * 86400
    cutoff_recent = now - recent_minutes * 60
    out: list[dict] = []
    with db_mod.connect() as conn:
        # Traffic z-score per device.
        rows = conn.execute(
            """
            SELECT mac, MAX(hostname) AS hostname,
                   AVG(usage) AS base_mean,
                   MAX(CASE WHEN ts >= ? THEN usage ELSE NULL END) AS recent_max
            FROM device_sample
            WHERE ts >= ?
            GROUP BY mac
            """,
            (cutoff_recent, cutoff_base),
        ).fetchall()
        for r in rows:
            if r["recent_max"] is None or r["base_mean"] is None:
                continue
            vals = [x[0] for x in conn.execute(
                "SELECT usage FROM device_sample WHERE mac = ? AND ts >= ? AND ts < ?",
                (r["mac"], cutoff_base, cutoff_recent),
            ).fetchall()]
            mu, sigma = _safe_stats(vals)
            if sigma == 0:
                continue
            z = (r["recent_max"] - mu) / sigma
            if z >= z_threshold:
                out.append({
                    "kind": "traffic_spike",
                    "mac": r["mac"],
                    "hostname": r["hostname"],
                    "z_score": round(z, 2),
                    "recent_usage": r["recent_max"],
                    "baseline_mean": round(mu, 1),
                })
        # New time-of-day presence.
        hour_recent = dt_hour(now)
        pres = conn.execute(
            """
            SELECT mac, MAX(hostname) AS hostname
            FROM device_sample WHERE ts >= ? AND active = 1
            GROUP BY mac
            """, (cutoff_recent,)
        ).fetchall()
        for r in pres:
            seen_hours = [row[0] for row in conn.execute(
                "SELECT DISTINCT CAST(strftime('%H', ts, 'unixepoch','localtime') AS INTEGER) "
                "FROM device_sample WHERE mac = ? AND ts >= ? AND ts < ? AND active = 1",
                (r["mac"], cutoff_base, cutoff_recent),
            ).fetchall()]
            if seen_hours and hour_recent not in seen_hours:
                out.append({
                    "kind": "unusual_hour",
                    "mac": r["mac"],
                    "hostname": r["hostname"],
                    "hour": hour_recent,
                })
        # Latency IQR outliers.
        lat_devs = conn.execute(
            "SELECT DISTINCT mac FROM latency_sample WHERE ts >= ?", (cutoff_base,)
        ).fetchall()
        for row in lat_devs:
            mac = row["mac"]
            vals = [x["rtt_ms"] for x in conn.execute(
                "SELECT rtt_ms FROM latency_sample WHERE mac = ? AND ts >= ? AND rtt_ms IS NOT NULL",
                (mac, cutoff_base),
            ).fetchall() if x["rtt_ms"] is not None]
            if len(vals) < 8:
                continue
            vals_sorted = sorted(vals)
            q1 = vals_sorted[len(vals_sorted)//4]
            q3 = vals_sorted[(3*len(vals_sorted))//4]
            iqr = q3 - q1
            if iqr <= 0:
                continue
            high = q3 + 1.5 * iqr
            recent = [x["rtt_ms"] for x in conn.execute(
                "SELECT rtt_ms FROM latency_sample WHERE mac = ? AND ts >= ? AND rtt_ms IS NOT NULL",
                (mac, cutoff_recent),
            ).fetchall()]
            if recent and max(recent) > high:
                out.append({
                    "kind": "latency_spike",
                    "mac": mac,
                    "rtt_max": round(max(recent), 1),
                    "iqr_high": round(high, 1),
                })
    return out


def dt_hour(ts: int) -> int:
    import datetime as dt
    return dt.datetime.fromtimestamp(ts).hour
