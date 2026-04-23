"""Rules engine — declarative reactions to events.

Rules live in rules.json (or rules.yaml if PyYAML is present) at the repo root:

    {
      "rules": [
        {
          "name": "unknown device at night",
          "when": {"kind": "device_joined", "unknown_mac": true, "hour_between": [23, 6]},
          "then": [{"push": {"title": "New device!", "body": "{mac} {hostname}"}}]
        },
        {
          "name": "public ip change",
          "when": {"kind": "public_ip_changed"},
          "then": [{"webhook": {"url": "https://hooks.zapier.com/..."}},
                   {"push": {"title": "IP changed", "body": "{previous} -> {current}"}}]
        }
      ]
    }

Triggers (`when`):
    - kind: match event kind exactly
    - unknown_mac: mac not in aliases.json / known_macs.txt
    - hour_between: [start, end] in local time (wraps over midnight)
    - mac_in: list of MACs

Actions (`then` items are single-key dicts):
    - push: {title, body, priority, tags, profiles?}
    - webhook: {url, method?, body?}
    - notify_desktop: {title, body}
    - reboot_router: {}
    - wifi_toggle: {which, band, state}
    - exec: {argv: [...]}  (runs subprocess.Popen, env-aware only)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import subprocess
from pathlib import Path

import requests

from . import aliases as aliases_mod
from . import config as cfg_mod
from . import pushnotify as push_mod

log = logging.getLogger(__name__)

RULES_PATHS = ("rules.json", "rules.yaml", "rules.yml")


def _try_yaml_load(text: str):
    try:
        import yaml  # type: ignore
        return yaml.safe_load(text)
    except ImportError:
        raise RuntimeError("rules.yaml requires PyYAML — `pip install pyyaml`")


def load_rules() -> list[dict]:
    root = cfg_mod.ROOT
    for name in RULES_PATHS:
        p = root / name
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        data = _try_yaml_load(text) if name.endswith((".yaml", ".yml")) else json.loads(text)
        return (data or {}).get("rules", []) or []
    return []


def _known_macs() -> set[str]:
    out = set()
    out.update(m.upper() for m in aliases_mod.load().keys())
    path = cfg_mod.KNOWN_MACS_PATH
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                out.add(line.upper())
    return out


def _fmt(template: str, event: dict) -> str:
    try:
        return template.format(**event)
    except (KeyError, IndexError):
        return template


def _trigger_matches(when: dict, event: dict) -> bool:
    if not when:
        return True
    if "kind" in when and event.get("kind") != when["kind"]:
        return False
    if "mac_in" in when:
        mac = (event.get("mac") or "").upper()
        if mac not in {m.upper() for m in when["mac_in"]}:
            return False
    if when.get("unknown_mac"):
        mac = (event.get("mac") or "").upper()
        if mac in _known_macs():
            return False
    if "hour_between" in when:
        start, end = when["hour_between"]
        hour = dt.datetime.now().hour
        in_range = (start <= hour < end) if start <= end else (hour >= start or hour < end)
        if not in_range:
            return False
    return True


def _do_push(spec: dict, event: dict, cfg: dict) -> None:
    title = _fmt(spec.get("title", "c6u event"), event)
    body = _fmt(spec.get("body", json.dumps(event)), event)
    push_mod.push(cfg.get("push"), title, body,
                  priority=spec.get("priority"), tags=spec.get("tags"))


def _do_webhook(spec: dict, event: dict, _cfg) -> None:
    url = _fmt(spec.get("url", ""), event)
    if not url:
        return
    method = (spec.get("method") or "POST").upper()
    body = spec.get("body")
    if isinstance(body, str):
        body = _fmt(body, event)
    try:
        requests.request(method, url, json=(body or event), timeout=5)
    except Exception as e:
        log.warning("rule webhook failed: %s", e)


def _do_notify_desktop(spec: dict, event: dict, _cfg) -> None:
    try:
        from plyer import notification  # type: ignore
        notification.notify(
            title=_fmt(spec.get("title", "c6u"), event),
            message=_fmt(spec.get("body", ""), event),
            timeout=5,
        )
    except Exception as e:
        log.warning("desktop notify failed: %s", e)


def _do_reboot(_spec, _event, _cfg) -> None:
    from .client import router
    with router() as r:
        r.reboot()


def _do_wifi_toggle(spec: dict, _event, _cfg) -> None:
    from tplinkrouterc6u import Connection
    from .client import router
    m = {
        ("host", "2g"): Connection.HOST_2G, ("host", "5g"): Connection.HOST_5G, ("host", "6g"): Connection.HOST_6G,
        ("guest", "2g"): Connection.GUEST_2G, ("guest", "5g"): Connection.GUEST_5G, ("guest", "6g"): Connection.GUEST_6G,
        ("iot", "2g"): Connection.IOT_2G, ("iot", "5g"): Connection.IOT_5G, ("iot", "6g"): Connection.IOT_6G,
    }
    target = m.get((spec.get("which"), spec.get("band")))
    if not target:
        return
    with router() as r:
        r.set_wifi(target, spec.get("state") == "on")


def _do_exec(spec: dict, event: dict, _cfg) -> None:
    argv = spec.get("argv")
    if not argv:
        return
    argv = [_fmt(a, event) if isinstance(a, str) else a for a in argv]
    subprocess.Popen(argv, shell=False)


ACTIONS = {
    "push": _do_push,
    "webhook": _do_webhook,
    "notify_desktop": _do_notify_desktop,
    "reboot_router": _do_reboot,
    "wifi_toggle": _do_wifi_toggle,
    "exec": _do_exec,
}


def dispatch(event: dict, cfg: dict | None = None, rules: list[dict] | None = None) -> int:
    """Feed an event through all rules. Returns count of actions fired."""
    cfg = cfg or cfg_mod.load_config(interactive=False)
    rules = rules if rules is not None else load_rules()
    fired = 0
    for rule in rules:
        try:
            if not _trigger_matches(rule.get("when") or {}, event):
                continue
            for action in rule.get("then") or []:
                if not isinstance(action, dict) or len(action) != 1:
                    continue
                kind = next(iter(action))
                fn = ACTIONS.get(kind)
                if not fn:
                    continue
                try:
                    fn(action[kind] or {}, event, cfg)
                    fired += 1
                except Exception as e:
                    log.warning("rule %r action %r failed: %s", rule.get("name"), kind, e)
        except Exception as e:
            log.warning("rule %r failed: %s", rule.get("name"), e)
    return fired


def example_rules() -> dict:
    """Starter rules — written to rules.example.json."""
    return {
        "rules": [
            {
                "name": "new unknown device",
                "when": {"kind": "device_joined", "unknown_mac": True},
                "then": [{"push": {"title": "Unknown device joined", "body": "{mac} {hostname} {ip}"}}],
            },
            {
                "name": "late-night join",
                "when": {"kind": "device_joined", "hour_between": [23, 6]},
                "then": [{"push": {"title": "Late-night device",
                                    "body": "{mac} {hostname}", "priority": 1}}],
            },
            {
                "name": "public ip change",
                "when": {"kind": "public_ip_changed"},
                "then": [{"push": {"title": "WAN IP changed", "body": "{previous} -> {current}"}}],
            },
        ]
    }


def write_example() -> Path:
    path = cfg_mod.ROOT / "rules.example.json"
    path.write_text(json.dumps(example_rules(), indent=2), encoding="utf-8")
    return path
