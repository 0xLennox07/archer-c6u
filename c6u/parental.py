"""Parental-controls wrapper.

Given a per-MAC schedule (parental.json), evaluates which devices should be
blocked/allowed right now and applies the difference via the router API.

parental.json schema:
    {
      "rules": [
        {"mac": "AA:BB:...", "block": [{"dow": [0,1,2,3,4], "from": "23:00", "to": "06:30"}]},
        {"mac": "CC:DD:...", "block": [{"dow": [5,6], "from": "00:00", "to": "09:00"}]}
      ]
    }

dow is Python weekday: Mon=0..Sun=6.

The actual "block" action depends on what the firmware exposes; tplinkrouterc6u
doesn't always have a first-class parental-control API, so this module tries
several common methods and logs the one that worked. Worst case, it just records
the scheduled decision to the event log so the user can wire their own action
via rules.py.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from pathlib import Path

from . import config as cfg_mod
from . import db as db_mod

log = logging.getLogger(__name__)


def _parse_hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def load_rules() -> list[dict]:
    p = cfg_mod.ROOT / "parental.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    return (data or {}).get("rules", []) or []


def should_block(mac: str, now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now()
    minutes = now.hour * 60 + now.minute
    mac_u = mac.upper().replace("-", ":")
    for r in load_rules():
        if (r.get("mac", "").upper().replace("-", ":")) != mac_u:
            continue
        for window in r.get("block", []) or []:
            dow = window.get("dow") or list(range(7))
            if now.weekday() not in dow:
                continue
            start = _parse_hhmm(window["from"])
            end = _parse_hhmm(window["to"])
            if start <= end:
                if start <= minutes < end:
                    return True
            else:  # overnight wrap
                if minutes >= start or minutes < end:
                    return True
    return False


def _apply(router_obj, mac: str, block: bool) -> bool:
    """Try several known method names. Returns True if any succeeded."""
    for method in ("set_parental_control", "parental_set", "block_device",
                   "set_device_block", "deny_device", "allow_device"):
        fn = getattr(router_obj, method, None)
        if not fn:
            continue
        try:
            fn(mac, block)
            return True
        except Exception as e:
            log.debug("%s failed: %s", method, e)
    return False


def evaluate_and_apply(dry_run: bool = False) -> dict:
    rules = load_rules()
    if not rules:
        return {"rules": 0, "decisions": []}
    decisions = []
    from .client import router
    apply_ctx = None if dry_run else router()
    r_obj = None
    if not dry_run:
        r_obj = apply_ctx.__enter__()
    try:
        for r in rules:
            mac = r.get("mac", "")
            if not mac:
                continue
            block = should_block(mac)
            applied = False
            if not dry_run and r_obj is not None:
                applied = _apply(r_obj, mac, block)
            decisions.append({"mac": mac, "block": block, "applied": applied})
            db_mod.record_event("parental_decision", mac=mac,
                                 payload=f"block={block} applied={applied}")
    finally:
        if apply_ctx is not None:
            apply_ctx.__exit__(None, None, None)
    return {"rules": len(rules), "decisions": decisions}


def example() -> dict:
    return {
        "rules": [
            {"mac": "AA:BB:CC:DD:EE:FF",
             "block": [
                 {"dow": [0, 1, 2, 3, 4], "from": "23:00", "to": "06:30"},
                 {"dow": [0, 1, 2, 3, 4], "from": "14:00", "to": "16:00"},
             ]},
        ]
    }


def write_example() -> Path:
    p = cfg_mod.ROOT / "parental.example.json"
    p.write_text(json.dumps(example(), indent=2), encoding="utf-8")
    return p
