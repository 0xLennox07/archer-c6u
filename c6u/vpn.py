"""WireGuard config generator + Tailscale status reporter.

WireGuard path: generate a keypair for the local machine + one or more peers,
emit a server config and per-peer client configs (with QR for phones).

Tailscale path: if `tailscale` CLI is on PATH, wrap `tailscale status --json`
so the dashboard can show peer state alongside the rest of the network.

Neither path changes system state automatically — you still install the WG
service or `tailscale up` yourself. This is a helper, not an installer.
"""
from __future__ import annotations

import base64
import ipaddress
import json
import os
import shutil
import subprocess
from pathlib import Path

from . import config as cfg_mod


# ---------- WireGuard ----------

def _have(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _wg(cmd: list[str]) -> str:
    if not _have("wg"):
        raise RuntimeError("wg CLI not on PATH — install wireguard-tools")
    out = subprocess.run(cmd, capture_output=True, text=True, check=True,
        creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    ).stdout
    return out.strip()


def _gen_keypair_pycrypto() -> tuple[str, str]:
    """Curve25519 keypair using the standard library (no wg CLI required)."""
    # Python 3.11+ has `cryptography` available — we require it for tlswatch already.
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding, NoEncryption, PrivateFormat, PublicFormat,
    )
    sk = X25519PrivateKey.generate()
    priv = sk.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    pub = sk.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return base64.b64encode(priv).decode(), base64.b64encode(pub).decode()


def gen_keypair() -> tuple[str, str]:
    """Returns (private_b64, public_b64). Uses `wg` CLI if present, else pure Python."""
    if _have("wg"):
        priv = _wg(["wg", "genkey"])
        pub = subprocess.run(["wg", "pubkey"], input=priv, capture_output=True, text=True,
            check=True,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        ).stdout.strip()
        return priv, pub
    return _gen_keypair_pycrypto()


def _preshared() -> str:
    if _have("wg"):
        return _wg(["wg", "genpsk"])
    return base64.b64encode(os.urandom(32)).decode()


def server_config(server_private: str, listen_port: int, network: str,
                  peers: list[dict]) -> str:
    """Emit a wg-quick [Interface]+[Peer]... config."""
    server_ip = str(next(ipaddress.ip_network(network).hosts()))
    lines = [
        "[Interface]",
        f"PrivateKey = {server_private}",
        f"Address = {server_ip}/{ipaddress.ip_network(network).prefixlen}",
        f"ListenPort = {listen_port}",
        "SaveConfig = false",
        "",
    ]
    for p in peers:
        lines += [
            f"# peer: {p['name']}",
            "[Peer]",
            f"PublicKey = {p['public']}",
            f"PresharedKey = {p['psk']}",
            f"AllowedIPs = {p['address']}/32",
            "",
        ]
    return "\n".join(lines)


def client_config(client_private: str, client_ip: str, network: str,
                  server_public: str, server_endpoint: str, psk: str,
                  dns: str | None = None) -> str:
    prefix = ipaddress.ip_network(network).prefixlen
    lines = [
        "[Interface]",
        f"PrivateKey = {client_private}",
        f"Address = {client_ip}/{prefix}",
    ]
    if dns:
        lines.append(f"DNS = {dns}")
    lines += [
        "",
        "[Peer]",
        f"PublicKey = {server_public}",
        f"PresharedKey = {psk}",
        f"Endpoint = {server_endpoint}",
        "AllowedIPs = 0.0.0.0/0, ::/0",
        "PersistentKeepalive = 25",
        "",
    ]
    return "\n".join(lines)


def provision(out_dir: str | Path | None = None, peer_names: list[str] | None = None,
              network: str = "10.77.77.0/24", listen_port: int = 51820,
              endpoint: str | None = None, dns: str | None = None) -> dict:
    """Generate a fresh server keypair + N peer configs. Writes files to out_dir.

    Does NOT install or start wg — you still do that by copying the server
    config to /etc/wireguard/wg0.conf and running `wg-quick up wg0`. Phones
    scan the per-peer QR.
    """
    out = Path(out_dir) if out_dir else cfg_mod.ROOT / "wireguard"
    out.mkdir(parents=True, exist_ok=True)
    peer_names = peer_names or ["phone", "laptop"]

    server_priv, server_pub = gen_keypair()
    net = ipaddress.ip_network(network)
    hosts = list(net.hosts())[1:]  # skip .1 reserved for server

    peers: list[dict] = []
    for i, name in enumerate(peer_names):
        if i >= len(hosts):
            break
        priv, pub = gen_keypair()
        psk = _preshared()
        addr = str(hosts[i])
        peers.append({"name": name, "private": priv, "public": pub,
                       "psk": psk, "address": addr})

    ep = endpoint or f"YOUR_PUBLIC_IP:{listen_port}"
    server_cfg = server_config(server_priv, listen_port, network, peers)
    (out / "wg0.conf").write_text(server_cfg, encoding="utf-8")
    client_files: list[dict] = []
    for p in peers:
        client_cfg = client_config(p["private"], p["address"], network,
                                    server_pub, ep, p["psk"], dns=dns)
        fname = out / f"{p['name']}.conf"
        fname.write_text(client_cfg, encoding="utf-8")
        qr_png = None
        try:
            import qrcode
            img = qrcode.make(client_cfg)
            qr_png = out / f"{p['name']}.png"
            img.save(qr_png)
        except Exception:
            pass
        client_files.append({
            "name": p["name"], "address": p["address"],
            "config": str(fname), "qr": str(qr_png) if qr_png else None,
        })
    return {
        "out_dir": str(out),
        "server_config": str(out / "wg0.conf"),
        "server_public": server_pub,
        "network": network,
        "listen_port": listen_port,
        "peers": client_files,
    }


# ---------- Tailscale ----------

def tailscale_status() -> dict | None:
    if not _have("tailscale"):
        return None
    try:
        out = subprocess.run(["tailscale", "status", "--json"],
            capture_output=True, text=True, check=True, timeout=5,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        ).stdout
        return json.loads(out)
    except Exception:
        return None
