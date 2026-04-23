"""CLI command implementations. Each takes argparse.Namespace."""
from __future__ import annotations

import json as _json

from rich.console import Console
from tplinkrouterc6u import Connection

from . import aliases as aliases_mod
from . import config as cfg
from . import csv_export as csv_mod
from . import db as db_mod
from . import discover as discover_mod
from . import firmware_check as fwchk
from . import latency as latency_mod
from . import mqtt as mqtt_mod
from . import presence as presence_mod
from . import publicip as publicip_mod
from . import qr as qr_mod
from . import rdns as rdns_mod
from . import scheduler as sched_mod
from . import vendor as vendor_mod
from . import wol as wol_mod
from .client import router
from .render import (
    clients_table,
    dhcp_leases_table,
    enrich_devices_json,
    firmware_panel,
    reservations_table,
    status_table,
    to_json,
    wan_table,
    wifi_table,
)

console = Console()


def _emit(args, obj_for_json, renderable) -> None:
    """If --json flag set, print JSON; else rich render."""
    if getattr(args, "json", False):
        print(_json.dumps(to_json(obj_for_json), indent=2))
    else:
        console.print(renderable)


def cmd_setup(_args) -> None:
    cfg.run_setup()


def cmd_clear_password(_args) -> None:
    cfg.clear_stored_password()


def cmd_login(_args) -> None:
    with router():
        console.print("[bold green]Login OK[/bold green]")


def cmd_status(args) -> None:
    with router() as r:
        s = r.get_status()
    _emit(args, s, status_table(s))


def cmd_clients(args) -> None:
    with router() as r:
        s = r.get_status()
    if getattr(args, "json", False):
        print(_json.dumps([to_json(d) for d in s.devices], indent=2))
    else:
        console.print(clients_table(s))


def cmd_wan(args) -> None:
    with router() as r:
        ipv4 = r.get_ipv4_status()
    _emit(args, ipv4, wan_table(ipv4))


def cmd_wifi(args) -> None:
    with router() as r:
        s = r.get_status()
    if getattr(args, "json", False):
        print(_json.dumps({
            b: {
                "host": getattr(s, f"wifi_{b}_enable", None),
                "guest": getattr(s, f"guest_{b}_enable", None),
                "iot": getattr(s, f"iot_{b}_enable", None),
            }
            for b in ("2g", "5g", "6g")
        }, indent=2))
    else:
        console.print(wifi_table(s))


def cmd_firmware(args) -> None:
    with router() as r:
        fw = r.get_firmware()
    _emit(args, fw, firmware_panel(fw))


def cmd_reboot(args) -> None:
    if not args.yes:
        console.print("[yellow]This drops every connection.[/yellow]")
        if console.input("Type REBOOT: ").strip() != "REBOOT":
            console.print("Aborted.")
            return
    with router() as r:
        r.reboot()
    console.print("[green]Reboot command sent.[/green]")


def cmd_all(args) -> None:
    with router() as r:
        fw = r.get_firmware()
        s = r.get_status()
        ipv4 = r.get_ipv4_status()
    if getattr(args, "json", False):
        print(_json.dumps({
            "firmware": to_json(fw),
            "status": to_json(s),
            "wan": to_json(ipv4),
        }, indent=2))
        return
    console.print(firmware_panel(fw))
    console.print(status_table(s))
    console.print(wan_table(ipv4))
    console.print(clients_table(s))


def cmd_wifi_toggle(args) -> None:
    band = args.band.lower()
    which = args.which.lower()
    enable = args.state == "on"
    name_map = {
        ("host", "2g"): Connection.HOST_2G,
        ("host", "5g"): Connection.HOST_5G,
        ("host", "6g"): Connection.HOST_6G,
        ("guest", "2g"): Connection.GUEST_2G,
        ("guest", "5g"): Connection.GUEST_5G,
        ("guest", "6g"): Connection.GUEST_6G,
        ("iot", "2g"): Connection.IOT_2G,
        ("iot", "5g"): Connection.IOT_5G,
        ("iot", "6g"): Connection.IOT_6G,
    }
    target = name_map.get((which, band))
    if target is None:
        console.print(f"[red]Unknown combination {which}/{band}[/red]")
        return
    with router() as r:
        r.set_wifi(target, enable)
    console.print(f"[green]{which} {band} → {args.state}[/green]")


def cmd_dhcp(args) -> None:
    with router() as r:
        leases = r.get_ipv4_dhcp_leases()
        try:
            reservations = r.get_ipv4_reservations()
        except Exception:
            reservations = []
    if getattr(args, "json", False):
        print(_json.dumps({
            "leases": [to_json(l) for l in leases],
            "reservations": [to_json(x) for x in reservations],
        }, indent=2))
        return
    console.print(dhcp_leases_table(leases))
    if reservations:
        console.print(reservations_table(reservations))


def cmd_wol(args) -> None:
    mac = wol_mod.resolve_mac(args.target)
    if not mac:
        console.print(f"[red]No MAC for {args.target!r} (not seen in DB).[/red]")
        return
    wol_mod.send_wol(mac, broadcast=args.broadcast, port=args.port)
    console.print(f"[green]WOL magic packet sent to {mac}[/green]")


def cmd_qr(args) -> None:
    if args.save:
        qr_mod.save_wifi_qr(args.ssid, args.password, args.save, security=args.security)
        console.print(f"[green]Saved QR to {args.save}[/green]")
    else:
        qr_mod.print_wifi_qr(args.ssid, args.password, security=args.security, hidden=args.hidden)


def cmd_log(_args) -> None:
    with router() as r:
        s = r.get_status()
    ts = db_mod.record_snapshot(s)
    console.print(f"[green]Snapshot recorded @ {ts}[/green] (clients={s.clients_total})")


