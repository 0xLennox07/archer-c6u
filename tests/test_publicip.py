"""Public IP change detection logic."""
from unittest.mock import patch

from c6u import db, publicip


def test_first_record_no_change(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p.sqlite3")
    with patch.object(publicip, "fetch_public_ip", return_value="1.2.3.4"):
        r = publicip.check_and_record()
    assert r["ip"] == "1.2.3.4"
    assert r["previous"] is None
    assert r["changed"] is False


def test_change_detected(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "p.sqlite3")
    with patch.object(publicip, "fetch_public_ip", return_value="1.1.1.1"):
        publicip.check_and_record()
    with patch.object(publicip, "fetch_public_ip", return_value="2.2.2.2"):
        r = publicip.check_and_record()
    assert r["previous"] == "1.1.1.1"
    assert r["ip"] == "2.2.2.2"
    assert r["changed"] is True
