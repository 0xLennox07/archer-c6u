"""Rolling packet-capture wrapper.

Relies on tshark/dumpcap being installed — we shell out instead of pulling
in a Python packet library with native deps. If tshark isn't on PATH, every
function gracefully reports "not available" rather than crashing.
"""
from __future__ import annotations

import datetime as dt
import shutil
import signal
import subprocess
from pathlib import Path

from . import config as cfg_mod


def tshark_available() -> bool:
    return shutil.which("tshark") is not None or shutil.which("dumpcap") is not None


def list_interfaces() -> list[dict]:
    if not tshark_available():
        return []
    try:
        out = subprocess.run(
            ["tshark", "-D"], capture_output=True, text=True, timeout=8,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        ).stdout
    except Exception:
        return []
    entries: list[dict] = []
    for line in out.splitlines():
        # Example: "1. \Device\NPF_{GUID} (Ethernet)"
        if "." in line and " " in line:
            idx, rest = line.split(".", 1)
            entries.append({"index": idx.strip(), "name": rest.strip()})
    return entries


def rolling_capture(interface: str, out_dir: str | Path | None = None,
                    file_duration_s: int = 300, files_to_keep: int = 12,
                    filter_bpf: str = "") -> subprocess.Popen:
    """Spawn a background tshark rolling capture.

    Returns the Popen — caller should `.terminate()` to stop. Files land in
    out_dir (default: `pcaps/` in the repo root) as `c6u-YYYYMMDD-HHMMSS.pcapng`.
    """
    if not tshark_available():
        raise RuntimeError("tshark/dumpcap not on PATH — install Wireshark first")
    root = Path(out_dir) if out_dir else cfg_mod.ROOT / "pcaps"
    root.mkdir(parents=True, exist_ok=True)
    base = root / f"c6u-{dt.datetime.now():%Y%m%d-%H%M%S}.pcapng"
    cmd = [
        "tshark", "-i", interface,
        "-b", f"duration:{file_duration_s}",
        "-b", f"files:{files_to_keep}",
        "-w", str(base),
    ]
    if filter_bpf:
        cmd += ["-f", filter_bpf]
    return subprocess.Popen(cmd,
        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )


def burst_capture(interface: str, seconds: int = 30,
                  out: str | Path | None = None, filter_bpf: str = "") -> Path | None:
    """Capture for N seconds, write one file, return the path."""
    if not tshark_available():
        raise RuntimeError("tshark/dumpcap not on PATH")
    root = cfg_mod.ROOT / "pcaps"
    root.mkdir(parents=True, exist_ok=True)
    path = Path(out) if out else root / f"burst-{dt.datetime.now():%Y%m%d-%H%M%S}.pcapng"
    cmd = ["tshark", "-i", interface, "-a", f"duration:{seconds}", "-w", str(path)]
    if filter_bpf:
        cmd += ["-f", filter_bpf]
    try:
        subprocess.run(cmd, check=True, timeout=seconds + 10,
            creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
    except Exception:
        return None
    return path if path.exists() else None


def stop(proc: subprocess.Popen) -> None:
    try:
        if hasattr(signal, "CTRL_BREAK_EVENT"):
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
    except Exception:
        proc.kill()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()
