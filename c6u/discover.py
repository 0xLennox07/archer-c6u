"""mDNS + SSDP discovery — find Chromecasts, AirPlay, printers, smart bulbs etc."""
from __future__ import annotations

import socket
import time
from threading import Thread


def mdns_scan(timeout: float = 4.0) -> list[dict]:
    """Browse a curated list of common mDNS service types."""
    from zeroconf import ServiceBrowser, Zeroconf, ServiceListener

    services = [
        "_googlecast._tcp.local.",
        "_airplay._tcp.local.",
        "_raop._tcp.local.",        # AirPlay receivers
        "_ipp._tcp.local.",         # IPP printers
        "_printer._tcp.local.",
        "_hap._tcp.local.",         # HomeKit
        "_spotify-connect._tcp.local.",
        "_workstation._tcp.local.",
        "_ssh._tcp.local.",
        "_sftp-ssh._tcp.local.",
        "_smb._tcp.local.",
        "_http._tcp.local.",
        "_homeassistant._tcp.local.",
    ]

    found: list[dict] = []
    seen: set[tuple] = set()

    class L(ServiceListener):
        def add_service(self, zc, type_, name):
            try:
                info = zc.get_service_info(type_, name, timeout=1500)
                if not info:
                    return
                addrs = [socket.inet_ntoa(a) for a in info.addresses]
                key = (type_, name)
                if key in seen:
                    return
                seen.add(key)
                found.append({
                    "service": type_.rstrip("."),
                    "name": name.rstrip("."),
                    "host": (info.server or "").rstrip("."),
                    "port": info.port,
                    "addresses": addrs,
                })
            except Exception:
                pass

        def update_service(self, *_): pass
        def remove_service(self, *_): pass

    zc = Zeroconf()
    listener = L()
    browsers = [ServiceBrowser(zc, s, listener) for s in services]
    time.sleep(timeout)
    for b in browsers:
        try: b.cancel()
        except Exception: pass
    zc.close()
    return found


def ssdp_scan(timeout: float = 3.0) -> list[dict]:
    """SSDP M-SEARCH — finds UPnP devices (routers, smart TVs, NAS, IoT bridges)."""
    msg = (
        "M-SEARCH * HTTP/1.1\r\n"
        "HOST: 239.255.255.250:1900\r\n"
        "MAN: \"ssdp:discover\"\r\n"
        f"MX: {int(timeout)}\r\n"
        "ST: ssdp:all\r\n\r\n"
    ).encode()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(timeout)
    sock.sendto(msg, ("239.255.255.250", 1900))

    seen: dict[tuple, dict] = {}
    end = time.time() + timeout
    while time.time() < end:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            break
        text = data.decode(errors="replace")
        headers = {}
        for line in text.splitlines()[1:]:
            if ":" in line:
                k, _, v = line.partition(":")
                headers[k.strip().upper()] = v.strip()
        key = (addr[0], headers.get("ST", ""))
        if key not in seen:
            seen[key] = {
                "ip": addr[0],
                "st": headers.get("ST"),
                "server": headers.get("SERVER"),
                "location": headers.get("LOCATION"),
                "usn": headers.get("USN"),
            }
    sock.close()
    return list(seen.values())


def scan_all(timeout: float = 4.0) -> dict:
    """Run mDNS and SSDP in parallel, return combined results."""
    out: dict = {"mdns": [], "ssdp": []}

    def t1(): out["mdns"] = mdns_scan(timeout=timeout)
    def t2(): out["ssdp"] = ssdp_scan(timeout=min(timeout, 3.0))

    threads = [Thread(target=t1, daemon=True), Thread(target=t2, daemon=True)]
    for t in threads: t.start()
    for t in threads: t.join(timeout + 2)
    return out
