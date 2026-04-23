"""Mini Pi-hole: forwarding DNS resolver with blocklist filtering + per-MAC policy + query logging.

Run it with `c6u dns run` then point your router's DHCP "DNS server" at this machine's LAN IP.
Every LAN device will then resolve through here, each query is logged to SQLite, blocked domains
are answered with 0.0.0.0 (NXDOMAIN optional), and passive-DNS records are populated.

Config (config.json → dns):
    "dns": {
      "port": 53,
      "upstreams": ["https://cloudflare-dns.com/dns-query",
                    "https://dns.google/resolve"],
      "blocklists": ["https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"],
      "policies": {
        "default": {"block": true, "lists": ["ads", "tracking"]},
        "AA:BB:CC:DD:EE:FF": {"block": true, "lists": ["ads", "tracking", "social"]}
      },
      "log": true,
      "ttl": 300
    }
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from . import config as cfg_mod
from . import db as db_mod

log = logging.getLogger(__name__)

DNS_SCHEMA = """
CREATE TABLE IF NOT EXISTS dns_query (
  ts         INTEGER,
  client_ip  TEXT,
  client_mac TEXT,
  qname      TEXT,
  qtype      TEXT,
  answer     TEXT,
  blocked    INTEGER,
  cached     INTEGER,
  latency_ms REAL
);
CREATE INDEX IF NOT EXISTS idx_dns_ts ON dns_query(ts);
CREATE INDEX IF NOT EXISTS idx_dns_qname ON dns_query(qname);
CREATE INDEX IF NOT EXISTS idx_dns_client ON dns_query(client_ip);

CREATE TABLE IF NOT EXISTS dns_block (
  domain     TEXT PRIMARY KEY,
  list_name  TEXT
);

