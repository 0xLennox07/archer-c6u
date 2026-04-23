"""NetFlow v5 receiver (best-effort v9 detection).

When you get a managed switch / router that can export flows, point its flow
collector at this machine's IP on port 2055. Records land in the flow_sample
table and `c6u netflow top` + the web `/flows` page use them.

NetFlow v5 packet layout:
    14-byte header:
        version     u16
        count       u16       (number of flow records)
        sys_uptime  u32
        unix_secs   u32
        unix_nsecs  u32
        flow_seq    u32
        engine      u8 + u8
        sampling    u16
    48-byte records:
        srcaddr, dstaddr       u32 each
        nexthop                u32
        input, output          u16 each
        dPkts, dOctets         u32 each
        first, last            u32 each (sys_uptime ms at flow start/end)
        srcport, dstport       u16 each
        pad1                   u8
        tcp_flags, prot, tos   u8 each
        src_as, dst_as         u16 each
        src_mask, dst_mask     u8 each
        pad2                   u16
"""
from __future__ import annotations

import logging
import socket
import struct
import time
from socket import inet_ntoa

from . import db as db_mod

log = logging.getLogger(__name__)

FLOW_SCHEMA = """
CREATE TABLE IF NOT EXISTS flow_sample (
  ts         INTEGER,
  src_ip     TEXT,
  dst_ip     TEXT,
  src_port   INTEGER,
  dst_port   INTEGER,
  protocol   INTEGER,
  bytes      INTEGER,
  packets    INTEGER,
  duration_ms INTEGER,
  tcp_flags  INTEGER,
  exporter   TEXT
);
CREATE INDEX IF NOT EXISTS idx_flow_ts   ON flow_sample(ts);
CREATE INDEX IF NOT EXISTS idx_flow_src  ON flow_sample(src_ip);
CREATE INDEX IF NOT EXISTS idx_flow_dst  ON flow_sample(dst_ip);
"""


def _ensure_schema() -> None:
    with db_mod.connect() as conn:
        conn.executescript(FLOW_SCHEMA)


def parse_v5(data: bytes, exporter_ip: str = "") -> list[dict]:
    if len(data) < 24:
        return []
    version, count = struct.unpack("!HH", data[:4])
    if version != 5:
        return []
    out: list[dict] = []
    ts = int(time.time())
    offset = 24
    for _ in range(min(count, (len(data) - 24) // 48)):
        rec = data[offset:offset + 48]
        if len(rec) < 48:
            break
        (src_raw, dst_raw, _nh, _in, _out,
         d_pkts, d_octets, first, last,
         src_port, dst_port,
         _pad1, tcp_flags, prot, _tos,
         _src_as, _dst_as, _smask, _dmask, _pad2) = struct.unpack(
            "!4s4s4sHHIIIIHHBBBBHHBBH", rec)
        out.append({
            "ts": ts,
            "src_ip": inet_ntoa(src_raw),
            "dst_ip": inet_ntoa(dst_raw),
            "src_port": src_port,
            "dst_port": dst_port,
            "protocol": prot,
            "bytes": d_octets,
            "packets": d_pkts,
            "duration_ms": max(0, last - first),
            "tcp_flags": tcp_flags,
            "exporter": exporter_ip,
        })
        offset += 48
    return out


def _persist(rows: list[dict]) -> None:
    if not rows:
        return
    with db_mod.connect() as conn:
        conn.executemany(
            "INSERT INTO flow_sample VALUES "
            "(:ts,:src_ip,:dst_ip,:src_port,:dst_port,:protocol,:bytes,"
            ":packets,:duration_ms,:tcp_flags,:exporter)",
            rows,
        )


def run(port: int = 2055, bind: str = "0.0.0.0") -> None:
    _ensure_schema()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((bind, port))
    log.info("NetFlow receiver on UDP %s:%d (v5; v9 detected but not decoded)", bind, port)
    total_flows = 0
    while True:
        try:
            data, addr = sock.recvfrom(8192)
        except KeyboardInterrupt:
            break
        try:
            version = struct.unpack("!H", data[:2])[0] if data else 0
            if version == 5:
                rows = parse_v5(data, exporter_ip=addr[0])
                _persist(rows)
                total_flows += len(rows)
            elif version == 9:
                log.debug("v9 flow from %s (not decoded)", addr[0])
            else:
                log.debug("unknown flow version %d from %s", version, addr[0])
        except Exception as e:
            log.warning("flow parse from %s failed: %s", addr, e)


def top(days: int = 1, by: str = "bytes", limit: int = 20) -> list[dict]:
    _ensure_schema()
    col = "SUM(bytes)" if by == "bytes" else "SUM(packets)" if by == "packets" else "COUNT(*)"
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        rows = conn.execute(
            f"""SELECT src_ip, dst_ip, protocol, dst_port,
                        {col} AS score,
                        SUM(bytes) AS tot_bytes, SUM(packets) AS tot_packets
                FROM flow_sample WHERE ts >= ?
                GROUP BY src_ip, dst_ip, protocol, dst_port
                ORDER BY score DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def by_src_ip(days: int = 1, limit: int = 20) -> list[dict]:
    _ensure_schema()
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        rows = conn.execute(
            """SELECT src_ip, SUM(bytes) AS tot_bytes, SUM(packets) AS tot_packets,
                      COUNT(DISTINCT dst_ip) AS uniq_peers
               FROM flow_sample WHERE ts >= ?
               GROUP BY src_ip ORDER BY tot_bytes DESC LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
    return [dict(r) for r in rows]
