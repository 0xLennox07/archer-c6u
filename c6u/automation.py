"""Cron-style scheduled actions.

Rules live in automation.json at the repo root:

    {
      "jobs": [
        {"name": "guest wifi off at midnight", "cron": "0 0 * * *",
         "action": {"wifi_toggle": {"which": "guest", "band": "2g", "state": "off"}}},
        {"name": "weekly reboot", "cron": "0 3 * * 1",
         "action": {"reboot_router": {}}},
        {"name": "speedtest hourly", "cron": "5 * * * *",
         "action": {"speedtest": {}}}
      ]
    }

Uses a tiny cron matcher — fields: minute, hour, day-of-month, month, day-of-week (0=Sun).
Ranges (1-5), lists (1,3,5), and */N step syntax all supported.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from pathlib import Path

from . import config as cfg_mod
from . import rules as rules_mod

log = logging.getLogger(__name__)


def _parse_field(expr: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for chunk in expr.split(","):
        chunk = chunk.strip()
        if chunk == "*":
            out.update(range(lo, hi + 1))
            continue
        step = 1
        if "/" in chunk:
            chunk, step_s = chunk.split("/", 1)
            step = int(step_s)
        if chunk in ("*", ""):
            start, end = lo, hi
        elif "-" in chunk:
            s, e = chunk.split("-", 1)
            start, end = int(s), int(e)
        else:
            start = end = int(chunk)
        out.update(range(start, end + 1, step))
    return {v for v in out if lo <= v <= hi}


def _parse_cron(expr: str) -> dict:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"cron expression needs 5 fields, got {len(parts)}: {expr!r}")
    return {
        "minute": _parse_field(parts[0], 0, 59),
        "hour":   _parse_field(parts[1], 0, 23),
        "dom":    _parse_field(parts[2], 1, 31),
        "month":  _parse_field(parts[3], 1, 12),
        "dow":    _parse_field(parts[4], 0, 6),
    }


def _matches(cron: dict, t: dt.datetime) -> bool:
    return (
        t.minute in cron["minute"]
        and t.hour in cron["hour"]
        and t.day in cron["dom"]
        and t.month in cron["month"]
        and ((t.weekday() + 1) % 7) in cron["dow"]
    )


def load_jobs() -> list[dict]:
    p = cfg_mod.ROOT / "automation.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    jobs = []
    for j in (data or {}).get("jobs", []) or []:
        try:
            j["_cron"] = _parse_cron(j["cron"])
            jobs.append(j)
        except Exception as e:
            log.warning("skip job %r: %s", j.get("name"), e)
    return jobs


def _do_speedtest(_spec, _event, _cfg) -> None:
    from . import speedtest_cmd
    speedtest_cmd.run_and_record()


def _do_snapshot(_spec, _event, _cfg) -> None:
    from . import db as db_mod
    from .client import router
    with router() as r:
        db_mod.record_snapshot(r.get_status())


# Extend rules.ACTIONS with automation-only ones.
rules_mod.ACTIONS.setdefault("speedtest", _do_speedtest)
rules_mod.ACTIONS.setdefault("snapshot", _do_snapshot)


def _run_action(action: dict, cfg: dict) -> None:
    if not isinstance(action, dict) or len(action) != 1:
        return
    kind = next(iter(action))
    fn = rules_mod.ACTIONS.get(kind)
    if not fn:
        log.warning("unknown automation action: %s", kind)
        return
    fn(action[kind] or {}, {}, cfg)


def run(stop: threading.Event | None = None, poll_seconds: int = 30) -> None:
    """Tick every minute, fire jobs whose cron matches the current minute.

    Safe to call in the daemon; emits its own log.
    """
    stop = stop or threading.Event()
    cfg = cfg_mod.load_config(interactive=False)
    jobs = load_jobs()
    if not jobs:
        log.info("automation: no jobs configured, exiting loop")
        return
    last_minute: tuple[int, int] | None = None
    while not stop.is_set():
        now = dt.datetime.now().replace(second=0, microsecond=0)
        key = (now.toordinal(), now.hour * 60 + now.minute)
        if key != last_minute:
            for j in jobs:
                try:
                    if _matches(j["_cron"], now):
                        log.info("automation fire: %s", j.get("name"))
                        _run_action(j.get("action") or {}, cfg)
                except Exception as e:
                    log.warning("automation job %r failed: %s", j.get("name"), e)
            last_minute = key
        stop.wait(poll_seconds)


def example() -> dict:
    return {
        "jobs": [
            {"name": "guest wifi off midnight", "cron": "0 0 * * *",
             "action": {"wifi_toggle": {"which": "guest", "band": "2g", "state": "off"}}},
            {"name": "weekly reboot 3am Mon", "cron": "0 3 * * 1",
             "action": {"reboot_router": {}}},
            {"name": "hourly speedtest", "cron": "5 * * * *",
             "action": {"speedtest": {}}},
        ]
    }


def write_example() -> Path:
    path = cfg_mod.ROOT / "automation.example.json"
    path.write_text(json.dumps(example(), indent=2), encoding="utf-8")
    return path
