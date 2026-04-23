"""Rich rendering + JSON serialization for router data."""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import timedelta

from rich.panel import Panel
from rich.table import Table
from tplinkrouterc6u import Connection

from . import aliases as _aliases
from . import vendor as _vendor


def fmt_uptime(seconds) -> str:
    if not seconds:
        return "-"
    return str(timedelta(seconds=int(seconds)))


def fmt_bool(v) -> str:
    if v is None:
        return "-"
    return "[green]on[/green]" if v else "[red]off[/red]"


def fmt_bps(v) -> str:
    if not v:
        return "-"
    v = float(v)
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if v < 1024:
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB/s"


def fmt_bytes(v) -> str:
    if not v:
        return "-"
    v = float(v)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024:
            return f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} PB"


def _pct(v) -> str:
    return f"{v * 100:.0f}%" if v is not None else "-"


def status_table(status) -> Table:
    t = Table(title="Router Status", show_header=False, title_style="bold cyan")
    t.add_column("Field", style="bold")
    t.add_column("Value")
    for k, v in [
        ("Connection type", status.conn_type or "-"),
        ("WAN IPv4", str(status.wan_ipv4_address) if status.wan_ipv4_address else "-"),
        ("WAN Gateway", str(status.wan_ipv4_gateway_address) if status.wan_ipv4_gateway_address else "-"),
        ("WAN MAC", str(status.wan_macaddress) if status.wan_macaddress else "-"),
        ("WAN uptime", fmt_uptime(status.wan_ipv4_uptime)),
        ("LAN IPv4", str(status.lan_ipv4_address) if status.lan_ipv4_address else "-"),
        ("LAN MAC", str(status.lan_macaddress) if status.lan_macaddress else "-"),
        ("CPU", _pct(status.cpu_usage)),
        ("Memory", _pct(status.mem_usage)),
        ("Clients total", str(status.clients_total)),
        ("  wired", str(status.wired_total)),
        ("  wifi", str(status.wifi_clients_total)),
        ("  guest", str(status.guest_clients_total)),
        ("WiFi 2.4G", fmt_bool(status.wifi_2g_enable)),
        ("WiFi 5G", fmt_bool(status.wifi_5g_enable)),
        ("Guest 2.4G", fmt_bool(status.guest_2g_enable)),
        ("Guest 5G", fmt_bool(status.guest_5g_enable)),
    ]:
        t.add_row(k, v)
    return t


def clients_table(status) -> Table:
    t = Table(title=f"Connected Devices ({len(status.devices)})", title_style="bold cyan")
    for col in ("Name", "Hostname", "IP", "MAC", "Vendor", "Type", "Down", "Up", "Usage", "Online", "Active"):
        t.add_column(col)
    aliases = _aliases.load()
    for d in status.devices:
        mac = str(d.macaddress) if d.macaddress else ""
        alias = aliases.get(mac.upper().replace("-", ":"), "")
        t.add_row(
            f"[bold]{alias}[/bold]" if alias else "-",
            d.hostname or "-",
            str(d.ipaddress) if d.ipaddress else "-",
            mac or "-",
            _vendor.vendor(mac) or "-",
            d.type.name if isinstance(d.type, Connection) else str(d.type),
            fmt_bps(d.down_speed),
            fmt_bps(d.up_speed),
            fmt_bytes(d.traffic_usage),
            fmt_uptime(int(d.online_time) if d.online_time else None),
            fmt_bool(d.active),
        )
    return t


