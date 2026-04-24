"""Combined background loops in one process: snapshot logger, latency probe,
public IP watcher, MQTT publisher, webhook firing on device join/leave events,
plus optional watchdog, automation scheduler, external-latency map, rules engine.
"""
from __future__ import annotations

import logging
import threading
import time

from rich.console import Console

from . import config as cfg_mod
from . import db as db_mod
from . import latency as latency_mod
from . import mqtt as mqtt_mod
from . import publicip as publicip_mod
from . import webhook as wh_mod
from .client import router

log = logging.getLogger(__name__)
console = Console()


def _every(interval: int, fn, name: str, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            fn()
        except Exception as e:
            log.warning("%s failed: %s", name, e)
        stop.wait(interval)


def run(snap_every: int = 60, latency_every: int = 120,
        publicip_every: int = 600, mqtt_every: int | None = 60,
        extping_every: int | None = 300, automation: bool = True,
        watchdog: bool = False, watchdog_interval: int = 60,
        watchdog_auto_reboot: bool = False,
        anomaly_every: int | None = 3600,
        retention_every: int | None = 86400,
        dns_filter: bool = False, dns_port: int | None = None) -> None:
    cfg = cfg_mod.load_config()
    webhook_urls = cfg.get("webhooks", []) or []
    mqtt_cfg = cfg.get("mqtt") or {}
    have_mqtt = bool(mqtt_cfg.get("host"))

    if have_mqtt:
        try:
            mqtt_mod.publish_discovery(mqtt_cfg)
            console.print("[green]MQTT discovery published[/green]")
        except Exception as e:
            console.print(f"[yellow]MQTT discovery failed: {e}[/yellow]")

    last_macs: set[str] = set()
    last_public_ip: str | None = None

    def _fire_event(kind: str, **fields) -> None:
        """Emit to webhooks/DB, evaluate rules, mirror to Discord, route through notifier cooldown."""
        wh_mod.emit(webhook_urls, kind, **fields)
        try:
            from . import rules as rules_mod
            rules_mod.dispatch({"kind": kind, **fields}, cfg=cfg)
        except Exception as e:
            log.warning("rules dispatch failed: %s", e)
        try:
            from . import notifier
            key = fields.get("mac") or fields.get("current") or fields.get("target") or kind
            notifier.emit(kind, str(key), title=kind, body=str(fields))
        except Exception as e:
            log.warning("notifier failed: %s", e)

    def snap_tick():
        nonlocal last_macs
        from . import qos as _qos
        with router() as r:
            s = r.get_status()
            _qos.enrich_status(r, s)
        db_mod.record_snapshot(s)
        seen = {(str(d.macaddress) or "").upper() for d in s.devices if d.macaddress}
        for mac in seen - last_macs:
            dev = next((d for d in s.devices if (str(d.macaddress) or "").upper() == mac), None)
            _fire_event("device_joined",
                        mac=mac, hostname=getattr(dev, "hostname", None),
                        ip=str(getattr(dev, "ipaddress", "")))
            console.print(f"[red]+ JOIN[/red] {mac} {getattr(dev, 'hostname', '')}")
        for mac in last_macs - seen:
            _fire_event("device_left", mac=mac)
            console.print(f"[yellow]- LEAVE[/yellow] {mac}")
        last_macs = seen
        if have_mqtt and mqtt_every:
            try:
                mqtt_mod.publish_state(mqtt_cfg, s, public_ip=last_public_ip)
            except Exception as e:
                log.warning("mqtt publish failed: %s", e)

    def latency_tick():
        latency_mod.probe_and_record()

    def publicip_tick():
        nonlocal last_public_ip
        r = publicip_mod.check_and_record()
        if r.get("ip"):
            last_public_ip = r["ip"]
        if r.get("changed"):
            _fire_event("public_ip_changed", previous=r["previous"], current=r["ip"])
            console.print(f"[bold red]Public IP changed:[/bold red] {r['previous']} -> {r['ip']}")

    def extping_tick():
        from . import extping
        extping.probe()

    def anomaly_tick():
        from . import anomaly as anomaly_mod
        hits = anomaly_mod.scan()
        for h in hits:
            # Strip `kind` from the payload so it doesn't collide with the
            # positional arg to _fire_event.
            fields = {k: v for k, v in h.items() if k != "kind"}
            _fire_event(f"anomaly_{h['kind']}", **fields)

    stop = threading.Event()
    threads = [
        threading.Thread(target=_every, args=(snap_every, snap_tick, "snapshot", stop), daemon=True),
        threading.Thread(target=_every, args=(latency_every, latency_tick, "latency", stop), daemon=True),
        threading.Thread(target=_every, args=(publicip_every, publicip_tick, "publicip", stop), daemon=True),
    ]
    if extping_every:
        threads.append(threading.Thread(target=_every,
            args=(extping_every, extping_tick, "extping", stop), daemon=True))
    if anomaly_every:
        threads.append(threading.Thread(target=_every,
            args=(anomaly_every, anomaly_tick, "anomaly", stop), daemon=True))
    if retention_every:
        def retention_tick():
            from . import retention as ret
            ret.sweep()
        threads.append(threading.Thread(target=_every,
            args=(retention_every, retention_tick, "retention", stop), daemon=True))
    if automation:
        from . import automation as auto_mod
        threads.append(threading.Thread(target=auto_mod.run,
            args=(stop,), daemon=True, name="automation"))
    if watchdog:
        from . import watchdog as wd_mod
        threads.append(threading.Thread(target=wd_mod.run,
            args=(stop,), kwargs={"interval": watchdog_interval,
                                   "auto_reboot": watchdog_auto_reboot},
            daemon=True, name="watchdog"))
    if dns_filter:
        def dns_run():
            from . import dnsfilter
            try:
                dnsfilter.run(port=dns_port)
            except PermissionError:
                log.error("DNS filter needs root / elevated privileges to bind :53")
            except Exception as e:
                log.error("DNS filter crashed: %s", e)
        threads.append(threading.Thread(target=dns_run, daemon=True, name="dnsfilter"))

    for t in threads:
        t.start()
    console.print(
        f"[bold green]daemon running[/bold green] - snap={snap_every}s latency={latency_every}s "
        f"publicip={publicip_every}s extping={extping_every}s anomaly={anomaly_every}s "
        f"retention={retention_every}s automation={automation} watchdog={watchdog} "
        f"dns_filter={dns_filter}. Ctrl-C to stop."
    )
    try:
        while not stop.is_set():
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        console.print("[yellow]stopping...[/yellow]")
