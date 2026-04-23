"""Port scan — public IP (from outside) or every device on the LAN."""
from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed

from . import publicip as publicip_mod

# WAN-facing — things you'd hate to see open from the internet.
COMMON_PORTS = (21, 22, 23, 25, 53, 80, 110, 111, 135, 139, 143, 443,
                445, 465, 587, 993, 995, 1723, 2049, 2082, 2083, 3306,
                3389, 5000, 5432, 5900, 6379, 8000, 8008, 8080, 8443,
                8888, 9000, 9090, 27017, 32400)

# LAN-facing — wider net; common IoT / media / admin ports included.
LAN_PORTS = (
    21, 22, 23, 25, 53, 80, 81, 88, 110, 111, 135, 139, 143, 161,
    389, 443, 445, 515, 548, 554, 587, 631, 873, 902, 993, 995,
    1080, 1194, 1433, 1723, 1883, 2049, 2082, 2083, 3128, 3306,
    3389, 5000, 5001, 5060, 5353, 5357, 5432, 5555, 5900, 5901,
    6379, 7000, 8000, 8008, 8009, 8080, 8081, 8443, 8554, 8888,
    9000, 9090, 9100, 9200, 11211, 27017, 32400,
)


def _check(ip: str, port: int, timeout: float) -> tuple[str, int, bool]:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return ip, port, True
    except Exception:
        return ip, port, False


def scan(ip: str | None = None, ports=COMMON_PORTS, timeout: float = 1.0,
         workers: int = 32) -> dict:
    """Scan the given (or public) IP. Default for legacy `c6u portscan`."""
    ip = ip or publicip_mod.fetch_public_ip()
    if not ip:
        return {"ip": None, "open": [], "error": "no public ip"}
    open_ports: list[int] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _, port, is_open in ex.map(lambda p: _check(ip, p, timeout), ports):
            if is_open:
                open_ports.append(port)
    return {"ip": ip, "checked": len(ports), "open": sorted(open_ports)}


def scan_host(ip: str, ports=LAN_PORTS, timeout: float = 0.5, workers: int = 32) -> list[int]:
    """Scan a single host, return sorted list of open ports."""
    open_ports: list[int] = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for _, port, is_open in ex.map(lambda p: _check(ip, p, timeout), ports):
            if is_open:
                open_ports.append(port)
    return sorted(open_ports)


def scan_lan(ports=LAN_PORTS, timeout: float = 0.5, workers: int = 64,
             include_gateway: bool = True) -> dict:
    """Scan every router-known device (and the router itself) in parallel."""
    from .client import router
    from . import aliases as aliases_mod
    from . import vendor as vendor_mod

    aliases = aliases_mod.load()
    with router() as r:
        s = r.get_status()
        try:
            wan = r.get_ipv4_status()
        except Exception:
            wan = None

    targets: list[dict] = []
    for d in s.devices:
        if not d.ipaddress:
            continue
        mac = (str(d.macaddress) or "").upper()
        targets.append({
            "mac": mac,
            "hostname": d.hostname or "",
            "ip": str(d.ipaddress),
            "alias": aliases.get(mac),
            "vendor": vendor_mod.vendor(mac) or "",
        })
    if include_gateway and wan is not None:
        gw_ip = getattr(wan, "lan_ipv4_ipaddr", None) or getattr(wan, "lan_ipv4_address", None)
        if gw_ip and not any(t["ip"] == str(gw_ip) for t in targets):
            targets.insert(0, {"mac": "", "hostname": "(router)",
                                "ip": str(gw_ip), "alias": "router", "vendor": "TP-Link"})

    # Flatten (ip, port) pairs, parallel across everything.
    tasks = [(t["ip"], p) for t in targets for p in ports]
    open_by_ip: dict[str, list[int]] = {t["ip"]: [] for t in targets}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_check, ip, p, timeout) for (ip, p) in tasks]
        for f in as_completed(futures):
            ip, port, is_open = f.result()
            if is_open:
                open_by_ip[ip].append(port)

    for t in targets:
        t["open"] = sorted(open_by_ip.get(t["ip"], []))
    return {
        "devices": targets,
        "checked_per_host": len(ports),
        "total_checks": len(tasks),
        "reachable_hosts": sum(1 for t in targets if t["open"]),
    }


# Risky-if-open LAN ports (roughly: admin/remote-exec/filesystem).
RISKY_LAN_PORTS = frozenset({21, 22, 23, 139, 445, 1433, 3306, 3389,
                              5432, 5555, 5900, 5901, 6379, 11211, 27017})


def risky_findings(result: dict) -> list[dict]:
    """Pick out hosts with potentially-sensitive open ports."""
    out = []
    for t in result.get("devices", []):
        risky = [p for p in t.get("open", []) if p in RISKY_LAN_PORTS]
        if risky:
            out.append({**t, "risky_ports": risky})
    return out
