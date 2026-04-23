"""Heatmap + SQL CLI round trips."""
import time
import datetime as dt

from c6u import db, heatmap, sqlcli


def _seed(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "h.sqlite3")
    # Seed samples across a few hours + days.
    with db.connect() as conn:
        for offset in (0, 3600, 86400, 90000):
            ts = int(time.time()) - offset
            conn.execute(
                "INSERT OR REPLACE INTO device_sample VALUES (?,?,?,?,?,?,?,?,?,?)",
                (ts, "AA:BB:CC:11:22:33", "host", "10.0.0.1", "wifi", 0, 0, 0, 0, 1),
            )


def test_heatmap_counts(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    h = heatmap.heatmap("AA:BB:CC:11:22:33", days=7)
    total = sum(sum(r) for r in h["grid"])
    assert total == 4
    assert len(h["grid"]) == 7 and len(h["grid"][0]) == 24


def test_sqlcli_read_only(monkeypatch, tmp_path):
    _seed(monkeypatch, tmp_path)
    cols, rows = sqlcli.run("SELECT COUNT(*) FROM device_sample")
    assert rows[0][0] == 4
    import pytest
    with pytest.raises(ValueError):
        sqlcli.run("DELETE FROM device_sample")
