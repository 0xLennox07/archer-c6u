"""Backup / restore: bundle config + aliases + DB + profiles + rules into a tar.gz."""
from __future__ import annotations

import datetime as dt
import os
import tarfile
from pathlib import Path

from . import config as cfg_mod


BACKUP_ITEMS = (
    "config.json",
    "aliases.json",
    "known_macs.txt",
    "c6u.sqlite3",
    "rules.json",
    "rules.yaml",
    "rules.yml",
    "automation.json",
    "tls_pins.json",
    "profiles",
)


def create(out: str | Path | None = None) -> Path:
    out = Path(out) if out else (
        cfg_mod.ROOT / f"c6u-backup-{dt.datetime.now():%Y%m%d-%H%M%S}.tar.gz"
    )
    root = cfg_mod.ROOT
    with tarfile.open(out, "w:gz") as tar:
        for name in BACKUP_ITEMS:
            p = root / name
            if p.exists():
                tar.add(p, arcname=name)
    return out


def restore(archive: str | Path, overwrite: bool = False) -> list[str]:
    """Extract into repo root. Returns filenames restored."""
    root = cfg_mod.ROOT
    restored: list[str] = []
    with tarfile.open(archive, "r:*") as tar:
        members = tar.getmembers()
        for m in members:
            # Prevent path traversal.
            dest = (root / m.name).resolve()
            if not str(dest).startswith(str(root.resolve())):
                continue
            if dest.exists() and not overwrite:
                continue
            tar.extract(m, path=root)
            restored.append(m.name)
    return restored


def list_contents(archive: str | Path) -> list[dict]:
    with tarfile.open(archive, "r:*") as tar:
        return [{"name": m.name, "size": m.size,
                 "mtime": int(m.mtime)} for m in tar.getmembers()]
