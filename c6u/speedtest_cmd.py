"""Speedtest correlator — run Ookla speedtest, stamp with router load."""
from __future__ import annotations

from .client import router
from .db import record_speedtest


def run_and_record() -> dict:
    import speedtest

    st = speedtest.Speedtest(secure=True)
    st.get_best_server()
    down = st.download() / 1_000_000
    up = st.upload() / 1_000_000
    ping = st.results.ping
    server = f"{st.results.server.get('sponsor', '?')} ({st.results.server.get('name', '?')})"

    try:
        with router() as r:
            s = r.get_status()
            cpu = s.cpu_usage
            mem = s.mem_usage
            clients = s.clients_total
    except Exception:
        cpu = mem = clients = None

    result = {
        "down_mbps": down,
        "up_mbps": up,
        "ping_ms": ping,
        "server": server,
        "cpu": cpu,
        "mem": mem,
        "clients": clients,
    }
    record_speedtest(result)
    return result
