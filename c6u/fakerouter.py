"""Simulation mode — fake router client for offline development / testing.

Enable by setting env `C6U_FAKE=1` OR passing `--fake` on the CLI. Everything
that uses `client.router()` gets a recorded-response stub instead of an actual
HTTP login, which means the entire stack (daemon, web, metrics, tests) can run
without a router on the LAN.
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from enum import Enum


class Connection(Enum):
    WIRED = "WIRED"
    HOST_2G = "HOST_2G"
    HOST_5G = "HOST_5G"
    HOST_6G = "HOST_6G"
    GUEST_2G = "GUEST_2G"
    GUEST_5G = "GUEST_5G"
    GUEST_6G = "GUEST_6G"
    IOT_2G = "IOT_2G"
    IOT_5G = "IOT_5G"
    IOT_6G = "IOT_6G"


@dataclass
class Device:
    macaddress: str
    hostname: str
    ipaddress: str
    type: Connection
    down_speed: int | None = 0
    up_speed: int | None = 0
    traffic_usage: int | None = 0
    online_time: int | None = 0
    active: bool = True


@dataclass
class Status:
    cpu_usage: float = 0.18
    mem_usage: float = 0.42
    wan_ipv4_address: str | None = "203.0.113.10"
    wan_ipv4_uptime: int = 123456
    lan_ipv4_addr: str = "192.168.0.1"
    clients_total: int = 0
    wired_total: int = 0
    wifi_clients_total: int = 0
    guest_clients_total: int = 0
    conn_type: str | None = "DHCP"
    wifi_2g_enable: bool = True
    wifi_5g_enable: bool = True
    wifi_6g_enable: bool = False
    guest_2g_enable: bool = False
    guest_5g_enable: bool = False
    iot_2g_enable: bool = False
    iot_5g_enable: bool = False
    devices: list[Device] = field(default_factory=list)


@dataclass
class IPv4Status:
    wan_ipv4_conntype: str = "DHCP"
    wan_ipv4_ipaddr: str = "203.0.113.10"
    wan_ipv4_gateway: str = "203.0.113.1"
    wan_ipv4_netmask: str = "255.255.255.0"
    wan_ipv4_pridns: str = "1.1.1.1"
    wan_ipv4_snddns: str = "8.8.8.8"
    wan_macaddr: str = "AA:BB:CC:DD:EE:FF"
    lan_ipv4_ipaddr: str = "192.168.0.1"
    lan_macaddr: str = "AA:BB:CC:DD:EE:FE"
    lan_ipv4_dhcp_enable: bool = True
    remote: bool = False


@dataclass
class Firmware:
    model: str = "Archer C6U"
    hardware_version: str = "V1.0"
    firmware_version: str = "1.4.0 Build 20240101 Rel.00000"


FIXTURE_DEVICES = [
    Device("AA:BB:CC:00:00:01", "work-laptop", "192.168.0.20", Connection.WIRED,  3_000_000, 200_000, 1_200_000_000, 86400),
    Device("AA:BB:CC:00:00:02", "iPhone-Bob",  "192.168.0.21", Connection.HOST_5G,  500_000,  80_000,   200_000_000, 43200),
    Device("AA:BB:CC:00:00:03", "Samsung-TV",  "192.168.0.22", Connection.HOST_5G, 2_500_000,  50_000,   800_000_000, 21600),
    Device("AA:BB:CC:00:00:04", "HP-Printer",  "192.168.0.23", Connection.HOST_2G,        0,       0,           0, 14400),
    Device("AA:BB:CC:00:00:05", "Chromecast",  "192.168.0.24", Connection.HOST_5G,   900_000,  30_000,   100_000_000, 7200),
    Device("AA:BB:CC:00:00:06", "RPi-NAS",     "192.168.0.25", Connection.WIRED,   200_000, 1_500_000, 400_000_000, 86400),
]


class FakeRouter:
    def __init__(self) -> None:
        self._authorized = False

    def authorize(self) -> None:
        self._authorized = True

    def logout(self) -> None:
        self._authorized = False

    def get_status(self) -> Status:
        devs = list(FIXTURE_DEVICES)
        wifi = sum(1 for d in devs if d.type.name.startswith("HOST_") and d.type != Connection.WIRED)
        wired = sum(1 for d in devs if d.type == Connection.WIRED)
        guest = sum(1 for d in devs if d.type.name.startswith("GUEST_"))
        # Jitter load a bit so graphs look alive.
        now = int(time.time())
        random.seed(now // 30)
        return Status(
            cpu_usage=min(0.98, max(0.02, 0.15 + random.random() * 0.2)),
            mem_usage=min(0.98, max(0.02, 0.40 + random.random() * 0.15)),
            clients_total=len(devs), wired_total=wired,
            wifi_clients_total=wifi, guest_clients_total=guest,
            devices=devs,
        )

    def get_ipv4_status(self) -> IPv4Status:
        return IPv4Status()

    def get_firmware(self) -> Firmware:
        return Firmware()

    def get_ipv4_dhcp_leases(self) -> list:
        return []

    def get_ipv4_reservations(self) -> list:
        return []

    def reboot(self) -> None:
        # no-op
        pass

    def set_wifi(self, _conn, _enable: bool) -> None:
        pass


def is_enabled() -> bool:
    return os.environ.get("C6U_FAKE", "").lower() in ("1", "true", "yes")


def enable() -> None:
    os.environ["C6U_FAKE"] = "1"


def disable() -> None:
    os.environ.pop("C6U_FAKE", None)
