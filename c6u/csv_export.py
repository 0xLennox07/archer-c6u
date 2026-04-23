"""CSV export for snapshots, devices, and report tables."""
from __future__ import annotations

import csv
from pathlib import Path

from . import db as db_mod


def export_snapshots(out: Path, days: int = 30) -> int:
    import time
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM snapshot WHERE ts >= ? ORDER BY ts ASC", (cutoff,)
        ).fetchall()
    with open(out, "w", newline="", encoding="utf-8") as fh:
        if not rows:
            return 0
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows:
            w.writerow(dict(r))
    return len(rows)


def export_devices(out: Path, days: int = 30) -> int:
    import time
    cutoff = int(time.time()) - days * 86400
    with db_mod.connect() as conn:
        rows = conn.execute(
            "SELECT * FROM device_sample WHERE ts >= ? ORDER BY ts ASC", (cutoff,)
        ).fetchall()
    with open(out, "w", newline="", encoding="utf-8") as fh:
        if not rows:
            return 0
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows:
            w.writerow(dict(r))
    return len(rows)
