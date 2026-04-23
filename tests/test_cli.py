"""CLI help runs without importing any network code."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_top_level_help():
    r = subprocess.run([sys.executable, "main.py", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0
    for sub in ("login", "status", "wifi-toggle", "dhcp", "wol", "qr", "report", "metrics", "web", "watch",
                "speedtest", "tray", "alias", "vendor", "rdns", "public-ip", "firmware-check",
                "latency", "ping", "discover", "presence", "csv", "events", "daemon", "mqtt",
                "schedule", "profiles"):
        assert sub in r.stdout


def test_subcommand_help():
    r = subprocess.run([sys.executable, "main.py", "report", "--help"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0
    assert "--days" in r.stdout and "--top" in r.stdout
