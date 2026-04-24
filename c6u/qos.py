"""QoS / per-device bandwidth probe.

The TP-Link Archer C6U populates per-device down/up/usage stats ONLY when its
"Game Accelerator" (a.k.a. Smart Network / QoS on some firmware revisions) is
enabled. The tplinkrouterc6u library tries one endpoint, gives up on first
failure, and silently sets down_speed/up_speed/traffic_usage to null for the
rest of the session.

This module bypasses that. It:
  1. Probes a list of known + likely QoS endpoints directly (ignoring the
     library's _smart_network auto-disable flag)
  2. Returns whichever endpoint(s) actually produced per-device bandwidth data
  3. Offers fetch_per_device_bandwidth() which uses the winning endpoint to
     build a {mac: {down_speed, up_speed, traffic_usage}} dict
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


# (path, data) pairs that historically return per-device bandwidth on various
# TP-Link firmware. Ordered from most-likely-on-C6U to least. If you find a
# new endpoint that works, add it here.
QOS_PROBE_ENDPOINTS = [
    ("admin/smart_network?form=game_accelerator&operation=loadDevice", "operation=loadDevice"),
    ("admin/smart_network?form=game_accelerator",                      "operation=loadDevice"),
    ("admin/smart_network?form=application&operation=loadDevice",      "operation=loadDevice"),
    ("admin/smart_network?form=game_accelerator&operation=read",       "operation=read"),
    ("admin/qos?form=device&operation=load",                           "operation=load"),
    ("admin/qos?form=host&operation=load",                             "operation=load"),
    ("admin/qos?form=bandwidth&operation=load",                        "operation=load"),
    ("admin/qos?form=global&operation=load",                           "operation=load"),
    ("admin/network?form=qos&operation=load",                          "operation=load"),
    ("admin/network?form=monitor_lan&operation=load",                  "operation=load"),
    ("admin/network?form=monitor_wan&operation=load",                  "operation=load"),
    ("admin/traffic?form=statistics&operation=load",                   "operation=load"),
    ("admin/traffic?form=monitor&operation=load",                      "operation=load"),
]

# Keys we expect to see in a QoS response item that indicate bandwidth.
BANDWIDTH_KEYS = (
    "downloadSpeed", "downSpeed", "down_speed",
    "uploadSpeed", "upSpeed", "up_speed",
    "trafficUsage", "trafficUsed", "traffic_usage",
    "rx_bytes", "tx_bytes", "rxSpeed", "txSpeed",
)


def _has_bandwidth_fields(item) -> bool:
    if not isinstance(item, dict):
        return False
    return any(k in item for k in BANDWIDTH_KEYS)


def _summarize(resp) -> dict:
    """Distill a response into something printable + machine-testable."""
    if resp is None:
        return {"shape": "None", "has_bandwidth": False}
    if isinstance(resp, list):
        sample = resp[0] if resp else {}
        return {
            "shape": f"list[{len(resp)}]",
            "keys": sorted(list(sample.keys())) if isinstance(sample, dict) else None,
            "has_bandwidth": any(_has_bandwidth_fields(i) for i in resp),
            "sample": sample if isinstance(sample, dict) else resp[:3],
        }
    if isinstance(resp, dict):
        return {
            "shape": "dict",
            "keys": sorted(list(resp.keys())),
            "has_bandwidth": _has_bandwidth_fields(resp),
            "sample": {k: resp[k] for k in list(resp.keys())[:8]},
        }
    return {"shape": type(resp).__name__, "has_bandwidth": False, "sample": str(resp)[:200]}


def probe(r) -> list[dict]:
    """Call every endpoint in QOS_PROBE_ENDPOINTS against an authorized router.

    `r` must be an authorized tplinkrouterc6u client (we call r.request()).
    Returns a list of {endpoint, path, data, ok, error, summary} rows.
    """
    # Re-enable the smart-network path even if the library turned it off earlier.
    try:
        r._smart_network = True
    except Exception:
        pass

    results: list[dict] = []
    for path, data in QOS_PROBE_ENDPOINTS:
        row: dict = {"path": path, "data": data, "ok": False, "error": None, "summary": None}
        try:
            resp = r.request(path, data, ignore_errors=True)
            row["ok"] = True
            row["summary"] = _summarize(resp)
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        results.append(row)
    return results


def winning_endpoint(probe_results: list[dict]) -> dict | None:
    """Pick the first endpoint whose response actually had bandwidth fields."""
    for row in probe_results:
        summary = row.get("summary") or {}
        if row.get("ok") and summary.get("has_bandwidth"):
            return row
    return None


def fetch_per_device_bandwidth(r) -> dict[str, dict]:
    """Run the probe once; use the winning endpoint to return {mac: {down, up, usage}}."""
    probes = probe(r)
    win = winning_endpoint(probes)
    if not win:
        return {}
    resp = r.request(win["path"], win["data"], ignore_errors=True)
    if not isinstance(resp, list):
        return {}
    out: dict[str, dict] = {}
    for item in resp:
        if not isinstance(item, dict):
            continue
        mac = (item.get("mac") or item.get("macaddr") or "").upper()
        if not mac:
            continue
        out[mac] = {
            "down_speed": item.get("downloadSpeed") or item.get("downSpeed") or item.get("down_speed"),
            "up_speed":   item.get("uploadSpeed")   or item.get("upSpeed")   or item.get("up_speed"),
            "traffic_usage": item.get("trafficUsage") or item.get("trafficUsed") or item.get("traffic_usage"),
            "online_time":   item.get("onlineTime")   or item.get("online_time"),
            "signal":        item.get("signal"),
        }
    return out


def diagnosis(r) -> dict:
    """Comprehensive check: endpoint probes + whether Game Accelerator is
    turned on + whether devices are coming back with data."""
    probes = probe(r)
    win = winning_endpoint(probes)
    # Best-effort Game Accelerator enable check.
    game_enabled = None
    try:
        cfg = r.request("admin/smart_network?form=game_accelerator", "operation=read",
                         ignore_errors=True)
        if isinstance(cfg, dict):
            game_enabled = cfg.get("enable") or cfg.get("enabled") or cfg.get("state")
    except Exception:
        pass

    bw = {}
    if win:
        try:
            bw = fetch_per_device_bandwidth(r)
        except Exception:
            pass

    return {
        "probes": probes,
        "winning_endpoint": (win and win["path"]) or None,
        "game_accelerator_config": game_enabled,
        "devices_with_bandwidth": len(bw),
        "sample_bandwidth": dict(list(bw.items())[:3]),
    }
