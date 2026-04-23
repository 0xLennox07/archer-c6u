"""Weekly (or N-day) HTML digest — summary report of recent activity."""
from __future__ import annotations

import datetime as dt
import html
from pathlib import Path

from . import aliases as aliases_mod
from . import db as db_mod


DIGEST_CSS = """
body { font: 14px/1.5 system-ui, sans-serif; margin:0; padding:24px; background:#111; color:#eee; max-width:900px; margin:auto; }
h1 { margin:0 0 4px; font-size:24px; }
h2 { margin-top:28px; font-size:15px; text-transform:uppercase; letter-spacing:.04em; color:#8aa; border-bottom:1px solid #333; padding-bottom:6px; }
table { border-collapse:collapse; width:100%; font-size:13px; margin-top:8px; }
th,td { padding:6px 8px; text-align:left; border-bottom:1px solid #333; }
th { color:#8aa; }
.card { background:#1b1b1b; border:1px solid #333; border-radius:8px; padding:16px; margin-top:10px; }
.pill { display:inline-block; padding:3px 10px; border-radius:10px; background:#233; font-size:12px; color:#8cf; }
.mute { color:#888; }
.metric { display:inline-block; padding:12px 20px; background:#1b1b1b; border:1px solid #333; border-radius:8px; margin-right:10px; }
.metric b { font-size:22px; display:block; }
"""


def _fmt(bytes_: int | None) -> str:
    if not bytes_:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(bytes_)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}"


def build(days: int = 7) -> str:
    rpt = db_mod.report(days=days)
    aliases = aliases_mod.load()
    # Events grouped by kind.
    with db_mod.connect() as conn:
        ev_by_kind = conn.execute(
            "SELECT kind, COUNT(*) as n FROM event WHERE ts >= strftime('%s','now') - ?*86400 "
            "GROUP BY kind ORDER BY n DESC", (days,)
        ).fetchall()
        recent = conn.execute(
            "SELECT ts,kind,mac,payload FROM event ORDER BY ts DESC LIMIT 30"
        ).fetchall()
    parts: list[str] = []
    parts.append(f"<!doctype html><meta charset=utf-8><title>c6u digest ({days}d)</title>")
    parts.append(f"<style>{DIGEST_CSS}</style>")
    parts.append(f"<h1>c6u digest</h1><p class=mute>last {days} days — {dt.datetime.now():%Y-%m-%d %H:%M}</p>")

    # Summary metrics.
    parts.append("<div>")
    parts.append(f"<div class=metric><b>{rpt['snapshots']}</b>snapshots</div>")
    parts.append(f"<div class=metric><b>{rpt.get('peak_clients') or 0}</b>peak clients</div>")
    if rpt.get("avg_cpu") is not None:
        parts.append(f"<div class=metric><b>{rpt['avg_cpu']*100:.0f}%</b>avg CPU</div>")
    if rpt.get("avg_mem") is not None:
        parts.append(f"<div class=metric><b>{rpt['avg_mem']*100:.0f}%</b>avg mem</div>")
    if rpt.get("speedtest_count"):
        parts.append(f"<div class=metric><b>{rpt['speedtest_avg_down']:.0f}</b>avg ↓ Mbps</div>")
        parts.append(f"<div class=metric><b>{rpt['speedtest_avg_up']:.0f}</b>avg ↑ Mbps</div>")
    parts.append("</div>")

    parts.append("<h2>Top devices by traffic usage</h2><table><tr><th>Name</th><th>Hostname</th><th>IP</th><th>Max usage</th><th>Samples</th></tr>")
    for d in rpt["devices"][:15]:
        name = aliases.get((d["mac"] or "").upper(), "-")
        parts.append(
            f"<tr><td>{html.escape(name)}</td>"
            f"<td>{html.escape(d['hostname'] or '-')}</td>"
            f"<td>{html.escape(d['ip'] or '-')}</td>"
            f"<td>{_fmt(d['max_usage'])}</td>"
            f"<td>{d['samples']}</td></tr>"
        )
    parts.append("</table>")

    if ev_by_kind:
        parts.append("<h2>Events by kind</h2><table><tr><th>Kind</th><th>Count</th></tr>")
        for r in ev_by_kind:
            parts.append(f"<tr><td>{html.escape(r['kind'] or '')}</td><td>{r['n']}</td></tr>")
        parts.append("</table>")

    if recent:
        parts.append("<h2>Most recent events</h2><table><tr><th>When</th><th>Kind</th><th>MAC</th><th>Payload</th></tr>")
        for r in recent:
            when = dt.datetime.fromtimestamp(r["ts"]).strftime("%Y-%m-%d %H:%M")
            parts.append(
                f"<tr><td>{when}</td><td>{html.escape(r['kind'] or '')}</td>"
                f"<td class=mono>{html.escape(r['mac'] or '-')}</td>"
                f"<td class=mono>{html.escape((r['payload'] or '')[:140])}</td></tr>"
            )
        parts.append("</table>")
    return "".join(parts)


def write(path: str | Path, days: int = 7) -> Path:
    p = Path(path)
    p.write_text(build(days=days), encoding="utf-8")
    return p
