"""Config + keyring-backed password storage."""
from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

import keyring
from rich.console import Console

KEYRING_SERVICE = "c6u-router"
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"
DB_PATH = ROOT / "c6u.sqlite3"
KNOWN_MACS_PATH = ROOT / "known_macs.txt"
PROFILES_DIR = ROOT / "profiles"

# Set by CLI before any config load if the user passed --profile NAME
ACTIVE_PROFILE: str | None = None

console = Console()


def _profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{name}.json"


def set_active_profile(name: str | None) -> None:
    global ACTIVE_PROFILE
    ACTIVE_PROFILE = name


def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    return sorted(p.stem for p in PROFILES_DIR.glob("*.json"))


def _active_path() -> Path:
    if ACTIVE_PROFILE:
        return _profile_path(ACTIVE_PROFILE)
    return CONFIG_PATH


def _read_json() -> dict | None:
    p = _active_path()
    if not p.exists():
        return None
    with p.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(cfg: dict) -> None:
    p = _active_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _keyring_user(cfg: dict) -> str:
    """Namespace keyring entries per profile so multi-router doesn't collide."""
    user = cfg.get("username", "admin")
    return f"{ACTIVE_PROFILE}:{user}" if ACTIVE_PROFILE else user


def load_config(interactive: bool = True) -> dict:
    """Load config.json, resolve password via keyring when available."""
    cfg = _read_json()
    if cfg is None:
        if not interactive:
            console.print(f"[red]Missing {CONFIG_PATH.name}[/red]. Run `python main.py setup`.")
            sys.exit(2)
        cfg = _first_run_wizard()

    if not cfg.get("password"):
        kuser = _keyring_user(cfg)
        pw = keyring.get_password(KEYRING_SERVICE, kuser)
        if not pw:
            if not interactive:
                console.print("[red]No password in keyring[/red]. Run `python main.py setup`.")
                sys.exit(2)
            pw = getpass.getpass(f"Password for {kuser}: ")
            keyring.set_password(KEYRING_SERVICE, kuser, pw)
        cfg["password"] = pw
    return cfg


def _first_run_wizard() -> dict:
    console.print("[yellow]First run — let's configure the router.[/yellow]")
    host = console.input("Router URL [http://192.168.0.1]: ").strip() or "http://192.168.0.1"
    username = console.input("Username [admin]: ").strip() or "admin"
    use_keyring = console.input("Store password in OS keyring? [Y/n]: ").strip().lower() != "n"
    password = getpass.getpass("Password: ")

    cfg = {
        "host": host,
        "username": username,
        "verify_ssl": False,
        "timeout": 30,
    }
    if use_keyring:
        keyring.set_password(KEYRING_SERVICE, _keyring_user(cfg), password)
    else:
        cfg["password"] = password
    _write_json(cfg)
    console.print(f"[green]Saved {_active_path().name}[/green]")
    return cfg


def run_setup() -> None:
    """Re-run the first-run wizard (overwriting config.json)."""
    _first_run_wizard()


def clear_stored_password() -> None:
    cfg = _read_json() or {}
    kuser = _keyring_user(cfg)
    try:
        keyring.delete_password(KEYRING_SERVICE, kuser)
        console.print(f"[green]Removed keyring password for {kuser}[/green]")
    except keyring.errors.PasswordDeleteError:
        console.print("[yellow]No keyring password stored[/yellow]")
    if "password" in cfg:
        cfg.pop("password")
        _write_json(cfg)
        console.print("[green]Cleared password from config[/green]")