def cmd_report(args) -> None:
    data = db_mod.report(days=args.days)
    if getattr(args, "json", False):
        print(_json.dumps(data, indent=2))
        return
    console.print(f"[bold cyan]Report — last {data['days']} day(s)[/bold cyan]")
    console.print(f"snapshots: {data['snapshots']}")
    console.print(f"clients: avg {data['avg_clients']:.1f}, peak {data['peak_clients']}" if data["avg_clients"] else "clients: no data")
    if data["avg_cpu"] is not None:
        console.print(f"CPU: avg {data['avg_cpu']*100:.0f}%, max {data['max_cpu']*100:.0f}%")
    if data["avg_mem"] is not None:
        console.print(f"Mem: avg {data['avg_mem']*100:.0f}%, max {data['max_mem']*100:.0f}%")
    if data["speedtest_count"]:
        console.print(
            f"speedtest: {data['speedtest_count']} runs, avg "
            f"↓{data['speedtest_avg_down']:.1f} ↑{data['speedtest_avg_up']:.1f} Mbps, "
            f"{data['speedtest_avg_ping']:.0f} ms ping"
        )
    from rich.table import Table
    t = Table(title="Top devices by traffic usage", title_style="bold cyan")
    for col in ("Hostname", "IP", "MAC", "Max usage (B)", "Samples"):
        t.add_column(col)
    for d in data["devices"][: args.top]:
        t.add_row(d["hostname"] or "-", d["ip"] or "-", d["mac"] or "-", str(d["max_usage"]), str(d["samples"]))
    console.print(t)


def cmd_metrics(args) -> None:
    from . import metrics
    metrics.serve(port=args.port, interval=args.interval)


def cmd_web(args) -> None:
    from . import web
    web.serve(host=args.host, port=args.port)


def cmd_watch(args) -> None:
    from . import watch
    watch.watch_loop(interval=args.interval, log_to_db=args.log, alert=not args.no_alert)


def cmd_speedtest(args) -> None:
    from . import speedtest_cmd
    r = speedtest_cmd.run_and_record()
    if getattr(args, "json", False):
        print(_json.dumps(r, indent=2))
        return
    console.print(
        f"[bold]↓[/bold] {r['down_mbps']:.1f} Mbps   "
        f"[bold]↑[/bold] {r['up_mbps']:.1f} Mbps   "
        f"[bold]ping[/bold] {r['ping_ms']:.0f} ms\n"
        f"[mute]server:[/mute] {r['server']}"
    )
    if r["cpu"] is not None:
        console.print(f"router @ CPU {r['cpu']*100:.0f}%, mem {r['mem']*100:.0f}%, clients {r['clients']}")


def cmd_tray(_args) -> None:
    from . import tray
    tray.run()


# ----- new commands -----

def cmd_alias_set(args) -> None:
    aliases_mod.set_alias(args.mac, args.name)
    console.print(f"[green]{args.mac} → {args.name}[/green]")


def cmd_alias_remove(args) -> None:
    if aliases_mod.remove_alias(args.mac):
        console.print(f"[green]removed alias for {args.mac}[/green]")
    else:
        console.print(f"[yellow]no alias for {args.mac}[/yellow]")


def cmd_alias_list(args) -> None:
    a = aliases_mod.load()
    if getattr(args, "json", False):
        print(_json.dumps(a, indent=2))
        return
    if not a:
        console.print("[yellow]no aliases[/yellow]")
        return
    from rich.table import Table
    t = Table(title="Aliases")
    t.add_column("MAC"); t.add_column("Name")
    for mac, name in sorted(a.items()):
        t.add_row(mac, name)
    console.print(t)


def cmd_vendor(args) -> None:
    name = vendor_mod.vendor(args.mac)
    if not name:
        console.print(f"[yellow]unknown OUI for {args.mac}[/yellow]")
    else:
        console.print(f"[bold]{args.mac}[/bold] → {name}")


def cmd_rdns(args) -> None:
    name = rdns_mod.reverse(args.ip)
    print(name if name else f"(no PTR for {args.ip})")


def cmd_publicip(args) -> None:
    r = publicip_mod.check_and_record()
    if getattr(args, "json", False):
        print(_json.dumps(r, indent=2))
        return
    if r["ip"] is None:
        console.print("[red]could not fetch public IP[/red]")
        return
    if r["changed"]:
        console.print(f"[bold red]changed:[/bold red] {r['previous']} → {r['ip']}")
    else:
        console.print(f"public IP: [bold]{r['ip']}[/bold]" + ("" if r["previous"] == r["ip"] else " (first record)"))


def cmd_firmware_check(args) -> None:
    with router() as r:
        fw = r.get_firmware()
    latest = fwchk.latest_for_model(fw.model)
    url = fwchk.published_url(fw.model)
    console.print(f"installed: [bold]{fw.firmware_version}[/bold]")
    console.print(f"latest:    [bold]{latest or '?'}[/bold]")
    console.print(f"page:      {url}")


def cmd_latency(args) -> None:
    samples = latency_mod.probe_and_record(workers=args.workers, timeout=args.timeout)
    if getattr(args, "json", False):
        print(_json.dumps(samples, indent=2))
        return
    from rich.table import Table
    aliases = aliases_mod.load()
    t = Table(title=f"Latency probe ({len(samples)} clients)")
    for col in ("Name", "MAC", "IP", "RTT", "Reachable"):
        t.add_column(col)
    for s in sorted(samples, key=lambda x: (x["rtt_ms"] is None, x["rtt_ms"] or 0)):
        mac_n = (s["mac"] or "").upper().replace("-", ":")
        t.add_row(
            aliases.get(mac_n, "-"),
            s["mac"],
            s["ip"] or "-",
            f"{s['rtt_ms']:.1f} ms" if s["rtt_ms"] is not None else "[red]timeout[/red]",
            "[green]yes[/green]" if s["reachable"] else "[red]no[/red]",
        )
    console.print(t)


