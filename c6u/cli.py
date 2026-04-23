"""argparse CLI entry point."""
from __future__ import annotations

import argparse
import sys

from rich.console import Console

from . import commands as c

console = Console()


def _add_json(p: argparse.ArgumentParser) -> None:
    p.add_argument("--json", action="store_true", help="output JSON instead of a table")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="c6u", description="TP-Link Archer C6U control CLI")
    p.add_argument("--debug", action="store_true", help="verbose logging")
    p.add_argument("--profile", metavar="NAME", help="use profiles/NAME.json instead of config.json")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="run first-run config wizard").set_defaults(func=c.cmd_setup)
    sub.add_parser("clear-password", help="delete stored password").set_defaults(func=c.cmd_clear_password)
    sub.add_parser("login", help="verify credentials").set_defaults(func=c.cmd_login)

    for name, fn in (
        ("status", c.cmd_status),
        ("clients", c.cmd_clients),
        ("wan", c.cmd_wan),
        ("wifi", c.cmd_wifi),
        ("firmware", c.cmd_firmware),
        ("all", c.cmd_all),
    ):
        sp = sub.add_parser(name)
        _add_json(sp)
        sp.set_defaults(func=fn)

    r = sub.add_parser("reboot", help="reboot the router")
    r.add_argument("-y", "--yes", action="store_true", help="skip confirmation")
    r.set_defaults(func=c.cmd_reboot)

    wt = sub.add_parser("wifi-toggle", help="enable/disable a wifi radio")
    wt.add_argument("which", choices=["host", "guest", "iot"])
    wt.add_argument("band", choices=["2g", "5g", "6g"])
    wt.add_argument("state", choices=["on", "off"])
    wt.set_defaults(func=c.cmd_wifi_toggle)

    dh = sub.add_parser("dhcp", help="DHCP leases + static reservations")
    _add_json(dh)
    dh.set_defaults(func=c.cmd_dhcp)

    wol = sub.add_parser("wol", help="send Wake-on-LAN magic packet")
    wol.add_argument("target", help="hostname (as seen by router) or MAC address")
    wol.add_argument("--broadcast", default="255.255.255.255")
    wol.add_argument("--port", type=int, default=9)
    wol.set_defaults(func=c.cmd_wol)

    qr = sub.add_parser("qr", help="print a WiFi-join QR code")
    qr.add_argument("ssid")
    qr.add_argument("password")
    qr.add_argument("--security", default="WPA", choices=["WPA", "WEP", "nopass"])
    qr.add_argument("--hidden", action="store_true")
    qr.add_argument("--save", help="save PNG to this path instead of printing ASCII")
    qr.set_defaults(func=c.cmd_qr)

    sub.add_parser("log", help="record one snapshot to SQLite").set_defaults(func=c.cmd_log)

    rp = sub.add_parser("report", help="summarize recent activity from SQLite")
    rp.add_argument("--days", type=int, default=7)
    rp.add_argument("--top", type=int, default=10)
    _add_json(rp)
    rp.set_defaults(func=c.cmd_report)

    m = sub.add_parser("metrics", help="run Prometheus metrics HTTP server")
    m.add_argument("--port", type=int, default=9100)
    m.add_argument("--interval", type=int, default=30)
    m.set_defaults(func=c.cmd_metrics)

    w = sub.add_parser("web", help="run FastAPI web dashboard")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8000)
    w.set_defaults(func=c.cmd_web)

    wa = sub.add_parser("watch", help="live refresh + new-device alerts")
    wa.add_argument("--interval", type=int, default=10, help="poll seconds")
    wa.add_argument("--log", action="store_true", help="also record snapshots to SQLite")
    wa.add_argument("--no-alert", action="store_true", help="disable desktop notifications")
    wa.set_defaults(func=c.cmd_watch)

    sp = sub.add_parser("speedtest", help="run speedtest and log alongside router load")
    _add_json(sp)
    sp.set_defaults(func=c.cmd_speedtest)

    sub.add_parser("tray", help="system tray icon with client count").set_defaults(func=c.cmd_tray)

    # ----- aliases -----
    al = sub.add_parser("alias", help="manage MAC aliases")
    alsub = al.add_subparsers(dest="alias_cmd", required=True)
    a1 = alsub.add_parser("set"); a1.add_argument("mac"); a1.add_argument("name"); a1.set_defaults(func=c.cmd_alias_set)
    a2 = alsub.add_parser("rm"); a2.add_argument("mac"); a2.set_defaults(func=c.cmd_alias_remove)
    a3 = alsub.add_parser("list"); _add_json(a3); a3.set_defaults(func=c.cmd_alias_list)

    # ----- vendor + rdns -----
    vd = sub.add_parser("vendor", help="MAC OUI to vendor name"); vd.add_argument("mac"); vd.set_defaults(func=c.cmd_vendor)
    rd = sub.add_parser("rdns", help="reverse DNS lookup"); rd.add_argument("ip"); rd.set_defaults(func=c.cmd_rdns)

    # ----- public IP -----
    pi = sub.add_parser("public-ip", help="check + record router's public IP")
    _add_json(pi); pi.set_defaults(func=c.cmd_publicip)

    # ----- firmware update -----
    fc = sub.add_parser("firmware-check", help="compare to TP-Link's published firmware")
    fc.set_defaults(func=c.cmd_firmware_check)

    # ----- latency / ping -----
    la = sub.add_parser("latency", help="ping every router-known device")
    la.add_argument("--workers", type=int, default=16)
    la.add_argument("--timeout", type=float, default=1.5)
    _add_json(la); la.set_defaults(func=c.cmd_latency)

    pg = sub.add_parser("ping", help="ping a single host")
    pg.add_argument("target")
    pg.add_argument("--timeout", type=float, default=1.5)
    pg.set_defaults(func=c.cmd_ping)

    # ----- discovery -----
    ds = sub.add_parser("discover", help="mDNS + SSDP scan")
    ds.add_argument("--timeout", type=float, default=4.0)
    _add_json(ds); ds.set_defaults(func=c.cmd_discover)

    # ----- presence -----
    pr = sub.add_parser("presence", help="who from aliases is on the network right now")
    _add_json(pr); pr.set_defaults(func=c.cmd_presence)

    # ----- csv export -----
    cs = sub.add_parser("csv", help="export DB tables to CSV")
    cs.add_argument("what", choices=["snapshots", "devices"])
    cs.add_argument("out")
    cs.add_argument("--days", type=int, default=30)
    cs.set_defaults(func=c.cmd_csv)

    # ----- events -----
    ev = sub.add_parser("events", help="recent events (joins/leaves/IP changes)")
    ev.add_argument("--limit", type=int, default=50)
    _add_json(ev); ev.set_defaults(func=c.cmd_events)

    # ----- daemon -----
    dm = sub.add_parser("daemon", help="run combined snapshot+latency+publicip loops")
    dm.add_argument("--snap", type=int, default=60)
    dm.add_argument("--latency", type=int, default=120)
    dm.add_argument("--publicip", type=int, default=600)
    dm.add_argument("--extping", type=int, default=300)
    dm.add_argument("--anomaly", type=int, default=3600)
    dm.add_argument("--no-automation", dest="automation", action="store_false", default=True)
    dm.add_argument("--watchdog", action="store_true")
    dm.add_argument("--watchdog-interval", type=int, default=60)
    dm.add_argument("--watchdog-auto-reboot", action="store_true")
    dm.set_defaults(func=c.cmd_daemon)

    # ----- mqtt -----
    mq = sub.add_parser("mqtt", help="MQTT publisher (Home Assistant)")
    mq.add_argument("--discovery", action="store_true", help="publish HA auto-discovery")
    mq.add_argument("--state", action="store_true", help="publish one state update")
    mq.set_defaults(func=c.cmd_mqtt_publish)

    # ----- task scheduler -----
    sc = sub.add_parser("schedule", help="generate Windows Task Scheduler XML for `daemon`")
    sc.add_argument("--out", default="c6u_daemon.xml")
    sc.set_defaults(func=c.cmd_schedule)

    # ----- profiles -----
    pf = sub.add_parser("profiles", help="list multi-router profiles")
    pf.set_defaults(func=c.cmd_profile_list)

    # ===== new commands =====

    # push notifications
    nt = sub.add_parser("notify", help="send a push notification via configured providers")
    nt.add_argument("title")
    nt.add_argument("body", nargs="?", default="")
    nt.add_argument("--priority", type=int)
    nt.add_argument("--tags", nargs="*")
    nt.set_defaults(func=c.cmd_notify)

    # rules
    rl = sub.add_parser("rules", help="manage the rules engine")
    rlsub = rl.add_subparsers(dest="rules_cmd", required=True)
    rlsub.add_parser("list").set_defaults(func=c.cmd_rules_list)
    rlsub.add_parser("example").set_defaults(func=c.cmd_rules_example)
    rt = rlsub.add_parser("test", help="fire a synthetic event through the rules")
    rt.add_argument("kind")
    rt.add_argument("--mac"); rt.add_argument("--hostname"); rt.add_argument("--ip")
    rt.set_defaults(func=c.cmd_rules_test)

    # automation jobs
    au = sub.add_parser("automation", help="scheduled automation jobs")
    ausub = au.add_subparsers(dest="auto_cmd", required=True)
    ausub.add_parser("list").set_defaults(func=c.cmd_auto_list)
    ausub.add_parser("example").set_defaults(func=c.cmd_auto_example)
    ausub.add_parser("run", help="run scheduler in foreground").set_defaults(func=c.cmd_auto_run)

    # watchdog
    wd = sub.add_parser("watchdog", help="connectivity watchdog loop")
    wd.add_argument("--interval", type=int, default=60)
    wd.add_argument("--timeout", type=float, default=2.0)
    wd.add_argument("--fail-threshold", type=int, default=3)
    wd.add_argument("--auto-reboot", action="store_true")
    wd.set_defaults(func=c.cmd_watchdog)

    # rotate
    rt2 = sub.add_parser("rotate", help="generate a new admin password")
    rt2.add_argument("--try-apply", action="store_true", help="attempt to push via the router API")
    rt2sub = rt2.add_subparsers(dest="rotate_cmd")
    rt2sub.add_parser("history").set_defaults(func=c.cmd_rotate_history)
    rt2.set_defaults(func=c.cmd_rotate)

    # fingerprint
    fp = sub.add_parser("fingerprint", help="guess device types from vendor+mdns+ports")
    fp.add_argument("--scan-ports", action="store_true")
    _add_json(fp)
    fp.set_defaults(func=c.cmd_fingerprint)

    # heatmap
    hm = sub.add_parser("heatmap", help="per-device presence heatmap")
    hm.add_argument("--mac")
    hm.add_argument("--days", type=int, default=30)
    hm.add_argument("--top", type=int, default=20)
    _add_json(hm)
    hm.set_defaults(func=c.cmd_heatmap)

    # cve
    cv = sub.add_parser("cve", help="CVE watcher - query NVD for router model")
    _add_json(cv); cv.set_defaults(func=c.cmd_cve)

    # sla
    sla_p = sub.add_parser("sla", help="ISP SLA report based on recorded speedtests")
    sla_p.add_argument("--days", type=int, default=30)
    _add_json(sla_p); sla_p.set_defaults(func=c.cmd_sla)

    # extping
    ep = sub.add_parser("extping", help="ping external targets and record to DB")
    _add_json(ep); ep.set_defaults(func=c.cmd_extping)

    # telegram
    tg = sub.add_parser("telegram", help="run the Telegram bot (long-polling)")
    tg.set_defaults(func=c.cmd_telegram)

    # discord
    dc = sub.add_parser("discord", help="post a message via Discord webhook")
    dc.add_argument("text")
    dc.set_defaults(func=c.cmd_discord)

    # security
    ps = sub.add_parser("portscan", help="TCP port scan of your public IP (or --lan for every device on the network)")
    ps.add_argument("--lan", action="store_true", help="scan every router-known device instead of the public IP")
    ps.add_argument("--target", help="scan a single explicit IP")
    ps.add_argument("--timeout", type=float, default=None, help="per-port timeout seconds")
    ps.add_argument("--workers", type=int, default=None)
    _add_json(ps); ps.set_defaults(func=c.cmd_portscan)
    sub.add_parser("arpwatch", help="snapshot ARP table, flag conflicts").set_defaults(func=c.cmd_arpwatch)
    sub.add_parser("dnscheck", help="compare system DNS to DoH (Cloudflare/Google)").set_defaults(func=c.cmd_dnscheck)
    hb = sub.add_parser("hibp", help="Have I Been Pwned - password or email check")
    hb.add_argument("what", choices=["password", "email", "config"])
    hb.add_argument("value", nargs="?")
    hb.set_defaults(func=c.cmd_hibp)
    sub.add_parser("tlswatch", help="router TLS cert pin watcher").set_defaults(func=c.cmd_tlswatch)

    # textual TUI + REPL
    sub.add_parser("tui", help="full-screen Textual dashboard").set_defaults(func=c.cmd_tui)
    sub.add_parser("repl", help="interactive shell").set_defaults(func=c.cmd_repl)

    # SQL / FTS5 search
    sq = sub.add_parser("sql", help="run ad-hoc SQL against history DB")
    sq.add_argument("statement")
    sq.add_argument("--mutate", action="store_true", help="allow DROP/DELETE/UPDATE/INSERT")
    _add_json(sq); sq.set_defaults(func=c.cmd_sql)

    se = sub.add_parser("search", help="FTS5 search over event log")
    sesub = se.add_subparsers(dest="search_cmd", required=True)
    seq = sesub.add_parser("query"); seq.add_argument("q"); seq.add_argument("--limit", type=int, default=100)
    seq.set_defaults(func=c.cmd_search_query)
    sesub.add_parser("rebuild").set_defaults(func=c.cmd_search_rebuild)

    # digest
    dg = sub.add_parser("digest", help="write weekly HTML digest")
    dg.add_argument("--out", default="digest.html")
    dg.add_argument("--days", type=int, default=7)
    dg.set_defaults(func=c.cmd_digest)

    # backup / restore
    bk = sub.add_parser("backup", help="create a backup archive")
    bk.add_argument("--out")
    bk.set_defaults(func=c.cmd_backup)

    rs = sub.add_parser("restore", help="restore from a backup archive")
    rs.add_argument("archive")
    rs.add_argument("--overwrite", action="store_true")
    rs.set_defaults(func=c.cmd_restore)

    # anomaly
    an = sub.add_parser("anomaly", help="scan for anomalies in recent activity")
    an.add_argument("--baseline-days", type=int, default=14)
    an.add_argument("--recent-minutes", type=int, default=60)
    _add_json(an); an.set_defaults(func=c.cmd_anomaly)

    # parental
    pa = sub.add_parser("parental", help="parental-control schedule evaluator")
    pasub = pa.add_subparsers(dest="parental_cmd", required=True)
    pasub.add_parser("list").set_defaults(func=c.cmd_parental_list)
    pasub.add_parser("example").set_defaults(func=c.cmd_parental_example)
    paa = pasub.add_parser("apply"); paa.add_argument("--dry-run", action="store_true")
    paa.set_defaults(func=c.cmd_parental_apply)

    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if getattr(args, "profile", None):
        from . import config as _cfg
        _cfg.set_active_profile(args.profile)
    try:
        args.func(args)
    except KeyboardInterrupt:
        console.print("\n[red]Interrupted[/red]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        if getattr(args, "debug", False):
            raise
        sys.exit(1)