CREATE TABLE IF NOT EXISTS pdns_cache (
  ip         TEXT PRIMARY KEY,
  hostname   TEXT,
  first_seen INTEGER,
  last_seen  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_pdns_host ON pdns_cache(hostname);
"""


def _ensure_schema() -> None:
    with db_mod.connect() as conn:
        conn.executescript(DNS_SCHEMA)


# ---------- Blocklists ----------

def _parse_hosts_line(line: str) -> str | None:
    """Parse a line in `hosts`-file format. Returns the blocked domain or None."""
    line = line.split("#", 1)[0].strip()
    if not line:
        return None
    parts = line.split()
    # Accept: "0.0.0.0 bad.domain", "127.0.0.1 bad.domain", or just "bad.domain".
    candidate = parts[-1].lower()
    if not candidate or candidate in ("localhost", "broadcasthost"):
        return None
    # crude sanity: must have a dot
    if "." not in candidate or candidate.startswith("."):
        return None
    return candidate


def update_blocklists(urls: list[str] | None = None) -> dict:
    _ensure_schema()
    cfg = cfg_mod.load_config(interactive=False)
    dns_cfg = cfg.get("dns") or {}
    urls = urls or dns_cfg.get("blocklists") or [
        "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
    ]
    total = 0
    loaded_by_list: dict[str, int] = {}
    with db_mod.connect() as conn:
        conn.execute("DELETE FROM dns_block")
        for url in urls:
            list_name = url.rsplit("/", 1)[-1] or url
            count = 0
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                for line in r.text.splitlines():
                    domain = _parse_hosts_line(line)
                    if not domain:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO dns_block(domain,list_name) VALUES (?,?)",
                        (domain, list_name),
                    )
                    count += 1
            except Exception as e:
                log.warning("blocklist %s failed: %s", url, e)
            loaded_by_list[list_name] = count
            total += count
    return {"loaded": loaded_by_list, "total": total}


def load_blockset() -> set[str]:
    _ensure_schema()
    with db_mod.connect() as conn:
        rows = conn.execute("SELECT domain FROM dns_block").fetchall()
    return {r["domain"] for r in rows}


# ---------- Policy ----------

def _policy_for(client_ip: str, client_mac: str | None, cfg: dict) -> dict:
    pols = (cfg.get("dns") or {}).get("policies") or {}
    if client_mac:
        mac_u = client_mac.upper()
        for k, v in pols.items():
            if k.upper() == mac_u:
                return v
    return pols.get("default") or {"block": True}


# ---------- ARP lookup (IP -> MAC) ----------

_ARP_CACHE: dict[str, tuple[str, float]] = {}
_ARP_TTL = 30.0


def _arp_lookup(ip: str) -> str | None:
    now = time.time()
    cached = _ARP_CACHE.get(ip)
    if cached and now - cached[1] < _ARP_TTL:
        return cached[0]
    mac = None
    try:
        from . import arpwatch
        table = arpwatch.read_arp_table()
        mac = table.get(ip)
        # Warm cache for *all* ARP entries at once.
        for i, m in table.items():
            _ARP_CACHE[i] = (m, now)
    except Exception:
        pass
    return mac


# ---------- Passive DNS ----------

def _record_pdns(ip: str, hostname: str) -> None:
    try:
        ipaddress.ip_address(ip)
    except ValueError:
        return
    now = int(time.time())
    with db_mod.connect() as conn:
        conn.execute(
            """INSERT INTO pdns_cache(ip,hostname,first_seen,last_seen)
               VALUES (?,?,?,?)
               ON CONFLICT(ip) DO UPDATE SET hostname=excluded.hostname,
                                             last_seen=excluded.last_seen""",
            (ip, hostname, now, now),
        )


# ---------- Upstream resolver (DoH) ----------

def _doh_query(qname: str, qtype: str, upstream: str, timeout: float = 4.0):
    params = {"name": qname, "type": qtype}
    headers = {"Accept": "application/dns-json"}
    r = requests.get(upstream, params=params, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _resolve(qname: str, qtype: str, cfg: dict) -> dict:
    upstreams = (cfg.get("dns") or {}).get("upstreams") or [
        "https://cloudflare-dns.com/dns-query",
        "https://dns.google/resolve",
    ]
    last_err: Exception | None = None
    for up in upstreams:
        try:
            return _doh_query(qname, qtype, up)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"all upstreams failed: {last_err}")


# ---------- Query log ----------

def _log_query(client_ip: str, mac: str | None, qname: str, qtype: str,
                answer: str, blocked: bool, cached: bool, latency_ms: float) -> None:
    with db_mod.connect() as conn:
        conn.execute(
            "INSERT INTO dns_query VALUES (?,?,?,?,?,?,?,?,?)",
            (int(time.time()), client_ip, mac, qname.lower(), qtype,
             answer, int(blocked), int(cached), latency_ms),
        )


# ---------- DNS server ----------

_CACHE: dict[tuple[str, str], tuple[dict, float]] = {}  # (qname,qtype) -> (answer, expires_at)


def _check_blocked(qname: str, blockset: set[str]) -> bool:
    qname = qname.lower().rstrip(".")
    if qname in blockset:
        return True
    # subdomain match: block ads.google.com if google.com isn't blocked but doubleclick.net is.
    parts = qname.split(".")
    for i in range(1, len(parts)):
        if ".".join(parts[i:]) in blockset:
            return True
    return False


def handle_query(data: bytes, client_ip: str, blockset: set[str], cfg: dict) -> bytes:
    """Given a raw DNS wire packet, return the raw response bytes."""
    from dnslib import DNSRecord, RR, A, AAAA, QTYPE, RCODE

    req = DNSRecord.parse(data)
    if not req.questions:
        return req.reply().pack()
    q = req.questions[0]
    qname = str(q.qname).rstrip(".")
    qtype = QTYPE.get(q.qtype, str(q.qtype))
    t0 = time.perf_counter()
    mac = _arp_lookup(client_ip)
    pol = _policy_for(client_ip, mac, cfg)
    default_ttl = int((cfg.get("dns") or {}).get("ttl", 300))

    reply = req.reply()

    # Blocked?
    if pol.get("block", True) and _check_blocked(qname, blockset):
        if qtype == "A":
            reply.add_answer(RR(q.qname, rdata=A("0.0.0.0"), ttl=default_ttl))
        elif qtype == "AAAA":
            reply.add_answer(RR(q.qname, rdata=AAAA("::"), ttl=default_ttl))
        else:
            reply.header.rcode = RCODE.NXDOMAIN
        latency = (time.perf_counter() - t0) * 1000
        if (cfg.get("dns") or {}).get("log", True):
            _log_query(client_ip, mac, qname, qtype, "BLOCKED", True, False, latency)
        return reply.pack()

    # Cache hit?
    key = (qname.lower(), qtype)
    cached_entry = _CACHE.get(key)
    if cached_entry and cached_entry[1] > time.time():
        result, _ = cached_entry
        cached = True
    else:
        try:
            result = _resolve(qname, qtype, cfg)
            ttl_from_response = min((a.get("TTL") or default_ttl) for a in result.get("Answer", [])) if result.get("Answer") else default_ttl
            _CACHE[key] = (result, time.time() + max(30, ttl_from_response))
            cached = False
        except Exception as e:
            log.warning("resolve %s/%s failed: %s", qname, qtype, e)
            reply.header.rcode = RCODE.SERVFAIL
            return reply.pack()

    answers: list[str] = []
    for a in result.get("Answer") or []:
        if a.get("type") == 1:   # A
            reply.add_answer(RR(q.qname, rdata=A(a["data"]), ttl=a.get("TTL", default_ttl)))
            answers.append(a["data"])
            _record_pdns(a["data"], qname.lower())
        elif a.get("type") == 28:  # AAAA
            reply.add_answer(RR(q.qname, rdata=AAAA(a["data"]), ttl=a.get("TTL", default_ttl)))
            answers.append(a["data"])

    latency = (time.perf_counter() - t0) * 1000
    if (cfg.get("dns") or {}).get("log", True):
        _log_query(client_ip, mac, qname, qtype,
                   ",".join(answers) or f"rcode={result.get('Status', '?')}",
                   False, cached, latency)
    return reply.pack()


def run(port: int | None = None) -> None:
    """Start the DNS server. Blocks forever."""
    _ensure_schema()
    cfg = cfg_mod.load_config(interactive=False)
    dns_cfg = cfg.get("dns") or {}
    port = port or int(dns_cfg.get("port", 53))
    blockset = load_blockset()
    log.info("DNS filter starting on UDP :%d  (blocklist: %d domains)", port, len(blockset))

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", port))
    ex = ThreadPoolExecutor(max_workers=16)

    def _worker(data: bytes, addr):
        try:
            resp = handle_query(data, addr[0], blockset, cfg)
            sock.sendto(resp, addr)
        except Exception as e:
            log.warning("query from %s failed: %s", addr, e)

    while True:
        try:
            data, addr = sock.recvfrom(4096)
        except KeyboardInterrupt:
            break
        ex.submit(_worker, data, addr)


# ---------- Stats ----------

def stats(days: int = 1) -> dict:
    _ensure_schema()
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM dns_query WHERE ts >= ?", (cutoff,)).fetchone()[0]
        blocked = conn.execute("SELECT COUNT(*) FROM dns_query WHERE ts >= ? AND blocked = 1", (cutoff,)).fetchone()[0]
        top_dom = conn.execute(
            "SELECT qname, COUNT(*) AS n FROM dns_query WHERE ts >= ? "
            "GROUP BY qname ORDER BY n DESC LIMIT 20", (cutoff,),
        ).fetchall()
        top_blocked = conn.execute(
            "SELECT qname, COUNT(*) AS n FROM dns_query WHERE ts >= ? AND blocked = 1 "
            "GROUP BY qname ORDER BY n DESC LIMIT 20", (cutoff,),
        ).fetchall()
        top_clients = conn.execute(
            "SELECT client_ip, client_mac, COUNT(*) AS n FROM dns_query WHERE ts >= ? "
            "GROUP BY client_ip ORDER BY n DESC LIMIT 20", (cutoff,),
        ).fetchall()
    return {
        "days": days,
        "total": total, "blocked": blocked,
        "block_pct": (100.0 * blocked / total) if total else 0.0,
        "top_domains": [dict(r) for r in top_dom],
        "top_blocked": [dict(r) for r in top_blocked],
        "top_clients": [dict(r) for r in top_clients],
    }
