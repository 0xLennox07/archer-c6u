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
    # ----- Game Accelerator / Smart Network / QoS -----
    ("admin/smart_network?form=device_priority",                       "operation=load"),
    ("admin/smart_network?form=device_priority",                       "operation=read"),
    ("admin/smart_network?form=device_priority",                       "operation=list"),
    ("admin/smart_network?form=game_accelerator&operation=loadDevice", "operation=loadDevice"),
    ("admin/smart_network?form=game_accelerator",                      "operation=loadDevice"),
    ("admin/smart_network?form=application&operation=loadDevice",      "operation=loadDevice"),
    ("admin/smart_network?form=game_accelerator&operation=read",       "operation=read"),
    # ----- Traffic Monitor (captured from web UI DevTools) -----
    ("admin/traffic?form=data",                                        "operation=load"),
    ("admin/traffic?form=data",                                        "operation=read"),
    ("admin/traffic?form=data",                                        "operation=list"),
    # ----- QoS -----
    ("admin/qos?form=device&operation=load",                           "operation=load"),
    ("admin/qos?form=host&operation=load",                             "operation=load"),
    ("admin/qos?form=bandwidth&operation=load",                        "operation=load"),
    ("admin/qos?form=global&operation=load",                           "operation=load"),
    ("admin/network?form=qos&operation=load",                          "operation=load"),
    # ----- Network monitors -----
    ("admin/network?form=monitor_lan&operation=load",                  "operation=load"),
    ("admin/network?form=monitor_wan&operation=load",                  "operation=load"),
    ("admin/traffic?form=statistics&operation=load",                   "operation=load"),
    ("admin/traffic?form=monitor&operation=load",                      "operation=load"),
    # ----- System Tools → Traffic Monitor (the hint from user) -----
    ("admin/traffic?form=ip_stat&operation=load",                      "operation=load"),
    ("admin/traffic?form=ip_stats&operation=load",                     "operation=load"),
    ("admin/traffic?form=device&operation=load",                       "operation=load"),
    ("admin/traffic?form=host&operation=load",                         "operation=load"),
    ("admin/traffic?form=list&operation=load",                         "operation=load"),
    ("admin/traffic?form=enable&operation=load",                       "operation=load"),
    ("admin/system_tools?form=traffic_monitor&operation=load",         "operation=load"),
    ("admin/system?form=traffic_monitor&operation=load",               "operation=load"),
    ("admin/systemtools?form=traffic&operation=load",                  "operation=load"),
    ("admin/statistics?form=device&operation=load",                    "operation=load"),
    ("admin/statistics?form=host&operation=load",                      "operation=load"),
    ("admin/monitor?form=traffic&operation=load",                      "operation=load"),
    ("admin/monitor?form=device&operation=load",                       "operation=load"),
    # ----- Bandwidth Control (legacy) -----
    ("admin/bandwidth?form=rule&operation=load",                       "operation=load"),
    ("admin/bandwidth?form=enable&operation=load",                     "operation=load"),
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


def _deep_has_bandwidth(obj, depth: int = 0) -> bool:
    """Walk nested dicts/lists up to 4 levels looking for bandwidth-like keys."""
    if depth > 4:
        return False
    if isinstance(obj, dict):
        if _has_bandwidth_fields(obj):
            return True
        return any(_deep_has_bandwidth(v, depth + 1) for v in obj.values())
    if isinstance(obj, list):
        return any(_deep_has_bandwidth(x, depth + 1) for x in obj)
    return False


def _summarize(resp) -> dict:
    """Distill a response into something printable + machine-testable.

    Handles nested envelopes like `{data: [...]}` or `{data: {host: [...]}}`
    by drilling in one more level when the top-level has a single `data` key.
    """
    if resp is None:
        return {"shape": "None", "has_bandwidth": False}
    if isinstance(resp, list):
        sample = resp[0] if resp else {}
        return {
            "shape": f"list[{len(resp)}]",
            "keys": sorted(list(sample.keys())) if isinstance(sample, dict) else None,
            "has_bandwidth": _deep_has_bandwidth(resp),
            "sample": sample if isinstance(sample, dict) else resp[:3],
        }
    if isinstance(resp, dict):
        # If the envelope is `{data: ...}`, describe the inner payload instead.
        if set(resp.keys()) == {"data"}:
            inner = resp["data"]
            inner_summary = _summarize(inner)
            inner_summary["outer_shape"] = "dict{data: ...}"
            return inner_summary
        if set(resp.keys()) <= {"data", "errorcode", "success"} and "data" in resp:
            inner_summary = _summarize(resp["data"])
            inner_summary["outer_shape"] = f"dict{sorted(resp.keys())}"
            inner_summary["errorcode"] = resp.get("errorcode")
            inner_summary["success"] = resp.get("success")
            return inner_summary
        return {
            "shape": "dict",
            "keys": sorted(list(resp.keys())),
            "has_bandwidth": _deep_has_bandwidth(resp),
            "errorcode": resp.get("errorcode"),
            "success": resp.get("success"),
            "sample": {k: resp[k] for k in list(resp.keys())[:8]},
        }
    return {"shape": type(resp).__name__, "has_bandwidth": False, "sample": str(resp)[:200]}


