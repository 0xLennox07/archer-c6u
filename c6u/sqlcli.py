"""Ad-hoc SQL against the history DB."""
from __future__ import annotations

import sqlite3

from . import db as db_mod


DANGEROUS_PREFIXES = ("DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "REPLACE")


def run(sql: str, params: tuple = (), allow_mutate: bool = False) -> tuple[list[str], list[tuple]]:
    """Returns (columns, rows). Blocks mutations by default."""
    stmt = sql.strip().rstrip(";").strip()
    if not allow_mutate:
        first = stmt.upper().split(None, 1)[0] if stmt else ""
        if first in DANGEROUS_PREFIXES:
            raise ValueError(f"{first} blocked — pass allow_mutate=True if you really want this.")
    with db_mod.connect() as conn:
        try:
            cur = conn.execute(stmt, params)
        except sqlite3.Error as e:
            raise RuntimeError(f"SQL error: {e}") from e
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
    return cols, [tuple(r) for r in rows]


def tables() -> list[str]:
    cols, rows = run("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    return [r[0] for r in rows]


def schema(table: str) -> list[tuple]:
    _, rows = run(f"PRAGMA table_info({table})")
    return rows
