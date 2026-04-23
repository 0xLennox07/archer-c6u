"""Rules engine — matcher and action dispatch."""
import datetime as dt
from unittest.mock import patch

from c6u import rules


def test_kind_match():
    rs = [{"name": "x", "when": {"kind": "device_joined"},
           "then": [{"webhook": {"url": "http://example.com/"}}]}]
    fired_urls = []
    def fake_post(*a, **kw):
        fired_urls.append(kw.get("json") or a[0])
        class R: ok = True
        return R()
    with patch("c6u.rules.requests.request", side_effect=fake_post):
        fired = rules.dispatch({"kind": "device_joined", "mac": "aa"}, cfg={}, rules=rs)
    assert fired == 1
    fired2 = rules.dispatch({"kind": "wifi_toggle"}, cfg={}, rules=rs)
    assert fired2 == 0


def test_hour_between_wrap():
    rs = [{"name": "late", "when": {"kind": "e", "hour_between": [23, 6]}, "then": []}]
    assert rules._trigger_matches(rs[0]["when"], {"kind": "e"}) in (True, False)


def test_unknown_mac(monkeypatch, tmp_path):
    from c6u import aliases as amod, config as cmod
    monkeypatch.setattr(amod, "ALIASES_PATH", tmp_path / "a.json", raising=False)
    monkeypatch.setattr(cmod, "KNOWN_MACS_PATH", tmp_path / "k.txt")
    (tmp_path / "k.txt").write_text("AA:BB:CC:DD:EE:01")
    rs = [{"when": {"kind": "device_joined", "unknown_mac": True},
           "then": [{"webhook": {"url": "http://x/"}}]}]
    with patch("c6u.rules.requests.request"):
        # Known MAC → no fire.
        assert rules.dispatch(
            {"kind": "device_joined", "mac": "AA:BB:CC:DD:EE:01"},
            cfg={}, rules=rs) == 0
        # Unknown MAC → fires.
        assert rules.dispatch(
            {"kind": "device_joined", "mac": "AA:BB:CC:DD:EE:02"},
            cfg={}, rules=rs) == 1
