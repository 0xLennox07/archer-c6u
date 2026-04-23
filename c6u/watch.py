"""Watch mode — live refresh + desktop notifications on new devices."""
from __future__ import annotations

import time
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.table import Table

from .client import router
from .config import KNOWN_MACS_PATH
from .db import record_snapshot
from .render import clients_table, status_table


def _load_known(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip().upper() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def _append_known(path: Path, mac: str) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(mac.upper() + "\n")


def _notify(title: str, msg: str) -> None:
    try:
        from plyer import notification
        notification.notify(title=title, message=msg, app_name="c6u", timeout=8)
    except Exception:
        pass


def watch_loop(interval: int = 10, log_to_db: bool = False, alert: bool = True) -> None:
    console = Console()
    known = _load_known(KNOWN_MACS_PATH)
    first = not known

    def render(status):
        grid = Table.grid(expand=True)
        grid.add_column()
        grid.add_row(status_table(status))
        grid.add_row(clients_table(status))
        return grid

    with router() as r, Live(console=console, refresh_per_second=2, screen=False) as live:
        while True:
            try:
                status = r.get_status()
                live.update(render(status))

                seen = {str(d.macaddress).upper() for d in status.devices if d.macaddress}
                if first:
                    for m in seen:
                        _append_known(KNOWN_MACS_PATH, m)
                    known |= seen
                    first = False
                else:
                    new = seen - known
                    for m in new:
                        dev = next((d for d in status.devices if str(d.macaddress).upper() == m), None)
                        label = (dev.hostname if dev and dev.hostname else m)
                        console.print(f"[bold red]NEW DEVICE:[/bold red] {label} ({m})")
                        if alert:
                            _notify("c6u: new device", f"{label} joined")
                        _append_known(KNOWN_MACS_PATH, m)
                        known.add(m)

                if log_to_db:
                    record_snapshot(status)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                console.print(f"[yellow]poll failed:[/yellow] {e}")
            time.sleep(interval)
