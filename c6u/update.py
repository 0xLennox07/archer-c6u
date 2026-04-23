"""Self-update: git pull + pip install."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from . import config as cfg_mod


def _run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    cwd = cwd or cfg_mod.ROOT
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
        creationflags=0x08000000 if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
    )
    return p.returncode, p.stdout, p.stderr


def current_version() -> dict:
    rc, out, _ = _run(["git", "log", "-1", "--pretty=format:%H|%s|%ci"])
    if rc != 0:
        return {"commit": None, "subject": None, "committed": None}
    parts = (out or "").split("|", 2)
    while len(parts) < 3:
        parts.append("")
    return {"commit": parts[0], "subject": parts[1], "committed": parts[2]}


def update(pull: bool = True, deps: bool = True, quiet: bool = False) -> dict:
    log: list[str] = []
    if not (cfg_mod.ROOT / ".git").exists():
        return {"ok": False, "error": "not a git checkout — can't self-update"}
    before = current_version()
    if pull:
        rc, out, err = _run(["git", "pull", "--ff-only"])
        log.append(f"git pull (rc={rc}): {out.strip()} {err.strip()}")
        if rc != 0:
            return {"ok": False, "log": log, "before": before,
                    "error": "git pull failed — aborting"}
    after = current_version()
    if deps and before.get("commit") != after.get("commit"):
        rc, out, err = _run([sys.executable, "-m", "pip", "install",
                             "-r", "requirements.txt"])
        log.append(f"pip install (rc={rc})")
        if not quiet and rc != 0:
            log.append(err.strip())
    return {
        "ok": True, "before": before, "after": after,
        "changed": before.get("commit") != after.get("commit"),
        "log": log,
    }
