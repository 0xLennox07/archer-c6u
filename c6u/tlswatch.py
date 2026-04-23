"""Monitor the router admin UI's TLS certificate for changes.

Unlike most watchers we compare by SPKI pin (sha256 of the subject public key
info) — that's stable across cert re-issuance as long as the private key stays
the same. If the pin flips, something replaced the cert.
"""
from __future__ import annotations

import hashlib
import json
import socket
import ssl
from pathlib import Path
from urllib.parse import urlparse

from cryptography import x509  # only for SPKI extraction; cryptography ships with keyring

from . import config as cfg_mod
from . import db as db_mod

PIN_PATH = cfg_mod.ROOT / "tls_pins.json"


def _host_port(url: str) -> tuple[str, int]:
    u = urlparse(url)
    host = u.hostname or ""
    port = u.port or (443 if u.scheme == "https" else 80)
    return host, port


def _fetch_cert_der(host: str, port: int, timeout: float = 4.0) -> bytes:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((host, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls:
            return tls.getpeercert(binary_form=True)


def _spki_pin(der: bytes) -> str:
    cert = x509.load_der_x509_certificate(der)
    spki = cert.public_key().public_bytes(
        encoding=__import__("cryptography.hazmat.primitives.serialization",
                            fromlist=["Encoding"]).Encoding.DER,
        format=__import__("cryptography.hazmat.primitives.serialization",
                           fromlist=["PublicFormat"]).PublicFormat.SubjectPublicKeyInfo,
    )
    return "sha256/" + hashlib.sha256(spki).hexdigest()


def _load_pins() -> dict:
    if PIN_PATH.exists():
        try:
            return json.loads(PIN_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_pins(pins: dict) -> None:
    PIN_PATH.write_text(json.dumps(pins, indent=2))


def check(url: str | None = None) -> dict:
    cfg = cfg_mod.load_config(interactive=False)
    url = url or cfg.get("host") or "https://192.168.0.1"
    # If the admin UI is plain HTTP, there's no cert to watch.
    if urlparse(url).scheme != "https":
        return {"url": url, "watched": False, "reason": "not https"}
    host, port = _host_port(url)
    der = _fetch_cert_der(host, port)
    pin = _spki_pin(der)
    cert = x509.load_der_x509_certificate(der)
    info = {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "not_before": str(cert.not_valid_before_utc),
        "not_after": str(cert.not_valid_after_utc),
        "pin": pin,
    }
    pins = _load_pins()
    previous = pins.get(url)
    changed = previous is not None and previous != pin
    if changed:
        db_mod.record_event("tls_pin_changed",
                            payload=f"{url}: {previous} -> {pin}")
    pins[url] = pin
    _save_pins(pins)
    return {"url": url, "info": info, "previous_pin": previous, "changed": bool(changed)}