def cmd_ping(args) -> None:
    rtt = latency_mod.ping_once(args.target, timeout=args.timeout)
    if rtt is None:
        console.print(f"[red]{args.target} unreachable[/red]")
    else:
        console.print(f"[green]{args.target}[/green] {rtt:.1f} ms")


def cmd_discover(args) -> None:
    res = discover_mod.scan_all(timeout=args.timeout)
    if getattr(args, "json", False):
        print(_json.dumps(res, indent=2))
        return
    from rich.table import Table
    t = Table(title=f"mDNS ({len(res['mdns'])})")
    for c in ("Service", "Name", "Host", "Port", "Addresses"): t.add_column(c)
    for x in res["mdns"]:
        t.add_row(x["service"], x["name"], x["host"], str(x["port"]), ", ".join(x["addresses"]))
    console.print(t)
    t2 = Table(title=f"SSDP ({len(res['ssdp'])})")
    for c in ("IP", "ST", "Server"): t2.add_column(c)
    for x in res["ssdp"]:
        t2.add_row(x["ip"], x.get("st") or "-", x.get("server") or "-")
    console.print(t2)


def cmd_presence(args) -> None:
    p = presence_mod.who_is_present()
    if getattr(args, "json", False):
        print(_json.dumps(p, indent=2))
        return
    console.print(f"[bold]Present ({len(p['present'])})[/bold]")
    for x in p["present"]:
        console.print(f"  [green]●[/green] {x.get('name') or x.get('hostname') or x['mac']} [mute]({x['mac']})[/mute]")
    console.print(f"[bold]Absent ({len(p['absent'])})[/bold]")
    for x in p["absent"]:
        console.print(f"  [red]○[/red] {x['name']} [mute]({x['mac']})[/mute]")


def cmd_csv(args) -> None:
    from pathlib import Path
    out = Path(args.out)
    if args.what == "snapshots":
        n = csv_mod.export_snapshots(out, days=args.days)
    elif args.what == "devices":
        n = csv_mod.export_devices(out, days=args.days)
    else:
        console.print("[red]unknown[/red]"); return
    console.print(f"[green]wrote {n} rows to {out}[/green]")


def cmd_events(args) -> None:
    rows = db_mod.recent_events(limit=args.limit)
    if getattr(args, "json", False):
        print(_json.dumps(rows, indent=2))
        return
    from rich.table import Table
    t = Table(title=f"Recent events ({len(rows)})")
    for c in ("When", "Kind", "MAC", "Payload"): t.add_column(c)
    import datetime
    for r in rows:
        t.add_row(
            datetime.datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M:%S"),
            r["kind"], r["mac"] or "-", (r["payload"] or "")[:80],
        )
    console.print(t)


def cmd_daemon(args) -> None:
    from . import daemon
    daemon.run(
        snap_every=args.snap, latency_every=args.latency,
        publicip_every=args.publicip,
        extping_every=getattr(args, "extping", 300),
        anomaly_every=getattr(args, "anomaly", 3600),
        automation=getattr(args, "automation", True),
        watchdog=getattr(args, "watchdog", False),
        watchdog_interval=getattr(args, "watchdog_interval", 60),
        watchdog_auto_reboot=getattr(args, "watchdog_auto_reboot", False),
        retention_every=getattr(args, "retention", 86400) or None,
        dns_filter=getattr(args, "dns_filter", False),
        dns_port=getattr(args, "dns_port", None),
    )


def cmd_mqtt_publish(args) -> None:
    c = cfg.load_config()
    mq = c.get("mqtt") or {}
    if not mq.get("host"):
        console.print("[red]no mqtt config in config.json[/red]"); return
    if args.discovery:
        mqtt_mod.publish_discovery(mq)
        console.print("[green]discovery published[/green]")
    if args.state:
        with router() as r:
            s = r.get_status()
        mqtt_mod.publish_state(mq, s, public_ip=publicip_mod.fetch_public_ip())
        console.print("[green]state published[/green]")


def cmd_schedule(args) -> None:
    from pathlib import Path
    out = Path(args.out)
    sched_mod.emit_xml(out)
    console.print(f"[green]wrote {out}[/green]")
    console.print("Import via: [bold]schtasks /create /tn c6u_daemon /xml " + str(out) + "[/bold]")


def cmd_profile_list(_args) -> None:
    profs = cfg.list_profiles()
    if not profs:
        console.print("[yellow]no profiles in profiles/[/yellow] (default config.json is always available)")
        return
    for p in profs:
        console.print(f"  {p}")


# ===== new command handlers =====

def cmd_notify(args) -> None:
    from . import pushnotify
    c = cfg.load_config(interactive=False)
    fired = pushnotify.push(c.get("push"), args.title, args.body,
                             priority=args.priority, tags=args.tags)
    if not fired:
        console.print("[yellow]no push provider configured in config.json -> push[/yellow]")
        return
    console.print(f"[green]sent via:[/green] {', '.join(fired)}")


def cmd_rules_list(_args) -> None:
    from . import rules
    rs = rules.load_rules()
    if not rs:
        console.print("[yellow]no rules.json/rules.yaml found[/yellow]")
        return
    from rich.table import Table
    t = Table(title=f"{len(rs)} rules")
    for col in ("Name", "When", "Actions"): t.add_column(col)
    for r in rs:
        t.add_row(r.get("name", "-"), _json.dumps(r.get("when", {})),
                  ", ".join(next(iter(a)) for a in r.get("then", []) if isinstance(a, dict)))
    console.print(t)


def cmd_rules_example(_args) -> None:
    from . import rules
    p = rules.write_example()
    console.print(f"[green]wrote {p}[/green] — copy to rules.json and edit.")


