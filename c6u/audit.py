"""Signed event log — hash chain over the event table.

Every time you seal a window, we compute
    H_n = sha256(H_{n-1} || canonical(row_n))
for every event since the last seal and stick the final hash (+ a sealed range)
into the `audit_seal` table. `verify()` recomputes and reports any tamper.

It's append-only. Inserts, deletes, or edits anywhere in the range will
change every subsequent hash — making silent corruption detectable.
"""
from __future__ import annotations

import hashlib
import json
import time

from . import db as db_mod

AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_seal (
  ts         INTEGER PRIMARY KEY,
  start_ts   INTEGER,
  end_ts     INTEGER,
  start_id   INTEGER,
  end_id     INTEGER,
  n_events   INTEGER,
  final_hash TEXT
);
"""


def _ensure_schema() -> None:
    with db_mod.connect() as conn:
        conn.executescript(AUDIT_SCHEMA)


def _canonical(row) -> bytes:
    return json.dumps(
        {"rowid": row["rowid"], "ts": row["ts"], "kind": row["kind"],
         "mac": row["mac"] or "", "payload": row["payload"] or ""},
        separators=(",", ":"), sort_keys=True,
    ).encode("utf-8")


def _chain_hash(seed: str, rows) -> str:
    h = hashlib.sha256()
    h.update(seed.encode("utf-8"))
    for r in rows:
        h.update(hashlib.sha256(_canonical(r)).digest())
    return h.hexdigest()


def _last_seal(conn):
    return conn.execute(
        "SELECT * FROM audit_seal ORDER BY ts DESC LIMIT 1"
    ).fetchone()


def seal() -> dict:
    """Hash every event since the previous seal, store the new seal row."""
    _ensure_schema()
    now = int(time.time())
    with db_mod.connect() as conn:
        prev = _last_seal(conn)
        start_id = (prev["end_id"] if prev else 0) + 1
        rows = conn.execute(
            "SELECT rowid, ts, kind, mac, payload FROM event WHERE rowid >= ? ORDER BY rowid",
            (start_id,),
        ).fetchall()
        if not rows:
            return {"sealed": 0, "message": "no new events"}
        seed = prev["final_hash"] if prev else "GENESIS"
        final = _chain_hash(seed, rows)
        conn.execute(
            "INSERT INTO audit_seal VALUES (?,?,?,?,?,?,?)",
            (now, rows[0]["ts"], rows[-1]["ts"],
             rows[0]["rowid"], rows[-1]["rowid"], len(rows), final),
        )
    return {"sealed": len(rows), "start_id": start_id,
            "end_id": rows[-1]["rowid"], "final_hash": final}


def verify() -> dict:
    """Replay every seal's hash chain against the current event table contents.

    Returns a dict with `ok`, `seals`, and, if ok is False, the first seal
    that failed so you know the tampered window.
    """
    _ensure_schema()
    with db_mod.connect() as conn:
        seals = conn.execute(
            "SELECT * FROM audit_seal ORDER BY ts ASC"
        ).fetchall()
        if not seals:
            return {"ok": True, "seals": 0, "message": "no seals yet"}
        prev_hash = "GENESIS"
        for s in seals:
            rows = conn.execute(
                "SELECT rowid, ts, kind, mac, payload FROM event "
                "WHERE rowid BETWEEN ? AND ? ORDER BY rowid",
                (s["start_id"], s["end_id"]),
            ).fetchall()
            if len(rows) != s["n_events"]:
                return {"ok": False, "seals": len(seals),
                        "failed_at": dict(s),
                        "reason": f"row count {len(rows)} != recorded {s['n_events']}"}
            got = _chain_hash(prev_hash, rows)
            if got != s["final_hash"]:
                return {"ok": False, "seals": len(seals),
                        "failed_at": dict(s),
                        "reason": "hash mismatch (tamper or reorder)"}
            prev_hash = got
    return {"ok": True, "seals": len(seals),
            "chain_tip": prev_hash}
