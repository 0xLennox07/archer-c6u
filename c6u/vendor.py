"""MAC OUI → vendor name lookup. Cached to avoid hammering the lib."""
from __future__ import annotations

from functools import lru_cache

_lookup = None


def _get():
    global _lookup
    if _lookup is None:
        from mac_vendor_lookup import MacLookup
        _lookup = MacLookup()
    return _lookup


@lru_cache(maxsize=4096)
def vendor(mac: str) -> str:
    if not mac:
        return ""
    try:
        return _get().lookup(mac)
    except Exception:
        return ""
