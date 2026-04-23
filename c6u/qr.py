"""WiFi QR code generator (scan with phone to join)."""
from __future__ import annotations

import qrcode


def _escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace('"', '\\"').replace(":", "\\:")


def wifi_payload(ssid: str, password: str, security: str = "WPA", hidden: bool = False) -> str:
    return f"WIFI:T:{security};S:{_escape(ssid)};P:{_escape(password)};H:{'true' if hidden else 'false'};;"


def print_wifi_qr(ssid: str, password: str, security: str = "WPA", hidden: bool = False) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(wifi_payload(ssid, password, security, hidden))
    qr.make(fit=True)
    qr.print_ascii(invert=True)


def save_wifi_qr(ssid: str, password: str, path: str, security: str = "WPA") -> None:
    img = qrcode.make(wifi_payload(ssid, password, security))
    img.save(path)