def cmd_rules_test(args) -> None:
    from . import rules
    event = {"kind": args.kind, "mac": args.mac, "hostname": args.hostname, "ip": args.ip}
    event = {k: v for k, v in event.items() if v is not None}
    fired = rules.dispatch(event)
    console.print(f"[green]{fired} action(s) fired[/green]")


def cmd_auto_list(_args) -> None:
    from . import automation
    jobs = automation.load_jobs()
    if not jobs:
        console.print("[yellow]no automation.json found[/yellow]")
        return
    from rich.table import Table
    t = Table(title=f"{len(jobs)} jobs")
    for col in ("Name", "Cron", "Action"): t.add_column(col)
    for j in jobs:
        action = j.get("action") or {}
        kind = next(iter(action), "?") if action else "?"
        t.add_row(j.get("name", "-"), j.get("cron", ""), kind)
    console.print(t)


def cmd_auto_example(_args) -> None:
    from . import automation
    p = automation.write_example()
    console.print(f"[green]wrote {p}[/green] — copy to automation.json and edit.")


def cmd_auto_run(_args) -> None:
    from . import automation
    console.print("[bold green]automation runner started[/bold green] (ctrl-C to stop)")
    automation.run()


def cmd_watchdog(args) -> None:
    from . import watchdog
    console.print("[bold green]watchdog started[/bold green] (ctrl-C to stop)")
    watchdog.run(interval=args.interval, timeout=args.timeout,
                 fail_threshold=args.fail_threshold, auto_reboot=args.auto_reboot)


def cmd_rotate(args) -> None:
    from . import rotate
    if getattr(args, "rotate_cmd", None) == "history":
        return cmd_rotate_history(args)
    r = rotate.rotate(try_apply=args.try_apply)
    console.print(f"[bold green]new password:[/bold green] {r['password']}")
    console.print(f"applied via API: {r['applied']}")
    console.print(f"[mute]stored in keyring under {r['keyring_user']}[/mute]")
    if not r["applied"]:
        console.print("[yellow]Set this on the router admin page manually to complete rotation.[/yellow]")


def cmd_rotate_history(_args) -> None:
    from . import rotate
    from rich.table import Table
    h = rotate.history()
    t = Table(title=f"rotation history ({len(h)})")
    for col in ("when", "fingerprint"): t.add_column(col)
    import datetime
    for e in h:
        t.add_row(datetime.datetime.fromtimestamp(e["ts"]).strftime("%Y-%m-%d %H:%M"),
                  e.get("fp", "-"))
    console.print(t)


def cmd_fingerprint(args) -> None:
    from . import fingerprint
    from .client import router
    with router() as r:
        s = r.get_status()
    devs = [{"mac": str(d.macaddress) or "",
             "hostname": d.hostname,
             "ip": str(d.ipaddress) if d.ipaddress else None} for d in s.devices]
    results = fingerprint.fingerprint_all(devs, scan_ports=args.scan_ports)
    if getattr(args, "json", False):
        print(_json.dumps(results, indent=2))
        return
    from rich.table import Table
    t = Table(title=f"Fingerprint ({len(results)} devices)")
    for col in ("MAC", "Hostname", "Vendor", "Guesses", "Open ports"): t.add_column(col)
    for r in results:
        t.add_row(r["mac"], r.get("hostname") or "-", r.get("vendor") or "-",
                  ", ".join(r["guesses"]) or "-",
                  ", ".join(str(p) for p in r.get("open_ports", [])))
    console.print(t)


def cmd_heatmap(args) -> None:
    from . import heatmap as heatmap_mod
    if args.mac:
        data = heatmap_mod.heatmap(args.mac, days=args.days)
        if getattr(args, "json", False):
            print(_json.dumps(data, indent=2)); return
        _render_heatmap(data)
    else:
        data = heatmap_mod.heatmap_all(days=args.days, top=args.top)
        if getattr(args, "json", False):
            print(_json.dumps(data, indent=2)); return
        for d in data:
            console.print(f"[bold]{d.get('hostname') or '-'}[/bold] [mute]{d['mac']}[/mute]")
            _render_heatmap(d)


def _render_heatmap(data: dict) -> None:
    from rich.table import Table
    t = Table(title=f"Heatmap ({data['days']}d)")
    t.add_column(" ")
    for h in range(24):
        t.add_column(f"{h:02d}", justify="right")
    max_v = max((max(row) if row else 0) for row in data["grid"]) or 1
    shades = (".", "·", "▂", "▄", "▆", "█")
    for dow, row in enumerate(data["grid"]):
        cells = []
        for v in row:
            idx = 0 if v == 0 else min(len(shades) - 1, 1 + int((v / max_v) * (len(shades) - 2)))
            color = "dim" if v == 0 else ("green" if v < max_v * 0.5 else "yellow" if v < max_v * 0.8 else "red")
            cells.append(f"[{color}]{shades[idx]}[/{color}]")
        t.add_row(data["labels_dow"][dow], *cells)
    console.print(t)


def cmd_cve(args) -> None:
    from . import cve
    from .client import router
    with router() as r:
        fw = r.get_firmware()
    result = cve.check(fw.model, firmware=fw.firmware_version)
    if getattr(args, "json", False):
        print(_json.dumps(result, indent=2)); return
    console.print(f"[bold]model[/bold] {fw.model}   [bold]fw[/bold] {fw.firmware_version}")
    console.print(f"total CVEs: {result['total']}   matching firmware: {result['matching_firmware']}")
    if result["firmware_hits"]:
        console.print("[bold red]matches your firmware version:[/bold red]")
        for c in result["firmware_hits"][:10]:
            console.print(f"  {c['id']}  CVSS {c.get('cvss') or '-'}  {c['description'][:160]}")
    elif result["cves"]:
        console.print(f"no firmware-specific hits; showing {min(10, len(result['cves']))} recent CVEs for the model:")
        for c in result["cves"][:10]:
            console.print(f"  {c['id']}  CVSS {c.get('cvss') or '-'}  {c['description'][:160]}")


