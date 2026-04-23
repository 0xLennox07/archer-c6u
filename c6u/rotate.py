"""Admin password generator + keyring history + rotation helper.

Doesn't assume the router firmware exposes password change — if it does
(via tplinkrouterc6u), use it; otherwise the user sets it manually after
this command prints the new password.

Keeps a rotation log as JSON in keyring under `<service>:<user>:history`:
    [{"ts": 1701..., "fp": "sha256:..."}]
Only the *hash* is stored in history (so you can prove rotation happened).
"""
from __future__ import annotations

import hashlib
import json
import secrets
import string
import time

import keyring

from . import config as cfg_mod
from . import db as db_mod

ALPHABET = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"


def generate(length: int = 24) -> str:
    # Guarantee ≥1 of each class.
    while True:
        pw = "".join(secrets.choice(ALPHABET) for _ in range(length))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*()-_=+" for c in pw)):
            return pw


def _history_key(kuser: str) -> str:
    return f"{kuser}:history"


def _append_history(kuser: str, pw: str) -> None:
    raw = keyring.get_password(cfg_mod.KEYRING_SERVICE, _history_key(kuser)) or "[]"
    try:
        hist = json.loads(raw)
    except Exception:
        hist = []
    hist.append({
        "ts": int(time.time()),
        "fp": "sha256:" + hashlib.sha256(pw.encode("utf-8")).hexdigest()[:16],
    })
    keyring.set_password(cfg_mod.KEYRING_SERVICE, _history_key(kuser),
                          json.dumps(hist[-20:]))


def rotate(try_apply: bool = False) -> dict:
    cfg = cfg_mod.load_config(interactive=False)
    kuser = cfg_mod._keyring_user(cfg)
    new_pw = generate()
    applied = False
    if try_apply:
        try:
            # Not all TP-Link firmware exposes this via the library; best effort.
            from .client import router
            with router() as r:
                if hasattr(r, "set_admin_password"):
                    r.set_admin_password(new_pw)
                    applied = True
                elif hasattr(r, "change_password"):
                    r.change_password(new_pw)
                    applied = True
        except Exception:
            applied = False
    keyring.set_password(cfg_mod.KEYRING_SERVICE, kuser, new_pw)
    _append_history(kuser, new_pw)
    db_mod.record_event("admin_password_rotated", payload=("auto" if applied else "manual"))
    return {"password": new_pw, "applied": applied, "keyring_user": kuser}


def history() -> list[dict]:
    cfg = cfg_mod.load_config(interactive=False)
    kuser = cfg_mod._keyring_user(cfg)
    raw = keyring.get_password(cfg_mod.KEYRING_SERVICE, _history_key(kuser)) or "[]"
    try:
        return json.loads(raw)
    except Exception:
        return []
