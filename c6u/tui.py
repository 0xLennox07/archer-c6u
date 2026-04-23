"""Full-screen Textual TUI dashboard.

Panels: router status, connected devices, live event log, latency sparkline.
Keys: r=refresh, l=run latency probe, e=events, q=quit.
"""
from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

from . import aliases as aliases_mod
from . import db as db_mod
from . import latency as latency_mod
from . import vendor as vendor_mod
from .client import router


def run() -> None:
    try:
        from textual.app import App, ComposeResult
        from textual.containers import Horizontal, Vertical
        from textual.widgets import DataTable, Footer, Header, Log, Static
    except ImportError:
        print("Textual not installed. Run: pip install textual>=0.60.0")
        return

    class C6UTUI(App):
        CSS = """
        Screen { layout: vertical; }
        #top { height: 10; }
        #status { width: 1fr; border: round $accent; padding: 1; }
        #wan    { width: 1fr; border: round $primary; padding: 1; }
        #main   { height: 1fr; }
        #clients { width: 2fr; border: round $accent; }
        #events  { width: 1fr; border: round $primary; }
        DataTable { height: 1fr; }
        """
        BINDINGS = [
            ("q", "quit", "Quit"),
            ("r", "refresh", "Refresh"),
            ("l", "latency", "Latency"),
        ]

        def compose(self) -> ComposeResult:
            yield Header(show_clock=True)
            with Horizontal(id="top"):
                yield Static("status…", id="status")
                yield Static("wan…", id="wan")
            with Horizontal(id="main"):
                t = DataTable(id="clients"); t.zebra_stripes = True
                yield t
                yield Log(id="events", max_lines=200)
            yield Footer()

        def on_mount(self) -> None:
            table = self.query_one("#clients", DataTable)
            table.add_columns("Name", "Hostname", "IP", "MAC", "Vendor", "Type")
            self.set_interval(5.0, self.action_refresh)
            self.action_refresh()

        async def _fetch(self) -> dict[str, Any]:
            loop = asyncio.get_event_loop()
            def go():
                with router() as r:
                    s = r.get_status()
                return s
            s = await loop.run_in_executor(None, go)
            return {"status": s}

        async def action_refresh(self) -> None:
            try:
                data = await self._fetch()
            except Exception as e:
                self.query_one("#events", Log).write(f"[error] {e}\n")
                return
            s = data["status"]
            self.query_one("#status", Static).update(
                f"CPU   {s.cpu_usage*100:5.1f}%\n"
                f"MEM   {s.mem_usage*100:5.1f}%\n"
                f"CLIEN {s.clients_total} (wired {s.wired_total}, wifi {s.wifi_clients_total}, guest {s.guest_clients_total})\n"
                f"2.4/5/6: {getattr(s,'wifi_2g_enable',None)}/{getattr(s,'wifi_5g_enable',None)}/{getattr(s,'wifi_6g_enable',None)}"
            )
            self.query_one("#wan", Static).update(
                f"WAN IP   {s.wan_ipv4_address}\n"
                f"uptime   {s.wan_ipv4_uptime}s"
            )
            table = self.query_one("#clients", DataTable)
            table.clear()
            aliases = aliases_mod.load()
            for d in sorted(s.devices, key=lambda x: x.hostname or ""):
                mac = (str(d.macaddress) or "").upper()
                name = aliases.get(mac, "-")
                table.add_row(
                    name, d.hostname or "-", str(d.ipaddress or "-"),
                    mac, vendor_mod.vendor(mac) or "-",
                    d.type.name if hasattr(d.type, "name") else str(d.type),
                )
            for r in db_mod.recent_events(limit=10)[::-1]:
                when = dt.datetime.fromtimestamp(r["ts"]).strftime("%H:%M:%S")
                self.query_one("#events", Log).write(
                    f"{when}  {r['kind']:<20} {r.get('mac') or ''}\n"
                )

        async def action_latency(self) -> None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, latency_mod.probe_and_record)
            self.query_one("#events", Log).write("[info] latency probe done\n")

    C6UTUI().run()