def cmd_sla(args) -> None:
    from . import sla
    data = sla.report(days=args.days)
    if getattr(args, "json", False):
        print(_json.dumps(data, indent=2)); return
    console.print(f"[bold]ISP SLA — last {data['days']}d ({data['samples']} samples)[/bold]")
    con = data["contract"] or {}
    if con:
        console.print(f"contracted: ↓{con.get('down_mbps')}  ↑{con.get('up_mbps')}  ({con.get('provider','?')})")
    for k in ("down_mbps", "up_mbps", "ping_ms"):
        v = data[k]
        if v.get("count"):
            console.print(f"  {k:10}  mean {v['mean']:.1f}  p10 {v['p10']:.1f}  p95 {v['p95']:.1f}")
    if "down_percent_of_contract" in data:
        console.print(f"[bold]↓ % of contract:[/bold] {data['down_percent_of_contract']:.0f}%   "
                      f"SLA (>=80%) met: {data['down_sla_met_percent']:.0f}% of samples")
    if "up_percent_of_contract" in data:
        console.print(f"[bold]↑ % of contract:[/bold] {data['up_percent_of_contract']:.0f}%   "
                      f"SLA (>=80%) met: {data['up_sla_met_percent']:.0f}% of samples")
    if data["outage_events"]:
        console.print(f"[yellow]{len(data['outage_events'])} outage events in window[/yellow]")


def cmd_extping(args) -> None:
    from . import extping
    results = extping.probe()
    if getattr(args, "json", False):
        print(_json.dumps(results, indent=2)); return
    from rich.table import Table
    t = Table(title=f"External latency ({len(results)} targets)")
    for col in ("Name", "Target", "RTT", "OK"): t.add_column(col)
    for r in results:
        t.add_row(r["name"], r["target"],
                  f"{r['rtt_ms']:.1f} ms" if r.get("rtt_ms") is not None else "[red]timeout[/red]",
                  "[green]yes[/green]" if r["ok"] else "[red]no[/red]")
    console.print(t)


def cmd_telegram(_args) -> None:
    from . import tgbot
    console.print("[bold green]telegram bot running[/bold green]")
    tgbot.run_polling()


def cmd_discord(args) -> None:
    from . import discordbot
    ok = discordbot.send_text(args.text)
    console.print("[green]sent[/green]" if ok else "[yellow]no discord webhook configured[/yellow]")


def cmd_portscan(args) -> None:
    from . import portscan
    # Resolve port list from --ports spec.
    default_ports = portscan.LAN_PORTS if getattr(args, "lan", False) else portscan.COMMON_PORTS
    try:
        ports = portscan.parse_ports(args.ports) if args.ports else default_ports
    except ValueError as e:
        console.print(f"[red]{e}[/red]"); return

    kw: dict = {"ports": ports}
    if args.timeout is not None: kw["timeout"] = args.timeout
    if args.workers is not None: kw["workers"] = args.workers
    if args.retry_timeout is not None:
        # 0 → disable retry by making retry_timeout <= timeout.
        kw["retry_timeout"] = args.retry_timeout if args.retry_timeout > 0 else 0

    if getattr(args, "lan", False):
        r = portscan.scan_lan(**kw)
        if getattr(args, "json", False):
            print(_json.dumps(r, indent=2)); return
        from rich.table import Table
        t = Table(title=f"LAN port scan ({len(r['devices'])} hosts × {r['checked_per_host']} ports, "
                        f"{r.get('total_timeouts', 0)} timeouts)")
        for col in ("Name", "Hostname", "IP", "MAC", "Vendor", "Open ports"):
            t.add_column(col)
        for d in r["devices"]:
            open_s = ", ".join(str(p) for p in d["open"]) or "[dim]-[/dim]"
            if portscan.RISKY_LAN_PORTS.intersection(d["open"]):
                open_s = "[bold red]" + ", ".join(str(p) for p in d["open"]) + "[/bold red]"
            t.add_row(d.get("alias") or "-", d["hostname"] or "-", d["ip"],
                      d["mac"] or "-", d["vendor"] or "-", open_s)
        console.print(t)
        risky_hosts = portscan.risky_findings(r)
        if risky_hosts:
            console.print(f"\n[bold red]{len(risky_hosts)} host(s) with risky ports open:[/bold red]")
            for h in risky_hosts:
                console.print(f"  {h['alias'] or h['hostname'] or h['ip']}  -> {h['risky_ports']}")
        else:
            console.print("\n[green]no risky LAN ports found[/green]")
        return

    # Public-IP / single-target path.
    if args.target:
        kw["ip"] = args.target
    r = portscan.scan(**kw)
    if getattr(args, "json", False):
        print(_json.dumps(r, indent=2)); return
    if r.get("error"):
        console.print(f"[red]{r['error']}[/red]"); return
    console.print(f"[bold]IP:[/bold] {r['ip']}   checked: {r['checked']}")
    if r["open"]:
        console.print(f"[bold red]open ports:[/bold red] {', '.join(str(p) for p in r['open'])}")
    else:
        console.print("[green]no ports open[/green]")


def cmd_arpwatch(_args) -> None:
    from . import arpwatch
    r = arpwatch.check()
    console.print(f"ARP entries: {r['entries']}")
    if r["changes_since_last"]:
        console.print("[bold yellow]MAC changes since last check:[/bold yellow]")
        for ch in r["changes_since_last"]:
            console.print(f"  {ch['ip']}: {ch['old_mac']} -> {ch['new_mac']}")
    else:
        console.print("[green]no ARP changes[/green]")
    for conf in r["mac_with_multiple_ips"]:
        if len(conf["ips"]) > 1:
            console.print(f"  MAC {conf['mac']} at IPs: {', '.join(conf['ips'])}")


