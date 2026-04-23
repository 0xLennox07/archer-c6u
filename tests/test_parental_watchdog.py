"""Parental schedule evaluation + watchdog ping parser."""
import datetime as dt
import json

from c6u import parental, config as cfg_mod


def _write_rules(tmp_path, rules):
    p = tmp_path / "parental.json"
    p.write_text(json.dumps(rules))
    return p


def test_parental_day_window(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_mod, "ROOT", tmp_path)
    _write_rules(tmp_path, {"rules": [
        {"mac": "AA:BB:CC:00:00:01", "block": [
            {"dow": [0, 1, 2, 3, 4], "from": "14:00", "to": "16:00"}
        ]}
    ]})
    # Mon 15:00 → should block.
    mon = dt.datetime(2026, 1, 5, 15, 0)  # Jan 5 = Monday
    assert parental.should_block("AA:BB:CC:00:00:01", mon)
    # Same MAC, Sat 15:00 → allow.
    sat = dt.datetime(2026, 1, 10, 15, 0)
    assert not parental.should_block("AA:BB:CC:00:00:01", sat)


def test_parental_overnight_wrap(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_mod, "ROOT", tmp_path)
    _write_rules(tmp_path, {"rules": [
        {"mac": "AA:BB:CC:00:00:02", "block": [
            {"dow": list(range(7)), "from": "23:00", "to": "06:00"}
        ]}
    ]})
    late = dt.datetime(2026, 1, 5, 23, 30)
    early = dt.datetime(2026, 1, 6, 5, 30)
    mid = dt.datetime(2026, 1, 5, 10, 0)
    assert parental.should_block("AA:BB:CC:00:00:02", late)
    assert parental.should_block("AA:BB:CC:00:00:02", early)
    assert not parental.should_block("AA:BB:CC:00:00:02", mid)
