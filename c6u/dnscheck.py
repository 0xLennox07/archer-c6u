"""Detect ISP DNS hijacking / transparent DNS proxying.

For each probe domain, compare:
  - system resolver's answer (whatever the router hands out via DHCP)
  - Cloudflare DoH answer (1.1.1.1)
  - Google DoH answer (8.8.8.8)
"""
from __future__ import annotations

import socket
from typing import Iterable

import requests

DEFAULT_DOMAINS = ("example.com", "google.com", "cloudflare.com", "github.com")
DOH_ENDPOINTS = {
    "cloudflare": "https://cloudflare-dns.com/dns-query",
    "google":     "https://dns.google/resolve",
}


def _doh(name: str, url: str) -> list[str]:
    params = {"name": name, "type": "A"}
    headers = {"Accept": "application/dns-json"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=4)
        r.raise_for_status()
        answers = (r.json() or {}).get("Answer", []) or []
        return sorted({a["data"] for a in answers if a.get("type") == 1})
    except Exception:
        return []


def _system(name: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(name, None, family=socket.AF_INET)
        return sorted({i[4][0] for i in infos})
    except Exception:
        return []


def check(domains: Iterable[str] = DEFAULT_DOMAINS) -> dict:
    results = []
    hijack_suspects = []
    for d in domains:
        sys_a = _system(d)
        cf_a = _doh(d, DOH_ENDPOINTS["cloudflare"])
        go_a = _doh(d, DOH_ENDPOINTS["google"])
        # "Suspect" if system answer disjoint from BOTH upstream answers.
        divergent = bool(sys_a) and bool(cf_a or go_a) and not (
            set(sys_a) & (set(cf_a) | set(go_a))
        )
        if divergent:
            hijack_suspects.append({"domain": d, "system": sys_a,
                                     "cloudflare": cf_a, "google": go_a})
        results.append({
            "domain": d, "system": sys_a,
            "cloudflare": cf_a, "google": go_a,
            "divergent": divergent,
        })
    return {
        "checked": len(results),
        "hijack_suspected": len(hijack_suspects),
        "suspects": hijack_suspects,
        "results": results,
    }
