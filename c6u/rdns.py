"""Reverse DNS lookups. Cached because resolution is slow."""
from __future__ import annotations

import socket
from functools import lru_cache


@lru_cache(maxsize=1024)
def reverse(ip: str) -> str | None:
    if not ip:
        return None
    try:
        return socket.gethostbyaddr(ip)[0]
    except Exception:
        return None