def cmd_dnscheck(_args) -> None:
    from . import dnscheck
    r = dnscheck.check()
    console.print(f"checked: {r['checked']}, suspect: {r['hijack_suspected']}")
    for x in r["results"]:
        mark = "[red]!!![/red]" if x["divergent"] else "[green]ok[/green]"
        console.print(f"  {mark} {x['domain']}  sys={x['system']}  cf={x['cloudflare']}")


def cmd_hibp(args) -> None:
    from . import hibp
    if args.what == "password":
        pw = args.value
        if not pw:
            import getpass as gp
            pw = gp.getpass("password (hidden): ")
        n = hibp.check_password(pw)
        if n < 0:
            console.print("[yellow]lookup failed[/yellow]")
        elif n == 0:
            console.print("[green]not found in pwned-passwords breaches[/green]")
        else:
            console.print(f"[bold red]seen {n:,} times in breaches — rotate![/bold red]")
    elif args.what == "email":
        if not args.value:
            console.print("[red]supply an email[/red]"); return
        res = hibp.check_email(args.value)
        if res is None:
            console.print("[yellow]set config.hibp.api_key first[/yellow]"); return
        if not res:
            console.print(f"[green]{args.value}: not found in any breach (or key lacks access)[/green]")
        else:
            for b in res:
                console.print(f"  [red]{b.get('Name')}[/red]  {b.get('BreachDate')}  ({b.get('PwnCount')})")
    else:  # config
        res = hibp.check_config_emails()
        if not res["emails"]:
            console.print("no emails found in config"); return
        for e in res["results"]:
            br = e["breaches"]
            if br is None:
                console.print(f"{e['email']}: [yellow]set hibp.api_key to check[/yellow]")
            elif not br:
                console.print(f"{e['email']}: [green]clean[/green]")
            else:
                console.print(f"{e['email']}: [red]{len(br)} breach(es)[/red]")


def cmd_tlswatch(_args) -> None:
    from . import tlswatch
    try:
        r = tlswatch.check()
    except Exception as e:
        console.print(f"[red]{e}[/red]"); return
    if not r.get("watched", True):
        console.print(f"[yellow]{r.get('reason')}[/yellow]"); return
    info = r["info"]
    console.print(f"subject: {info['subject']}")
    console.print(f"issuer:  {info['issuer']}")
    console.print(f"valid:   {info['not_before']} -> {info['not_after']}")
    console.print(f"pin:     [bold]{info['pin']}[/bold]")
    if r["changed"]:
        console.print(f"[bold red]PIN CHANGED![/bold red] previous: {r['previous_pin']}")
    else:
        console.print("[green]pin unchanged[/green]" if r["previous_pin"] else "[mute](first record)[/mute]")


def cmd_tui(_args) -> None:
    from . import tui
    tui.run()


def cmd_repl(_args) -> None:
    from . import repl
    repl.run()


def cmd_sql(args) -> None:
    from . import sqlcli
    try:
        cols, rows = sqlcli.run(args.statement, allow_mutate=args.mutate)
    except Exception as e:
        console.print(f"[red]{e}[/red]"); return
    if getattr(args, "json", False):
        print(_json.dumps([dict(zip(cols, r)) for r in rows], indent=2, default=str))
        return
    from rich.table import Table
    t = Table()
    for c in cols:
        t.add_column(c)
    for r in rows[:500]:
        t.add_row(*(str(v) if v is not None else "-" for v in r))
    console.print(t)
    if len(rows) > 500:
        console.print(f"[mute]({len(rows)} rows total; truncated to 500)[/mute]")


def cmd_search_query(args) -> None:
    from . import search
    try:
        rows = search.query(args.q, limit=args.limit)
    except Exception as e:
        console.print(f"[red]{e}[/red]"); return
    from rich.table import Table
    import datetime
    t = Table(title=f"results ({len(rows)})")
    for col in ("When", "Kind", "MAC", "Payload"): t.add_column(col)
    for r in rows:
        t.add_row(datetime.datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M"),
                  r["kind"], r.get("mac") or "-", (r.get("payload") or "")[:80])
    console.print(t)


def cmd_search_rebuild(_args) -> None:
    from . import search
    n = search.rebuild()
    console.print(f"[green]indexed {n} events[/green]")


def cmd_digest(args) -> None:
    from . import digest
    p = digest.write(args.out, days=args.days)
    console.print(f"[green]wrote {p}[/green]")


def cmd_backup(args) -> None:
    from . import backup
    p = backup.create(args.out)
    console.print(f"[green]wrote {p}[/green]")


def cmd_restore(args) -> None:
    from . import backup
    names = backup.restore(args.archive, overwrite=args.overwrite)
    console.print(f"[green]restored {len(names)} files[/green]")
    for n in names:
        console.print(f"  {n}")


def cmd_anomaly(args) -> None:
    from . import anomaly
    out = anomaly.scan(baseline_days=args.baseline_days, recent_minutes=args.recent_minutes)
    if getattr(args, "json", False):
        print(_json.dumps(out, indent=2)); return
    if not out:
        console.print("[green]no anomalies detected[/green]"); return
    from rich.table import Table
    t = Table(title=f"anomalies ({len(out)})")
    for col in ("Kind", "MAC", "Hostname", "Details"): t.add_column(col)
    for a in out:
        details = ", ".join(f"{k}={v}" for k, v in a.items() if k not in ("kind", "mac", "hostname"))
        t.add_row(a["kind"], a.get("mac", "-"), a.get("hostname") or "-", details)
    console.print(t)


def cmd_parental_list(_args) -> None:
    from . import parental
    rs = parental.load_rules()
    if not rs:
        console.print("[yellow]no parental.json[/yellow]"); return
    from rich.table import Table
    t = Table(title="parental rules")
    for col in ("MAC", "Windows"): t.add_column(col)
    for r in rs:
        wins = "; ".join(f"dow={w.get('dow')} {w['from']}-{w['to']}" for w in r.get("block", []))
        t.add_row(r.get("mac", ""), wins)
    console.print(t)