def dump_endpoint(r, path: str, data: str = "operation=load") -> dict:
    """Return the full raw response for a single endpoint (for bug-hunting)."""
    try:
        r._smart_network = True
    except Exception:
        pass
    try:
        resp = r.request(path, data, ignore_errors=True)
        return {"ok": True, "via": "request", "response": resp}
    except Exception as e:
        # Try the fallbacks.
        try:
            resp = r.request(path, data, ignore_errors=True, ignore_response=True)
            if resp is not None:
                return {"ok": True, "via": "ignore_response", "response": resp}
        except Exception:
            pass
        raw = _raw_request(r, path, data)
        if raw is not None:
            return {"ok": True, "via": "raw", "response": raw}
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def probe(r) -> list[dict]:
    """Call every endpoint in QOS_PROBE_ENDPOINTS against an authorized router.

    `r` must be an authorized tplinkrouterc6u client (we call r.request()).
    Returns a list of {endpoint, path, data, ok, error, summary} rows.

    If r.request() raises a 'ClientError: An unknown response' — common when
    the response shape differs from what the library's high-level parser
    expects — we fall back to _raw_request() to capture the decrypted payload
    directly, which is what we actually care about.
    """
    # Re-enable the smart-network path even if the library turned it off earlier.
    try:
        r._smart_network = True
    except Exception:
        pass

    results: list[dict] = []
    for path, data in QOS_PROBE_ENDPOINTS:
        row: dict = {"path": path, "data": data, "ok": False, "error": None,
                     "summary": None, "via": "request"}
        try:
            resp = r.request(path, data, ignore_errors=True)
            row["ok"] = True
            row["summary"] = _summarize(resp)
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
            # The library throws "unknown response" when the response envelope
            # doesn't match what it expects. Try again with ignore_response,
            # then fall back to a raw HTTP call that bypasses parsing.
            recovered = False
            try:
                resp = r.request(path, data, ignore_errors=True, ignore_response=True)
                if resp is not None:
                    row["ok"] = True
                    row["via"] = "ignore_response"
                    row["summary"] = _summarize(resp)
                    recovered = True
            except Exception:
                pass
            if not recovered:
                raw = _raw_request(r, path, data)
                if raw is not None:
                    row["ok"] = True
                    row["via"] = "raw"
                    row["summary"] = _summarize(raw)
        results.append(row)
    return results


def _raw_request(r, path: str, data: str):
    """Call the same HTTP endpoint r.request() would, but return the decrypted
    response dict as-is (no envelope validation, no `data` key unwrap). This
    lets us see what the endpoint actually sends back when the library's
    high-level parser rejects it as 'unknown response'.
    """
    try:
        import requests as _rq
        from json import loads
        # Build URL the same way the library does.
        url = f"{r.host}/cgi-bin/luci/;stok={getattr(r, '_stok', '')}/{path}"
        # Encrypt the payload with the library's helper.
        encrypted = r._prepare_data(data)
        headers = getattr(r, "_headers_request", {})
        resp = _rq.post(url, data=encrypted, headers=headers,
                         timeout=getattr(r, "timeout", 10),
                         verify=getattr(r, "verify_ssl", False))
        if not resp.ok:
            return None
        j = resp.json()
        # Decrypt if encrypted response envelope; otherwise return as-is.
        if isinstance(j, dict) and "data" in j and isinstance(j["data"], str):
            try:
                j = loads(r._encryption.aes_decrypt(j["data"]))
            except Exception:
                return j  # keep raw if decrypt fails
        return j
    except Exception as e:
        log.debug("raw request %s failed: %s", path, e)
        return None


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
