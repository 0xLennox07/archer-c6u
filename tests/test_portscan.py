"""LAN port scan — exercise the scan_host / risky filter without real sockets."""
from unittest.mock import patch

from c6u import portscan


def test_risky_findings_filters_correctly():
    result = {
        "devices": [
            {"mac": "A", "hostname": "laptop", "ip": "10.0.0.2", "open": [22, 80]},   # risky (22)
            {"mac": "B", "hostname": "printer", "ip": "10.0.0.3", "open": [631, 9100]},  # safe
            {"mac": "C", "hostname": "nas", "ip": "10.0.0.4", "open": [445, 5000]},    # risky (445)
            {"mac": "D", "hostname": "phone", "ip": "10.0.0.5", "open": []},           # nothing open
        ]
    }
    risky = portscan.risky_findings(result)
    ips = {r["ip"] for r in risky}
    assert ips == {"10.0.0.2", "10.0.0.4"}


def test_scan_host_mocked():
    """Mock socket.create_connection: only :22 and :80 "accept" on the IP."""
    open_targets = {("10.0.0.99", 22), ("10.0.0.99", 80)}

    class _FakeSock:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _fake_conn(addr, timeout=None):
        if tuple(addr) in open_targets:
            return _FakeSock()
        raise ConnectionRefusedError("nope")

    with patch("c6u.portscan.socket.create_connection", side_effect=_fake_conn):
        open_ports = portscan.scan_host("10.0.0.99", ports=(22, 80, 443, 3389), timeout=0.1)
    assert open_ports == [22, 80]
