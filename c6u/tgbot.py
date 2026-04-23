"""Telegram bot — long-polling, command-driven.

Config (config.json):
    "telegram": {
      "token": "123456:ABC...",
      "allowed_chats": [12345678]   // ints; users/chats that may issue commands
    }

Supported commands:
    /status     router CPU/mem/clients summary
    /clients    list of currently-connected devices (names + vendor)
    /presence   who is home, who isn't
    /public_ip  current WAN IP
    /speedtest  kick off a speedtest (takes ~30s)
    /reboot     reboot the router (requires `confirm`)
    /events N   last N events
    /help       list commands
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import aliases as aliases_mod
from . import config as cfg_mod
from . import db as db_mod
from . import presence as presence_mod
from . import publicip as publicip_mod
from . import vendor as vendor_mod
from .client import router

log = logging.getLogger(__name__)
API = "https://api.telegram.org/bot{token}/{method}"


def _api(token: str, method: str, **params) -> dict:
    r = requests.get(API.format(token=token, method=method),
                     params=params, timeout=40)
    return r.json()


def send(token: str, chat_id: int, text: str, markdown: bool = False) -> None:
    _api(token, "sendMessage", chat_id=chat_id, text=text[:4090],
         parse_mode="Markdown" if markdown else None)


# ----- command handlers -----

def _cmd_status(_args) -> str:
    with router() as r:
        s = r.get_status()
    return (
        f"*CPU* {s.cpu_usage*100:.0f}%  *mem* {s.mem_usage*100:.0f}%\n"
        f"*clients* {s.clients_total} (wired {s.wired_total}, wifi {s.wifi_clients_total}, guest {s.guest_clients_total})\n"
        f"*WAN IP* `{s.wan_ipv4_address}`"
    )


def _cmd_clients(_args) -> str:
    with router() as r:
        s = r.get_status()
    aliases = aliases_mod.load()
    lines = [f"*{len(s.devices)} clients*"]
    for d in s.devices:
        mac = (str(d.macaddress) or "").upper()
        name = aliases.get(mac) or (d.hostname or "(unnamed)")
        v = vendor_mod.vendor(mac) or ""
        lines.append(f"• `{mac}` {name} ({v})")
    return "\n".join(lines)[:3500]


def _cmd_presence(_args) -> str:
    p = presence_mod.who_is_present()
    lines = [f"*Present* ({len(p['present'])})"]
    for x in p["present"]:
        lines.append(f"✅ {x.get('name') or x.get('hostname') or x['mac']}")
    lines.append(f"\n*Absent* ({len(p['absent'])})")
    for x in p["absent"]:
        lines.append(f"❌ {x['name']}")
    return "\n".join(lines)


def _cmd_publicip(_args) -> str:
    r = publicip_mod.check_and_record()
    ip = r.get("ip")
    if not ip:
        return "could not fetch"
    if r.get("changed"):
        return f"*{ip}* (changed from `{r['previous']}`)"
    return f"*{ip}*"


def _cmd_speedtest(_args) -> str:
    from . import speedtest_cmd
    r = speedtest_cmd.run_and_record()
    return (
        f"↓ {r['down_mbps']:.1f} Mbps  ↑ {r['up_mbps']:.1f} Mbps  ping {r['ping_ms']:.0f} ms\n"
        f"server: {r['server']}"
    )


def _cmd_reboot(args) -> str:
    if (args or [""])[0].lower() != "confirm":
        return "Type `/reboot confirm` to actually reboot."
    with router() as r:
        r.reboot()
    return "reboot command sent."


def _cmd_events(args) -> str:
    n = 10
    if args:
        try:
            n = max(1, min(30, int(args[0])))
        except ValueError:
            pass
    rows = db_mod.recent_events(limit=n)
    import datetime
    lines = [f"*last {len(rows)} events*"]
    for r in rows:
        when = datetime.datetime.fromtimestamp(r['ts']).strftime("%m-%d %H:%M")
        lines.append(f"{when} `{r['kind']}` {r.get('mac') or ''}")
    return "\n".join(lines)


def _cmd_help(_args) -> str:
    return (
        "/status /clients /presence /public_ip\n"
        "/speedtest  /events [N]\n"
        "/reboot confirm"
    )


HANDLERS = {
    "/status": _cmd_status, "/clients": _cmd_clients,
    "/presence": _cmd_presence, "/public_ip": _cmd_publicip,
    "/speedtest": _cmd_speedtest, "/reboot": _cmd_reboot,
    "/events": _cmd_events, "/help": _cmd_help, "/start": _cmd_help,
}


def run_polling(poll_timeout: int = 25) -> None:
    cfg = cfg_mod.load_config(interactive=False)
    tg = cfg.get("telegram") or {}
    token = tg.get("token")
    allowed = set(tg.get("allowed_chats") or [])
    if not token:
        raise RuntimeError("config.json -> telegram.token missing")
    offset = 0
    log.info("telegram bot started (allowed=%s)", allowed)
    while True:
        try:
            data = _api(token, "getUpdates", offset=offset, timeout=poll_timeout)
            for upd in data.get("result", []) or []:
                offset = upd["update_id"] + 1
                msg: dict[str, Any] = upd.get("message") or {}
                chat_id = (msg.get("chat") or {}).get("id")
                text = (msg.get("text") or "").strip()
                if not (chat_id and text):
                    continue
                if allowed and chat_id not in allowed:
                    send(token, chat_id, "not authorized.")
                    continue
                parts = text.split()
                cmd = parts[0].split("@")[0].lower()
                args = parts[1:]
                handler = HANDLERS.get(cmd)
                if not handler:
                    send(token, chat_id, _cmd_help(None), markdown=True)
                    continue
                try:
                    reply = handler(args)
                except Exception as e:
                    reply = f"error: {e}"
                send(token, chat_id, reply, markdown=True)
        except Exception as e:
            log.warning("telegram poll failed: %s", e)
            time.sleep(5)
