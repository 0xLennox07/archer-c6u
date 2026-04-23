"""WiFi QR payload sanity (no network)."""
from c6u import qr


def test_payload_basic():
    p = qr.wifi_payload("net", "pw", "WPA")
    assert p == "WIFI:T:WPA;S:net;P:pw;H:false;;"


def test_payload_hidden():
    assert "H:true" in qr.wifi_payload("a", "b", hidden=True)
