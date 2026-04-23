"""WiFi QR payload + file output."""
from c6u import qr


def test_wifi_payload_escapes_specials():
    p = qr.wifi_payload("My;SSID", "pa:ss,word", "WPA")
    assert "My\\;SSID" in p
    assert "pa\\:ss\\,word" in p
    assert p.startswith("WIFI:T:WPA;")


def test_save_writes_png(tmp_path):
    out = tmp_path / "wifi.png"
    qr.save_wifi_qr("MyNet", "secret", str(out))
    assert out.exists() and out.stat().st_size > 100
