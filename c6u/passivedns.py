"""Passive DNS — reverse lookups from the DNS filter's observed replies.

Populated as a byproduct of dnsfilter when the forwarding resolver runs.
Falls back to live rDNS (rdns.reverse) if the IP isn't in the cache.
"""
from __future__ import annotations

from . import db as db_mod
from . import rdns as rdns_mod


def hostname_for(ip: str) -> str | None:
    """Look up an IP's hostname, preferring observed A-record data over live rDNS."""
    with db_mod.connect() as conn:
        row = conn.execute(
            "SELECT hostname FROM pdns_cache WHERE ip = ? ORDER BY last_seen DESC LIMIT 1",
            (ip,),
        ).fetchone()
    if row and row["hostname"]:
        return row["hostname"]
    return rdns_mod.reverse(ip)


def recent(ip: str | None = None, hostname: str | None = None, limit: int = 100) -> list[dict]:
    with db_mod.connect() as conn:
        if ip:
            rows = conn.execute(
                "SELECT * FROM pdns_cache WHERE ip = ? ORDER BY last_seen DESC LIMIT ?",
                (ip, limit),
            ).fetchall()
        elif hostname:
            rows = conn.execute(
                "SELECT * FROM pdns_cache WHERE hostname LIKE ? ORDER BY last_seen DESC LIMIT ?",
                (f"%{hostname}%", limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM pdns_cache ORDER BY last_seen DESC LIMIT ?", (limit,),
            ).fetchall()
    return [dict(r) for r in rows]
