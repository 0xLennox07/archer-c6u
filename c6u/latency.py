"""Per-device latency probe via system `ping`. Cross-platform, no admin needed."""
from __future__ import annotations

import platform
import re
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

from . import db as db_mod
from .client import router

_RE_RTT = re.compile(r"(?:time[=<])(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_IS_WIN = platform.system() == "Windows"


def ping_once(ip: str, timeout: float = 1.5) -> float | None:
    """Returns RTT in ms or None if unreachable. Single ping, short timeout."""
    if _IS_WIN:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(int(timeout)), ip]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout + 1, creationflags=0x08000000 if _IS_WIN else 0,  # CREATE_NO_WINDOW
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if proc.returncode != 0:
        return None
    m = _RE_RTT.search(proc.stdout)
    return float(m.group(1)) if m else None


def probe_clients(workers: int = 16, timeout: float = 1.5) -> list[dict]:
    """Ping every router-known client in parallel. Returns one dict per device."""
    with router() as r:
        s = r.get_status()
        devices = [(d.macaddress, str(d.ipaddress)) for d in s.devices if d.ipaddress and d.macaddress]

    def task(item):
        mac, ip = item
        rtt = ping_once(ip, timeout=timeout)
        return {"mac": str(mac), "ip": ip, "rtt_ms": rtt, "reachable": rtt is not None}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(task, devices))


def probe_and_record(workers: int = 16, timeout: float = 1.5) -> list[dict]:
    samples = probe_clients(workers=workers, timeout=timeout)
    db_mod.record_latency(samples)
    return samples