def cmd_parental_example(_args) -> None:
    from . import parental
    p = parental.write_example()
    console.print(f"[green]wrote {p}[/green]")


def cmd_parental_apply(args) -> None:
    from . import parental
    r = parental.evaluate_and_apply(dry_run=args.dry_run)
    console.print(f"{r['rules']} rule(s), {len(r['decisions'])} decision(s)")
    for d in r["decisions"]:
        state = "BLOCK" if d["block"] else "ALLOW"
        note = "" if d["applied"] or args.dry_run else "  [yellow](no firmware method available — logged only)[/yellow]"
        console.print(f"  {d['mac']}: {state}{note}")


# ===== round-3 handlers =====

def cmd_dns_run(args) -> None:
    from . import dnsfilter
    console.print("[bold green]DNS filter starting[/bold green] - point your router's DHCP DNS at this machine.")
    dnsfilter.run(port=args.port)


def cmd_dns_stats(args) -> None:
    from . import dnsfilter
    d = dnsfilter.stats(days=args.days)
    if getattr(args, "json", False):
        print(_json.dumps(d, indent=2)); return
    console.print(f"[bold]queries (last {d['days']}d):[/bold] {d['total']}   "
                  f"[bold]blocked:[/bold] {d['blocked']} ({d['block_pct']:.1f}%)")
    from rich.table import Table
    if d["top_domains"]:
        t = Table(title="Top domains")
        t.add_column("Domain"); t.add_column("Queries", justify="right")
        for r in d["top_domains"]:
            t.add_row(r["qname"], str(r["n"]))
        console.print(t)
    if d["top_blocked"]:
        t = Table(title="Top blocked")
        t.add_column("Domain"); t.add_column("Queries", justify="right")
        for r in d["top_blocked"]:
            t.add_row(r["qname"], str(r["n"]))
        console.print(t)
    if d["top_clients"]:
        t = Table(title="Top clients")
        t.add_column("IP"); t.add_column("MAC"); t.add_column("Queries", justify="right")
        for r in d["top_clients"]:
            t.add_row(r["client_ip"] or "-", r.get("client_mac") or "-", str(r["n"]))
        console.print(t)


def cmd_dns_blocklist_update(_args) -> None:
    from . import dnsfilter
    r = dnsfilter.update_blocklists()
    console.print(f"[green]loaded {r['total']} blocked domains[/green]")
    for name, n in r["loaded"].items():
        console.print(f"  {name}: {n}")


def cmd_netflow_run(args) -> None:
    from . import netflow
    console.print(f"[bold green]NetFlow receiver on :{args.port}[/bold green] (v5)")
    netflow.run(port=args.port)


def cmd_netflow_top(args) -> None:
    from . import netflow
    flows = netflow.top(days=args.days, by=args.by, limit=30)
    sources = netflow.by_src_ip(days=args.days, limit=30)
    if getattr(args, "json", False):
        print(_json.dumps({"flows": flows, "sources": sources}, indent=2)); return
    from rich.table import Table
    t = Table(title=f"Top flows by {args.by} ({args.days}d)")
    for col in ("Src", "Dst", "Proto", "DstPort", "Bytes", "Packets"):
        t.add_column(col)
    for r in flows:
        t.add_row(r["src_ip"], r["dst_ip"], str(r["protocol"]),
                  str(r["dst_port"]), str(r["tot_bytes"]), str(r["tot_packets"]))
    console.print(t)
    t2 = Table(title="Top source IPs")
    for col in ("Src", "Bytes", "Packets", "Peers"):
        t2.add_column(col)
    for r in sources:
        t2.add_row(r["src_ip"], str(r["tot_bytes"]), str(r["tot_packets"]), str(r["uniq_peers"]))
    console.print(t2)


def cmd_pcap_interfaces(_args) -> None:
    from . import pcap
    if not pcap.tshark_available():
        console.print("[red]tshark not on PATH - install Wireshark.[/red]"); return
    for i in pcap.list_interfaces():
        console.print(f"  {i['index']}. {i['name']}")


def cmd_pcap_burst(args) -> None:
    from . import pcap
    path = pcap.burst_capture(args.interface, seconds=args.seconds, filter_bpf=args.filter_bpf)
    if path:
        console.print(f"[green]wrote {path}[/green]")
    else:
        console.print("[red]capture failed[/red]")


def cmd_pdns(args) -> None:
    from . import passivedns
    is_ip = all(p.isdigit() for p in args.lookup.split(".") if p) and args.lookup.count(".") == 3
    if is_ip:
        host = passivedns.hostname_for(args.lookup)
        recs = passivedns.recent(ip=args.lookup)
        if getattr(args, "json", False):
            print(_json.dumps({"hostname": host, "records": recs}, indent=2)); return
        console.print(f"[bold]{args.lookup}[/bold] -> {host or '(unknown)'}")
    else:
        recs = passivedns.recent(hostname=args.lookup)
        if getattr(args, "json", False):
            print(_json.dumps(recs, indent=2)); return
        from rich.table import Table
        t = Table(title=f"Passive DNS matches for {args.lookup!r}")
        t.add_column("IP"); t.add_column("Hostname"); t.add_column("Last seen")
        import datetime
        for r in recs:
            when = datetime.datetime.fromtimestamp(r["last_seen"]).strftime("%Y-%m-%d %H:%M")
            t.add_row(r["ip"], r["hostname"], when)
        console.print(t)


