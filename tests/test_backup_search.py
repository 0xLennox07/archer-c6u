"""Backup/restore round-trip and FTS5 search."""
import os

from c6u import backup, db, search, config as cfg_mod


def test_backup_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_mod, "ROOT", tmp_path)
    (tmp_path / "config.json").write_text('{"host":"x"}')
    (tmp_path / "aliases.json").write_text('{}')
    archive = backup.create()
    assert archive.exists()
    # Wipe and restore.
    (tmp_path / "config.json").unlink()
    names = backup.restore(archive)
    assert "config.json" in names
    assert (tmp_path / "config.json").exists()


def test_fts5_search(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "f.sqlite3")
    db.record_event("device_joined", mac="AA:BB:CC:00:11:22", payload="new laptop")
    db.record_event("public_ip_changed", payload="1.1.1.1 -> 2.2.2.2")
    try:
        n = search.rebuild()
    except RuntimeError:
        # SQLite without FTS5 support — skip.
        import pytest; pytest.skip("no FTS5")
    assert n >= 2
    rows = search.query("laptop")
    assert any("laptop" in (r.get("payload") or "") for r in rows)
