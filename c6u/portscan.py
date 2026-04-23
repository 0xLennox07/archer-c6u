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

# LAN-facing — wider net; common IoT / media / admin / P2P ports included.
LAN_PORTS = (
    21, 22, 23, 25, 53, 80, 81, 88, 110, 111, 113, 119, 123, 135, 137, 139,
    143, 161, 162, 179, 194, 199, 389, 427, 443, 444, 445, 465, 500, 515,
    548, 554, 587, 631, 636, 873, 902, 993, 995, 1080, 1194, 1433, 1434,
    1521, 1701, 1723, 1883, 1900, 2049, 2082, 2083, 2086, 2087, 2095, 2096,
    2375, 2376, 2525, 3000, 3128, 3260, 3268, 3283, 3306, 3389, 3478, 3689,
    4000, 4321, 4369, 4444, 4500, 4567, 4711, 4750, 4848, 5000, 5001, 5005,
    5060, 5061, 5222, 5269, 5353, 5357, 5432, 5555, 5600, 5672, 5683, 5800,
    5900, 5901, 5902, 5903, 5938, 5984, 6000, 6379, 6443, 6660, 6666, 6667,
    6881, 6969, 7000, 7001, 7070, 7443, 7547, 8000, 8001, 8008, 8009, 8060,
    8080, 8081, 8086, 8088, 8096, 8123, 8181, 8291, 8333, 8443, 8554, 8686,
    8787, 8800, 8888, 8883, 9000, 9001, 9080, 9090, 9091, 9100, 9200, 9418,
    9443, 9999, 10000, 10001, 10022, 10443, 11211, 12345, 17500, 18080,
    19999, 20000, 22000, 23000, 25565, 27017, 27018, 27019, 27015, 28015,
    32400, 32469, 33434, 37777, 47808, 49152, 49153, 49154, 49155, 49156,
    50000, 51413, 52869, 54235, 55443, 62078, 64738, 65000, 65535,
)

# Well-known / system ports (1–1023) + the LAN_PORTS extras.
TOP1024_PLUS = tuple(sorted(set(LAN_PORTS) | set(range(1, 1024))))

_OPEN, _CLOSED, _TIMEOUT = "open", "closed", "timeout"


def _probe(ip: str, port: int, timeout: float) -> tuple[str, int, str]:
    """Returns (ip, port, state) where state is one of open/closed/timeout.

    Distinguishing 'closed' (TCP RST, fast) from 'timeout' (no response) lets
    us retry just the ambiguous cases — timeouts are usually a dozing WiFi
    device, host firewall silently dropping, or heavy retransmit, not a
    definitively closed port.
    """
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return ip, port, _OPEN
    except ConnectionRefusedError:
        return ip, port, _CLOSED
    except (socket.timeout, TimeoutError):
        return ip, port, _TIMEOUT
    except OSError as e:
        # WinError 10061 = refused, 10060 = timeout, others = treat as closed.
        msg = str(e).lower()
        if "refused" in msg or getattr(e, "winerror", None) == 10061:
            return ip, port, _CLOSED
        if "timed out" in msg or getattr(e, "winerror", None) == 10060:
            return ip, port, _TIMEOUT
        return ip, port, _CLOSED


def _run_checks(tasks, timeout, workers):
    """Runs a (ip, port) task list through a ThreadPool, yields states."""
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_probe, ip, p, timeout) for (ip, p) in tasks]
        for f in as_completed(futures):
            yield f.result()


def _scan_with_retry(tasks, timeout, workers, retry_timeout) -> dict[tuple[str, int], str]:
    """Two-pass scan: quick first, then re-check timeouts with a longer
    timeout to weed out false negatives on dozing devices.
    """
    result: dict[tuple[str, int], str] = {}
    for ip, port, state in _run_checks(tasks, timeout, workers):
        result[(ip, port)] = state
    to_retry = [(ip, p) for (ip, p), s in result.items() if s == _TIMEOUT]
    if to_retry and retry_timeout > timeout:
        for ip, port, state in _run_checks(to_retry, retry_timeout, max(1, workers // 2)):
            result[(ip, port)] = state
    return result


def parse_ports(spec: str) -> tuple[int, ...]:
    """Parse a port spec like '22,80,443', '1-1024', 'top1024', or 'all'."""
    spec = (spec or "").strip().lower()
    if spec in ("", "default", "lan"):
        return LAN_PORTS
    if spec == "wan":
        return COMMON_PORTS
    if spec == "all":
        return tuple(range(1, 65536))
    if spec in ("top1024", "top1k", "common"):
        return TOP1024_PLUS
    if spec == "top100":
        return LAN_PORTS
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            out.update(range(int(lo), int(hi) + 1))
        else:
            out.add(int(chunk))
    valid = {p for p in out if 1 <= p <= 65535}
    if not valid:
        raise ValueError(f"no valid ports in {spec!r}")
    return tuple(sorted(valid))


def scan(ip: str | None = None, ports=COMMON_PORTS, timeout: float = 1.5,
         workers: int = 32, retry_timeout: float = 3.5) -> dict:
    """Scan the given (or public) IP. Used by `c6u portscan`."""
    ip = ip or publicip_mod.fetch_public_ip()
    if not ip:
        return {"ip": None, "open": [], "error": "no public ip"}
    tasks = [(ip, p) for p in ports]
    states = _scan_with_retry(tasks, timeout, workers, retry_timeout)
    open_ports = sorted(p for (_, p), s in states.items() if s == _OPEN)
    return {"ip": ip, "checked": len(ports), "open": open_ports}


def scan_host(ip: str, ports=LAN_PORTS, timeout: float = 1.0,
              workers: int = 32, retry_timeout: float = 2.5) -> list[int]:
    """Scan a single host, return sorted list of open ports."""
    tasks = [(ip, p) for p in ports]
    states = _scan_with_retry(tasks, timeout, workers, retry_timeout)
    return sorted(p for (_, p), s in states.items() if s == _OPEN)


def scan_lan(ports=LAN_PORTS, timeout: float = 1.0, workers: int = 48,
             retry_timeout: float = 2.5, include_gateway: bool = True) -> dict:
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

    tasks = [(t["ip"], p) for t in targets for p in ports]
    states = _scan_with_retry(tasks, timeout, workers, retry_timeout)
    open_by_ip: dict[str, list[int]] = {t["ip"]: [] for t in targets}
    timeout_by_ip: dict[str, int] = {t["ip"]: 0 for t in targets}
    for (ip, port), state in states.items():
        if state == _OPEN:
            open_by_ip[ip].append(port)
        elif state == _TIMEOUT:
            timeout_by_ip[ip] = timeout_by_ip.get(ip, 0) + 1

    for t in targets:
        t["open"] = sorted(open_by_ip.get(t["ip"], []))
        t["timed_out"] = timeout_by_ip.get(t["ip"], 0)
    return {
        "devices": targets,
        "checked_per_host": len(ports),
        "total_checks": len(tasks),
        "reachable_hosts": sum(1 for t in targets if t["open"]),
        "total_timeouts": sum(timeout_by_ip.values()),
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
