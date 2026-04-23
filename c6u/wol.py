"""Wake-on-LAN — resolve MAC from last-seen clients in the DB."""
from __future__ import annotations

import socket
import struct

from .db import connect


def resolve_mac(name_or_mac: str) -> str | None:
    """Accept either a MAC literal or a hostname seen in the last snapshot."""
    s = name_or_mac.strip()
    if ":" in s or "-" in s:
        return s.upper().replace("-", ":")
    with connect() as conn:
        row = conn.execute(
            """
            SELECT mac FROM device_sample
            WHERE hostname = ?
            ORDER BY ts DESC
            LIMIT 1
            """,
            (s,),
        ).fetchone()
    return row["mac"] if row else None


def send_wol(mac: str, broadcast: str = "255.255.255.255", port: int = 9) -> None:
    clean = mac.replace(":", "").replace("-", "")
    if len(clean) != 12:
        raise ValueError(f"Bad MAC: {mac!r}")
    packet = b"\xff" * 6 + bytes.fromhex(clean) * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast, port))