def wan_table(ipv4) -> Table:
    t = Table(title="WAN / LAN (IPv4)", show_header=False, title_style="bold cyan")
    t.add_column("Field", style="bold")
    t.add_column("Value")
    for k, v in [
        ("WAN conn type", ipv4.wan_ipv4_conntype or "-"),
        ("WAN IP", str(ipv4.wan_ipv4_ipaddress) if ipv4.wan_ipv4_ipaddress else "-"),
        ("WAN netmask", str(ipv4.wan_ipv4_netmask_address) if ipv4.wan_ipv4_netmask_address else "-"),
        ("WAN gateway", str(ipv4.wan_ipv4_gateway_address) if ipv4.wan_ipv4_gateway_address else "-"),
        ("WAN DNS 1", str(ipv4.wan_ipv4_pridns_address) if ipv4.wan_ipv4_pridns_address else "-"),
        ("WAN DNS 2", str(ipv4.wan_ipv4_snddns_address) if ipv4.wan_ipv4_snddns_address else "-"),
        ("WAN MAC", str(ipv4.wan_macaddress) if ipv4.wan_macaddress else "-"),
        ("LAN IP", str(ipv4.lan_ipv4_ipaddress) if ipv4.lan_ipv4_ipaddress else "-"),
        ("LAN netmask", str(ipv4.lan_ipv4_netmask_address) if ipv4.lan_ipv4_netmask_address else "-"),
        ("LAN MAC", str(ipv4.lan_macaddress) if ipv4.lan_macaddress else "-"),
        ("DHCP enabled", fmt_bool(ipv4.lan_ipv4_dhcp_enable)),
        ("Remote mgmt", fmt_bool(ipv4.remote)),
    ]:
        t.add_row(k, v)
    return t


def firmware_panel(fw) -> Panel:
    body = (
        f"[bold]Model:[/bold] {fw.model}\n"
        f"[bold]Hardware:[/bold] {fw.hardware_version}\n"
        f"[bold]Firmware:[/bold] {fw.firmware_version}"
    )
    return Panel(body, title="Firmware", title_align="left", border_style="cyan")


def wifi_table(status) -> Table:
    t = Table(title="WiFi Radios", title_style="bold cyan")
    for col in ("Band", "Host", "Guest", "IoT"):
        t.add_column(col)
    for band in ("2g", "5g", "6g"):
        host = getattr(status, f"wifi_{band}_enable", None)
        guest = getattr(status, f"guest_{band}_enable", None)
        iot = getattr(status, f"iot_{band}_enable", None)
        if host is None and guest is None and iot is None:
            continue
        t.add_row(band.upper(), fmt_bool(host), fmt_bool(guest), fmt_bool(iot))
    return t


def dhcp_leases_table(leases) -> Table:
    t = Table(title=f"DHCP Leases ({len(leases)})", title_style="bold cyan")
    for col in ("Hostname", "IP", "MAC", "Lease time"):
        t.add_column(col)
    for lease in leases:
        t.add_row(
            lease.hostname or "-",
            str(lease.ipaddress) if lease.ipaddress else "-",
            str(lease.macaddress) if lease.macaddress else "-",
            lease.lease_time or "-",
        )
    return t


def reservations_table(reservations) -> Table:
    t = Table(title=f"IP Reservations ({len(reservations)})", title_style="bold cyan")
    for col in ("Hostname", "IP", "MAC", "Enabled"):
        t.add_column(col)
    for r in reservations:
        t.add_row(
            r.hostname or "-",
            str(r.ipaddress) if r.ipaddress else "-",
            str(r.macaddress) if r.macaddress else "-",
            fmt_bool(r.enabled),
        )
    return t


def _obj_to_dict(obj):
    """Best-effort JSON serialization for library dataclasses."""
    if is_dataclass(obj):
        return _obj_to_dict(asdict(obj))
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.startswith("_"):
                k = k[1:]
            out[k] = _obj_to_dict(v)
        return out
    if isinstance(obj, list):
        return [_obj_to_dict(x) for x in obj]
    if isinstance(obj, Connection):
        return obj.name
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    return str(obj)


def to_json(obj):
    return _obj_to_dict(obj)


def enrich_devices_json(devices) -> list[dict]:
    """List of devices as JSON dicts, with alias + vendor added."""
    aliases = _aliases.load()
    out = []
    for d in devices:
        d_dict = to_json(d)
        mac = (d_dict.get("macaddr") or "").upper().replace("-", ":")
        d_dict["alias"] = aliases.get(mac, None)
        d_dict["vendor"] = _vendor.vendor(mac) or None
        out.append(d_dict)
    return out
