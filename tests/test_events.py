"""Event log + recent_events query."""
from c6u import db


def test_event_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "e.sqlite3")
    db.record_event("device_joined", "AA:BB:CC:DD:EE:FF", '{"hostname":"x"}')
    db.record_event("device_left", "AA:BB:CC:DD:EE:FF", None)
    rows = db.recent_events(10)
    assert len(rows) == 2
    assert rows[0]["kind"] == "device_left"
    assert rows[1]["mac"] == "AA:BB:CC:DD:EE:FF"
