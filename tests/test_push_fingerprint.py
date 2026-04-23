"""Push-notify fanout + fingerprint heuristics."""
from unittest.mock import patch

from c6u import pushnotify, fingerprint


def test_push_fanout_all_providers():
    cfg = {
        "ntfy": {"topic": "t"},
        "pushover": {"token": "x", "user": "y"},
        "gotify": {"url": "http://g", "token": "x"},
    }
    with patch("c6u.pushnotify.requests.post") as m:
        fired = pushnotify.push(cfg, "t", "b")
    assert set(fired) == {"ntfy", "pushover", "gotify"}
    assert m.call_count == 3


def test_push_skips_missing_config():
    with patch("c6u.pushnotify.requests.post") as m:
        fired = pushnotify.push({"pushover": {"token": "x"}}, "t", "b")  # no user key
    assert fired == []
    assert m.call_count == 0


def test_fingerprint_hostname():
    r = fingerprint.fingerprint(mac="00:03:93:AA:BB:CC", hostname="iPhone-of-Bob")
    assert any("Apple iOS" in g or "Apple" in g for g in r["guesses"])


def test_fingerprint_raspberry():
    r = fingerprint.fingerprint(mac="B8:27:EB:00:11:22", hostname="raspberrypi")
    # Vendor lookup may or may not be populated; the hostname branch should hit.
    assert any("Raspberry Pi" in g for g in r["guesses"])