def cmd_vpn_provision(args) -> None:
    from . import vpn
    r = vpn.provision(peer_names=args.peers, network=args.network,
                       listen_port=args.port, endpoint=args.endpoint, dns=args.dns)
    console.print(f"[green]wrote {r['server_config']}[/green]")
    console.print(f"server public key: [bold]{r['server_public']}[/bold]")
    console.print(f"network: {r['network']}  listen_port: {r['listen_port']}")
    console.print("[bold]Peers:[/bold]")
    for p in r["peers"]:
        console.print(f"  {p['name']}: {p['address']}  cfg={p['config']}" + (f"  QR={p['qr']}" if p["qr"] else ""))
    console.print("[yellow]To start the server:[/yellow] copy wg0.conf to /etc/wireguard/ and `wg-quick up wg0`")


def cmd_vpn_tailscale(_args) -> None:
    from . import vpn
    r = vpn.tailscale_status()
    if r is None:
        console.print("[yellow]tailscale not installed or not running[/yellow]"); return
    self_n = (r.get("Self") or {})
    console.print(f"[bold]Self[/bold]: {self_n.get('HostName')} ({self_n.get('TailscaleIPs', [''])[0]})")
    peers = (r.get("Peer") or {})
    for p in peers.values():
        online = "[green]online[/green]" if p.get("Online") else "[red]offline[/red]"
        console.print(f"  {p.get('HostName')}  {p.get('TailscaleIPs', [''])[0]}  {online}")


def cmd_acme_issue(args) -> None:
    from . import acme
    r = acme.issue(staging=args.staging)
    if not r.get("ok"):
        console.print(f"[red]{r.get('error')}[/red]"); return
    console.print(f"[green]cert:[/green] {r.get('cert')}")
    console.print(f"[green]key:[/green]  {r.get('key')}")
    console.print(f"[green]domain:[/green] {r.get('domain')}")


def cmd_acme_renew(_args) -> None:
    from . import acme
    r = acme.renew()
    console.print("[green]renewed[/green]" if r["ok"] else f"[red]{r.get('err') or r.get('log')}[/red]")


def cmd_acme_status(_args) -> None:
    from . import acme
    a = acme.active_cert()
    if not a:
        console.print("[yellow]no cert in certs/ - run `c6u acme issue`[/yellow]"); return
    console.print(f"cert: {a['cert']}")
    console.print(f"key:  {a['key']}")


def cmd_version(_args) -> None:
    from . import update as upd
    v = upd.current_version()
    if not v.get("commit"):
        console.print("[yellow](not a git checkout)[/yellow]"); return
    console.print(f"{v['commit'][:10]}  {v['subject']}")
    console.print(f"[mute]{v['committed']}[/mute]")


def cmd_update(args) -> None:
    from . import update as upd
    r = upd.update(pull=args.pull, deps=args.deps)
    if not r.get("ok"):
        console.print(f"[red]{r.get('error')}[/red]"); return
    if r["changed"]:
        console.print(f"[green]updated {r['before']['commit'][:10]} -> {r['after']['commit'][:10]}[/green]")
    else:
        console.print("[yellow]already up to date[/yellow]")
    for line in r.get("log", []):
        console.print(f"[mute]{line}[/mute]")


def cmd_retention_sweep(_args) -> None:
    from . import retention
    r = retention.sweep()
    console.print("[green]sweep done[/green]")
    for t, n in (r.get("deleted") or {}).items():
        if n:
            console.print(f"  {t}: deleted {n}")


def cmd_retention_sizes(_args) -> None:
    from . import retention
    s = retention.sizes()
    from rich.table import Table
    t = Table(title=f"Row counts ({len(s)} tables)")
    t.add_column("Table"); t.add_column("Rows", justify="right")
    for name, n in sorted(s.items()):
        t.add_row(name, str(n))
    console.print(t)


def cmd_retention_vacuum(_args) -> None:
    from . import retention
    retention.vacuum()
    console.print("[green]VACUUM done[/green]")


def cmd_notifier_recent(_args) -> None:
    from . import notifier
    import datetime
    rows = notifier.recent()
    from rich.table import Table
    t = Table(title="Recent notifications")
    for col in ("Kind", "Key", "Last", "Count"): t.add_column(col)
    for r in rows:
        t.add_row(r["kind"], r["key"],
                  datetime.datetime.fromtimestamp(r["last_ts"]).strftime("%m-%d %H:%M:%S"),
                  str(r["count"]))
    console.print(t)


def cmd_notifier_test(args) -> None:
    from . import notifier
    r = notifier.emit(args.kind, args.key, args.title, args.body, force=args.force)
    console.print(_json.dumps(r, indent=2))


def cmd_audit_seal(_args) -> None:
    from . import audit
    r = audit.seal()
    if r.get("sealed", 0) == 0:
        console.print("[yellow](nothing new to seal)[/yellow]"); return
    console.print(f"[green]sealed {r['sealed']} events[/green] ({r['start_id']}..{r['end_id']})")
    console.print(f"tip: [bold]{r['final_hash'][:16]}...[/bold]")


def cmd_audit_verify(_args) -> None:
    from . import audit
    r = audit.verify()
    if r.get("ok"):
        console.print(f"[green]audit OK[/green] ({r['seals']} seals)")
        if r.get("chain_tip"):
            console.print(f"tip: [mute]{r['chain_tip'][:16]}...[/mute]")
    else:
        console.print(f"[bold red]AUDIT FAILED[/bold red] at seal {r['failed_at']['ts']}")
        console.print(f"reason: {r['reason']}")


def cmd_plugins_list(_args) -> None:
    from . import plugins
    info = plugins.info()
    if not info:
        console.print("[yellow]no plugins in plugins/[/yellow]")
        console.print("[mute](see plugins/example_hello.py for a template)[/mute]"); return
    from rich.table import Table
    t = Table(title=f"Plugins ({len(info)})")
    for col in ("File", "Doc", "Hooks"): t.add_column(col)
    for p in info:
        t.add_row(p["file"], p["doc"] or "-", ", ".join(p["hooks"]) or "-")
    console.print(t)
