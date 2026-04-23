"""Guess device type using vendor + hostname + mDNS + port hints.

This is a heuristic — good enough to tell "iPhone" from "Roku" from "Raspberry Pi".
"""
from __future__ import annotations

import re
import socket
from concurrent.futures import ThreadPoolExecutor

from . import discover as discover_mod
from . import vendor as vendor_mod


HOSTNAME_PATTERNS = [
    (re.compile(r"iphone|ipad", re.I), "Apple iOS"),
    (re.compile(r"macbook|imac|\bmac\b", re.I), "Apple Mac"),
    (re.compile(r"android", re.I), "Android"),
    (re.compile(r"galaxy", re.I), "Samsung Galaxy"),
    (re.compile(r"pixel", re.I), "Google Pixel"),
    (re.compile(r"\bps[345]\b|playstation", re.I), "PlayStation"),
    (re.compile(r"xbox", re.I), "Xbox"),
    (re.compile(r"nintendo|switch", re.I), "Nintendo Switch"),
    (re.compile(r"raspberrypi|\brpi\b", re.I), "Raspberry Pi"),
    (re.compile(r"roku", re.I), "Roku"),
    (re.compile(r"chromecast|googlehome|\bnest\b", re.I), "Google Home/Cast"),
    (re.compile(r"echo|\balexa\b", re.I), "Amazon Echo"),
    (re.compile(r"printer|-hp-|canon|epson|brother|hp-", re.I), "Printer"),
    (re.compile(r"tv\b|smart-?tv|\bbravia\b|lg-?tv|webos", re.I), "Smart TV"),
    (re.compile(r"\bfire(tv|stick)?\b", re.I), "Amazon Fire TV"),
]

VENDOR_HINTS = [
    (re.compile(r"apple", re.I), "Apple device"),
    (re.compile(r"samsung", re.I), "Samsung device"),
    (re.compile(r"google", re.I), "Google device"),
    (re.compile(r"amazon", re.I), "Amazon device"),
    (re.compile(r"raspberry", re.I), "Raspberry Pi"),
    (re.compile(r"espressif", re.I), "ESP32/ESP8266 (IoT)"),
    (re.compile(r"sony", re.I), "Sony device"),
    (re.compile(r"microsoft|xbox", re.I), "Microsoft/Xbox"),
    (re.compile(r"nintendo", re.I), "Nintendo"),
    (re.compile(r"roku", re.I), "Roku"),
    (re.compile(r"nest labs|google nest", re.I), "Google Nest"),
    (re.compile(r"philips", re.I), "Philips (Hue?)"),
    (re.compile(r"tuya|broadlink|xiaomi", re.I), "IoT (Tuya/Xiaomi/Broadlink)"),
]

MDNS_SERVICE_HINTS = {
    "_airplay._tcp.local.": "AirPlay (Apple TV/HomePod)",
    "_googlecast._tcp.local.": "Google Cast",
    "_companion-link._tcp.local.": "Apple device",
    "_device-info._tcp.local.": "generic mDNS device",
    "_ipp._tcp.local.": "Printer (IPP)",
    "_printer._tcp.local.": "Printer",
    "_raop._tcp.local.": "AirPlay audio",
    "_hap._tcp.local.": "HomeKit accessory",
    "_spotify-connect._tcp.local.": "Spotify Connect",
    "_ssh._tcp.local.": "has SSH",
    "_workstation._tcp.local.": "workstation",
}

PROBE_PORTS = (22, 80, 443, 515, 631, 5000, 5353, 8008, 8009, 8080, 9100, 32400)


def _port_open(ip: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False


def probe_ports(ip: str, ports=PROBE_PORTS, workers: int = 8) -> list[int]:
    open_ports = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for port, ok in zip(ports, ex.map(lambda p: _port_open(ip, p), ports)):
            if ok:
                open_ports.append(port)
    return open_ports


def fingerprint(mac: str, hostname: str | None = None, ip: str | None = None,
                mdns_hits: list[dict] | None = None,
                scan_ports: bool = False) -> dict:
    kind: list[str] = []
    confidence = 0
    if hostname:
        for pat, label in HOSTNAME_PATTERNS:
            if pat.search(hostname):
                kind.append(label)
                confidence += 3
                break
    vendor = vendor_mod.vendor(mac) or ""
    if vendor:
        for pat, label in VENDOR_HINTS:
            if pat.search(vendor):
                kind.append(label)
                confidence += 2
                break
    if mdns_hits:
        for hit in mdns_hits:
            svc = hit.get("service")
            label = MDNS_SERVICE_HINTS.get(svc)
            if label:
                kind.append(label)
                confidence += 1
    open_ports: list[int] = []
    if scan_ports and ip:
        open_ports = probe_ports(ip)
        if 631 in open_ports or 515 in open_ports or 9100 in open_ports:
            kind.append("Printer")
            confidence += 2
        if 8008 in open_ports or 8009 in open_ports:
            kind.append("Google Cast")
            confidence += 2
        if 32400 in open_ports:
            kind.append("Plex server")
            confidence += 3
        if 22 in open_ports:
            kind.append("has SSH")
    # Dedup, preserve order.
    seen, dedup = set(), []
    for k in kind:
        if k not in seen:
            seen.add(k); dedup.append(k)
    return {
        "mac": mac, "ip": ip, "hostname": hostname,
        "vendor": vendor, "guesses": dedup,
        "open_ports": open_ports, "confidence": confidence,
    }


def fingerprint_all(devices: list[dict], scan_ports: bool = False,
                    mdns_timeout: float = 3.0) -> list[dict]:
    """Fingerprint every device using a single mDNS sweep for efficiency."""
    mdns = discover_mod.scan_all(timeout=mdns_timeout)["mdns"] if scan_ports else []
    by_ip: dict[str, list[dict]] = {}
    for hit in mdns:
        for addr in hit.get("addresses") or []:
            by_ip.setdefault(addr, []).append(hit)
    out = []
    for d in devices:
        ip = d.get("ip")
        out.append(fingerprint(
            mac=d["mac"], hostname=d.get("hostname"), ip=ip,
            mdns_hits=by_ip.get(ip, []), scan_ports=scan_ports,
        ))
    return out
