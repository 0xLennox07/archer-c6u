"""FTS5 fulltext search across the event table.

Builds a `event_fts` virtual table that mirrors `event`. `rebuild()` repopulates
it from scratch; `query(q)` runs a MATCH query.
"""
from __future__ import annotations

from . import db as db_mod


FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS event_fts USING fts5(
  kind, mac, payload,
  content='event', content_rowid='rowid'
);
"""


def _has_fts5(conn) -> bool:
    try:
        conn.execute("SELECT fts5(?)", ("tokenize",))
        return True
    except Exception:
        pass
    try:
        conn.execute("CREATE VIRTUAL TABLE __probe USING fts5(x)")
        conn.execute("DROP TABLE __probe")
        return True
    except Exception:
        return False


def rebuild() -> int:
    with db_mod.connect() as conn:
        if not _has_fts5(conn):
            raise RuntimeError("your SQLite build has no FTS5 support")
        # Drop-and-recreate is safer than DELETE on an external-content FTS5 table
        # (DELETE triggers content-table reads that can fail on a fresh DB).
        conn.execute("DROP TABLE IF EXISTS event_fts")
        conn.executescript(FTS_SCHEMA)
        conn.execute(
            "INSERT INTO event_fts(rowid, kind, mac, payload) "
            "SELECT rowid, COALESCE(kind,''), COALESCE(mac,''), COALESCE(payload,'') FROM event"
        )
        n = conn.execute("SELECT COUNT(*) FROM event_fts").fetchone()[0]
    return n


def query(q: str, limit: int = 100) -> list[dict]:
    with db_mod.connect() as conn:
        if not _has_fts5(conn):
            raise RuntimeError("your SQLite build has no FTS5 support")
        conn.executescript(FTS_SCHEMA)
        rows = conn.execute(
            """
            SELECT e.ts, e.kind, e.mac, e.payload
              FROM event_fts f JOIN event e ON e.rowid = f.rowid
             WHERE event_fts MATCH ?
             ORDER BY e.ts DESC LIMIT ?
            """, (q, limit),
        ).fetchall()
    return [dict(r) for r in rows]
