"""DB round-trip with mocked Status/Device shaped objects."""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from c6u import db


@dataclass
class FakeDevice:
    macaddress: str
    hostname: str
    ipaddress: str
    type: SimpleNamespace
    down_speed: int | None
    up_speed: int | None
    traffic_usage: int | None
    online_time: float | None
    active: bool


def _make_status():
    return SimpleNamespace(
        cpu_usage=0.25,
        mem_usage=0.50,
        wan_ipv4_address="1.2.3.4",
        wan_ipv4_uptime=1000,
        clients_total=2,
        wired_total=1,
        wifi_clients_total=1,
        guest_clients_total=0,
        devices=[
            FakeDevice("AA:BB:CC:DD:EE:01", "alice", "192.168.0.10",
                       SimpleNamespace(name="WIRED"), 100, 50, 1024, 120.0, True),
            FakeDevice("AA:BB:CC:DD:EE:02", "bob",   "192.168.0.11",
                       SimpleNamespace(name="HOST_5G"), 200, 75, 2048, 240.0, True),
        ],
    )


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    path = tmp_path / "test.sqlite3"
    monkeypatch.setattr(db, "DB_PATH", path)
    return path


def test_record_snapshot_persists_devices(tmp_db):
    ts = db.record_snapshot(_make_status())
    assert ts > 0
    with db.connect(tmp_db) as conn:
        rows = conn.execute("SELECT hostname FROM device_sample ORDER BY hostname").fetchall()
    assert [r["hostname"] for r in rows] == ["alice", "bob"]


def test_report_summarizes(tmp_db):
    db.record_snapshot(_make_status())
    rep = db.report(days=1)
    assert rep["snapshots"] == 1
    assert rep["peak_clients"] == 2
    assert len(rep["devices"]) == 2


def test_record_speedtest(tmp_db):
    db.record_speedtest({
        "down_mbps": 123.4, "up_mbps": 45.6, "ping_ms": 7.8,
        "server": "test", "cpu": 0.1, "mem": 0.2, "clients": 3,
    })
    rep = db.report(days=1)
    assert rep["speedtest_count"] == 1
    assert abs(rep["speedtest_avg_down"] - 123.4) < 1e-6
