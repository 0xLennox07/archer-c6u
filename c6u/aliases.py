"""MAC alias map: aliases.json — { "AA:BB:CC:DD:EE:FF": "Mom's iPhone" }."""
from __future__ import annotations

import json
from pathlib import Path

ALIASES_PATH = Path(__file__).resolve().parent.parent / "aliases.json"


def _norm(mac: str) -> str:
    return mac.upper().replace("-", ":") if mac else ""


def load() -> dict[str, str]:
    if not ALIASES_PATH.exists():
        return {}
    try:
        with ALIASES_PATH.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return {_norm(k): v for k, v in raw.items()}
    except Exception:
        return {}


def save(aliases: dict[str, str]) -> None:
    ALIASES_PATH.write_text(
        json.dumps({_norm(k): v for k, v in aliases.items()}, indent=2),
        encoding="utf-8",
    )


def lookup(mac: str) -> str | None:
    return load().get(_norm(mac))


def set_alias(mac: str, name: str) -> None:
    a = load()
    a[_norm(mac)] = name
    save(a)


def remove_alias(mac: str) -> bool:
    a = load()
    key = _norm(mac)
    if key not in a:
        return False
    del a[key]
    save(a)
    return True
