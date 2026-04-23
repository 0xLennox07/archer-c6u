"""ACME / Let's Encrypt — shells out to certbot to fetch a cert, then tells
the web.serve() helper to use it.

Doing full ACME in-process is a lot of code; certbot is already packaged on
every distro and Windows. We just drive it.

Config (config.json → acme):
    "acme": {
      "domain": "home.example.com",
      "email": "you@example.com",
      "method": "standalone",   // or "webroot"
      "webroot": "./acme-webroot",
      "cert_dir": "./certs"     // where to COPY the issued cert so web can read it
    }

Usage:
    c6u acme issue    → runs certbot, returns cert/key paths
    c6u web --ssl     → web.serve() picks up the issued cert automatically
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from . import config as cfg_mod

log = logging.getLogger(__name__)


def _certbot_available() -> bool:
    return shutil.which("certbot") is not None


def _acme_cfg() -> dict:
    cfg = cfg_mod.load_config(interactive=False)
    return cfg.get("acme") or {}


def _cert_dir() -> Path:
    p = Path(_acme_cfg().get("cert_dir", cfg_mod.ROOT / "certs"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def issue(domain: str | None = None, email: str | None = None,
          method: str | None = None, webroot: str | None = None,
          staging: bool = False) -> dict:
    if not _certbot_available():
        return {"ok": False, "error": "certbot not on PATH — install it first"}
    acme = _acme_cfg()
    domain = domain or acme.get("domain")
    email = email or acme.get("email")
    method = (method or acme.get("method") or "standalone").lower()
    webroot = webroot or acme.get("webroot") or str(cfg_mod.ROOT / "acme-webroot")
    if not (domain and email):
        return {"ok": False, "error": "domain and email required (config.acme or flags)"}

    cmd = ["certbot", "certonly", "--non-interactive", "--agree-tos",
           "-m", email, "-d", domain]
    if method == "webroot":
        Path(webroot).mkdir(parents=True, exist_ok=True)
        cmd += ["--webroot", "-w", webroot]
    else:
        cmd += ["--standalone"]
    if staging:
        cmd += ["--staging"]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except Exception as e:
        return {"ok": False, "error": f"certbot failed: {e}"}
    if proc.returncode != 0:
        return {"ok": False, "error": proc.stderr.strip() or proc.stdout.strip()}

    # Certbot default layout: /etc/letsencrypt/live/<domain>/{fullchain,privkey}.pem
    src = Path(f"/etc/letsencrypt/live/{domain}")
    cert = src / "fullchain.pem"
    key = src / "privkey.pem"
    if not (cert.exists() and key.exists()):
        return {"ok": True, "log": proc.stdout.strip(), "warn": "cert issued but expected files not found"}

    dst = _cert_dir()
    dst_cert = dst / "fullchain.pem"
    dst_key = dst / "privkey.pem"
    shutil.copyfile(cert, dst_cert)
    shutil.copyfile(key, dst_key)
    return {"ok": True, "cert": str(dst_cert), "key": str(dst_key), "domain": domain}


def active_cert() -> dict | None:
    d = _cert_dir()
    cert = d / "fullchain.pem"
    key = d / "privkey.pem"
    if cert.exists() and key.exists():
        return {"cert": str(cert), "key": str(key)}
    return None


def renew() -> dict:
    if not _certbot_available():
        return {"ok": False, "error": "certbot not on PATH"}
    proc = subprocess.run(["certbot", "renew", "--non-interactive"],
                          capture_output=True, text=True, timeout=180)
    return {"ok": proc.returncode == 0, "log": proc.stdout.strip(),
            "err": proc.stderr.strip() or None}
