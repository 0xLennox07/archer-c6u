"""Port-scan your public IP — alert on anything unexpected."""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor

from . import publicip as publicip_mod

COMMON_PORTS = (21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443,
                445, 465, 587, 993, 995, 1723, 2049, 2082, 2083, 3306,
                3389, 5000, 5432, 5900, 6379, 8000, 8008, 8080, 8443,
                8888, 9000, 9090, 27017, 32400)


def _check(ip: str, port: int, timeout: float) -> tuple[int, bool]:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return port, True
    except Exception:
        return port, False


def scan(ip: str | None = None, ports=COMMON_PORTS, timeout: float = 1.0,
         workers: int = 32) -> dict:
    ip = ip or publicip_mod.fetch_public_ip()
    if not ip:
        return {"ip": None, "open": [], "error": "no public ip"}
    open_ports: list[int] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for port, is_open in ex.map(lambda p: _check(ip, p, timeout), ports):
            if is_open:
                open_ports.append(port)
    return {"ip": ip, "checked": len(ports), "open": sorted(open_ports)}
