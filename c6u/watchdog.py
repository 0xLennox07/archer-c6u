"""Connectivity watchdog.

Periodically pings external targets. After N consecutive failures, triggers
a reboot action (optional), records an outage to the event log, and fires
webhooks/pushes.
"""
from __future__ import annotations

import logging
import threading
import time

from . import config as cfg_mod
from . import db as db_mod
from . import latency as latency_mod
from . import pushnotify as push_mod
from . import webhook as wh_mod

log = logging.getLogger(__name__)

DEFAULT_TARGETS = ("1.1.1.1", "8.8.8.8", "9.9.9.9")


def _check_all(targets, timeout: float) -> tuple[bool, list[dict]]:
    results = []
    any_ok = False
    for t in targets:
        rtt = latency_mod.ping_once(t, timeout=timeout)
        ok = rtt is not None
        any_ok = any_ok or ok
        results.append({"target": t, "rtt_ms": rtt, "ok": ok})
    return any_ok, results


def run(stop: threading.Event | None = None,
        interval: int = 60, timeout: float = 2.0,
        fail_threshold: int = 3, auto_reboot: bool = False,
        targets=DEFAULT_TARGETS) -> None:
    stop = stop or threading.Event()
    cfg = cfg_mod.load_config(interactive=False)
    push_cfg = cfg.get("push") or {}
    hooks = cfg.get("webhooks") or []

    consecutive = 0
    outage_start: int | None = None
    while not stop.is_set():
        ok, results = _check_all(targets, timeout)
        now = int(time.time())
        if ok:
            if outage_start is not None:
                duration = now - outage_start
                db_mod.record_event("outage_recovered", payload=str(duration))
                wh_mod.emit(hooks, "outage_recovered", duration_s=duration)
                push_mod.push(push_cfg, "Internet recovered",
                              f"Outage lasted {duration}s", priority=0)
                log.info("recovered after %ss", duration)
                outage_start = None
            consecutive = 0
        else:
            consecutive += 1
            if outage_start is None:
                outage_start = now
                db_mod.record_event("outage_started", payload=repr(results))
                wh_mod.emit(hooks, "outage_started", results=results)
                push_mod.push(push_cfg, "Internet down",
                              f"Failed to reach {', '.join(targets)}", priority=1)
                log.warning("outage started, results=%s", results)
            if auto_reboot and consecutive >= fail_threshold:
                try:
                    from .client import router
                    with router() as r:
                        r.reboot()
                    db_mod.record_event("watchdog_reboot", payload=f"after {consecutive} failures")
                    wh_mod.emit(hooks, "watchdog_reboot", failures=consecutive)
                    push_mod.push(push_cfg, "Router auto-rebooted",
                                  f"after {consecutive} consecutive ping failures", priority=2)
                    log.warning("auto-rebooted after %s failures", consecutive)
                    consecutive = 0
                    stop.wait(180)  # wait for boot
                except Exception as e:
                    log.error("auto-reboot failed: %s", e)
        stop.wait(interval)
