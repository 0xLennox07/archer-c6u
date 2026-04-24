"""Prometheus exporter. `python main.py metrics --port 9100`"""
from __future__ import annotations

import logging
import time

from prometheus_client import Counter, Gauge, start_http_server

from .client import router

log = logging.getLogger(__name__)

g_cpu = Gauge("c6u_cpu_usage", "Router CPU usage ratio")
g_mem = Gauge("c6u_mem_usage", "Router memory usage ratio")
g_clients = Gauge("c6u_clients_total", "Total connected clients")
g_wired = Gauge("c6u_clients_wired", "Wired clients")
g_wifi = Gauge("c6u_clients_wifi", "WiFi clients")
g_guest = Gauge("c6u_clients_guest", "Guest clients")
g_uptime = Gauge("c6u_wan_uptime_seconds", "WAN uptime in seconds")
g_wifi_band = Gauge("c6u_wifi_enabled", "WiFi radio enabled (1/0)", ["band"])
g_dev_down = Gauge("c6u_device_down_bps", "Per-device download bps", ["mac", "hostname"])
g_dev_up = Gauge("c6u_device_up_bps", "Per-device upload bps", ["mac", "hostname"])
g_dev_usage = Gauge("c6u_device_traffic_bytes", "Per-device traffic usage", ["mac", "hostname"])
c_scrape_errors = Counter("c6u_scrape_errors_total", "Scrape errors")


def _scrape() -> None:
    from . import qos as _qos
    with router() as r:
        s = r.get_status()
        _qos.enrich_status(r, s)
        if s.cpu_usage is not None:
            g_cpu.set(s.cpu_usage)
        if s.mem_usage is not None:
            g_mem.set(s.mem_usage)
        g_clients.set(s.clients_total)
        g_wired.set(s.wired_total)
        g_wifi.set(s.wifi_clients_total)
        g_guest.set(s.guest_clients_total)
        if s.wan_ipv4_uptime is not None:
            g_uptime.set(s.wan_ipv4_uptime)
        for band, attr in (("2g", "wifi_2g_enable"), ("5g", "wifi_5g_enable"), ("6g", "wifi_6g_enable")):
            v = getattr(s, attr, None)
            if v is not None:
                g_wifi_band.labels(band=band).set(1 if v else 0)
        # per-device rates (reset-then-set so gone devices drop off)
        g_dev_down._metrics.clear()
        g_dev_up._metrics.clear()
        g_dev_usage._metrics.clear()
        for d in s.devices:
            mac = str(d.macaddress) if d.macaddress else "?"
            host = d.hostname or "?"
            g_dev_down.labels(mac=mac, hostname=host).set(d.down_speed or 0)
            g_dev_up.labels(mac=mac, hostname=host).set(d.up_speed or 0)
            g_dev_usage.labels(mac=mac, hostname=host).set(d.traffic_usage or 0)


def serve(port: int = 9100, interval: int = 30) -> None:
    from rich.console import Console
    console = Console()
    start_http_server(port)
    console.print(f"[bold green]Prometheus metrics server listening on :[/bold green][bold]{port}[/bold]")
    console.print(f"[mute]scrape:[/mute] http://127.0.0.1:{port}/metrics   [mute](scraping every {interval}s)[/mute]")
    console.print("[mute]Ctrl-C to stop.[/mute]")
    scrape_count = 0
    while True:
        try:
            _scrape()
            scrape_count += 1
            if scrape_count % 10 == 1:  # tick every 10 scrapes so user knows it's alive
                console.print(f"[mute]scrape #{scrape_count} ok[/mute]")
        except Exception as e:
            console.print(f"[yellow]scrape error:[/yellow] {e}")
            c_scrape_errors.inc()
        time.sleep(interval)
