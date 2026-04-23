"""Presence: is a tracked MAC currently visible on the router?"""
from __future__ import annotations

from . import aliases as aliases_mod
from .client import router


def who_is_present() -> dict:
    """Returns {mac, alias|hostname, present (bool)} per known device + currently seen extras."""
    aliases = aliases_mod.load()
    with router() as r:
        s = r.get_status()
    seen = {}
    for d in s.devices:
        mac = (str(d.macaddress) if d.macaddress else "").upper().replace("-", ":")
        if mac:
            seen[mac] = d.hostname or "?"
    out = {"present": [], "absent": [], "ts": __import__("time").time()}
    for mac, name in aliases.items():
        record = {"mac": mac, "name": name, "hostname": seen.get(mac)}
        (out["present"] if mac in seen else out["absent"]).append(record)
    for mac, host in seen.items():
        if mac not in aliases:
            out["present"].append({"mac": mac, "name": None, "hostname": host})
    return out
