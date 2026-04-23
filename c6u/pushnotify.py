"""Mobile push notifications: ntfy.sh, Pushover, Gotify.

Each adapter takes a config dict and a message dict ({title, body, priority, tags}).
Config is read from config.json under the `push` key, e.g.:
    "push": {
      "ntfy":     {"topic": "my-c6u-alerts", "server": "https://ntfy.sh"},
      "pushover": {"token": "APP_TOKEN", "user": "USER_KEY"},
      "gotify":   {"url": "https://gotify.example", "token": "APP_TOKEN"}
    }
"""
from __future__ import annotations

import logging
from typing import Iterable

import requests

log = logging.getLogger(__name__)


def _ntfy(cfg: dict, title: str, body: str, priority: int | None, tags: Iterable[str] | None) -> bool:
    server = (cfg.get("server") or "https://ntfy.sh").rstrip("/")
    topic = cfg.get("topic")
    if not topic:
        return False
    headers = {"Title": title}
    if priority is not None:
        headers["Priority"] = str(priority)
    if tags:
        headers["Tags"] = ",".join(tags)
    requests.post(f"{server}/{topic}", data=body.encode("utf-8"), headers=headers, timeout=6)
    return True


def _pushover(cfg: dict, title: str, body: str, priority: int | None, _tags) -> bool:
    token, user = cfg.get("token"), cfg.get("user")
    if not (token and user):
        return False
    payload = {"token": token, "user": user, "title": title, "message": body}
    if priority is not None:
        payload["priority"] = str(priority)
    requests.post("https://api.pushover.net/1/messages.json", data=payload, timeout=6)
    return True


def _gotify(cfg: dict, title: str, body: str, priority: int | None, _tags) -> bool:
    base, token = cfg.get("url"), cfg.get("token")
    if not (base and token):
        return False
    payload = {"title": title, "message": body}
    if priority is not None:
        payload["priority"] = priority
    requests.post(f"{base.rstrip('/')}/message?token={token}", json=payload, timeout=6)
    return True


_ADAPTERS = {"ntfy": _ntfy, "pushover": _pushover, "gotify": _gotify}


def push(push_cfg: dict | None, title: str, body: str,
         priority: int | None = None, tags: Iterable[str] | None = None) -> list[str]:
    """Fan out to every configured adapter. Returns names that actually fired."""
    fired: list[str] = []
    if not push_cfg:
        return fired
    for name, adapter in _ADAPTERS.items():
        sub = push_cfg.get(name)
        if not sub:
            continue
        try:
            if adapter(sub, title, body, priority, tags):
                fired.append(name)
        except Exception as e:
            log.warning("push via %s failed: %s", name, e)
    return fired
