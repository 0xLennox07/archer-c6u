"""ISP SLA report. Config (config.json):

    "isp": {"down_mbps": 200, "up_mbps": 20, "provider": "Jio Fiber"}
"""
from __future__ import annotations

import statistics
import time

from . import config as cfg_mod
from . import db as db_mod


def _percentile(values, p):
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * (p / 100)
    lo = int(k)
    hi = min(lo + 1, len(values) - 1)
    frac = k - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def report(days: int = 30) -> dict:
    cfg = cfg_mod.load_config(interactive=False)
    isp = cfg.get("isp") or {}
    contract_down = isp.get("down_mbps")
    contract_up = isp.get("up_mbps")

    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        rows = conn.execute(
            "SELECT ts, down_mbps, up_mbps, ping_ms FROM speedtest WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()
    downs = [r["down_mbps"] for r in rows if r["down_mbps"] is not None]
    ups = [r["up_mbps"] for r in rows if r["up_mbps"] is not None]
    pings = [r["ping_ms"] for r in rows if r["ping_ms"] is not None]

    def agg(vals):
        if not vals:
            return {"count": 0}
        return {
            "count": len(vals),
            "min": min(vals),
            "max": max(vals),
            "mean": statistics.mean(vals),
            "median": statistics.median(vals),
            "p10": _percentile(vals, 10),
            "p95": _percentile(vals, 95),
        }

    out = {
        "days": days, "contract": isp,
        "samples": len(rows),
        "down_mbps": agg(downs), "up_mbps": agg(ups), "ping_ms": agg(pings),
    }
    if contract_down and downs:
        out["down_percent_of_contract"] = (statistics.mean(downs) / contract_down) * 100
        out["down_sla_met_percent"] = 100 * sum(1 for v in downs if v >= 0.8 * contract_down) / len(downs)
    if contract_up and ups:
        out["up_percent_of_contract"] = (statistics.mean(ups) / contract_up) * 100
        out["up_sla_met_percent"] = 100 * sum(1 for v in ups if v >= 0.8 * contract_up) / len(ups)
    # Outages from event table.
    with db_mod.connect() as conn:
        outs = conn.execute(
            "SELECT ts, kind, payload FROM event WHERE ts >= ? AND kind LIKE 'outage_%' ORDER BY ts",
            (cutoff,),
        ).fetchall()
    out["outage_events"] = [dict(r) for r in outs]
    return out
