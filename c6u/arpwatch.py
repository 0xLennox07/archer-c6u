"""ARP watcher — parse the system ARP table, flag conflicts.

A conflict = two IPs pointing to the same MAC OR same IP suddenly mapping
to a different MAC than before. The history lives in the `arp_map` table.
"""
from __future__ import annotations

import re
import subprocess
import time

from . import db as db_mod

ARP_SCHEMA = """
CREATE TABLE IF NOT EXISTS arp_map (
  ip   TEXT PRIMARY KEY,
  mac  TEXT,
  ts   INTEGER
);
"""

_WIN_MAC = re.compile(r"([0-9a-f]{2}-){5}[0-9a-f]{2}", re.I)
_UNIX_MAC = re.compile(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", re.I)
_IP = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _ensure_schema():
    with db_mod.connect() as conn:
        conn.executescript(ARP_SCHEMA)


def _normalize(mac: str) -> str:
    return mac.upper().replace("-", ":")


def read_arp_table() -> dict[str, str]:
    """Runs `arp -a`, returns ip -> MAC dict."""
    try:
        out = subprocess.run(
            ["arp", "-a"], capture_output=True, text=True, timeout=5,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        ).stdout
    except Exception:
        return {}
    table: dict[str, str] = {}
    for line in out.splitlines():
        ip_m = _IP.search(line)
        mac_m = _WIN_MAC.search(line) or _UNIX_MAC.search(line)
        if not (ip_m and mac_m):
            continue
        ip = ip_m.group(0)
        mac = _normalize(mac_m.group(0))
        if mac in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            continue
        table[ip] = mac
    return table


def check() -> dict:
    _ensure_schema()
    now = int(time.time())
    table = read_arp_table()
    conflicts_ip: list[dict] = []
    changes: list[dict] = []

    # IPs mapping to new MACs (since last run).
    with db_mod.connect() as conn:
        prev_rows = conn.execute("SELECT ip, mac FROM arp_map").fetchall()
        prev = {r["ip"]: r["mac"] for r in prev_rows}

        for ip, mac in table.items():
            before = prev.get(ip)
            if before and before != mac:
                changes.append({"ip": ip, "old_mac": before, "new_mac": mac})
                db_mod.record_event("arp_change", mac=mac,
                                     payload=f"{ip}: {before} -> {mac}")
            conn.execute("INSERT OR REPLACE INTO arp_map VALUES (?,?,?)", (ip, mac, now))

    # MAC claimed by multiple IPs (could be legitimate; still worth knowing).
    by_mac: dict[str, list[str]] = {}
    for ip, mac in table.items():
        by_mac.setdefault(mac, []).append(ip)
    for mac, ips in by_mac.items():
        if len(ips) > 1:
            conflicts_ip.append({"mac": mac, "ips": sorted(ips)})

    return {
        "ts": now,
        "entries": len(table),
        "changes_since_last": changes,
        "mac_with_multiple_ips": conflicts_ip,
    }
