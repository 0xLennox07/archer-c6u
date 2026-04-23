"""System tray icon. Shows client count and lets you reboot / open web UI / refresh."""
from __future__ import annotations

import threading
import time
import webbrowser

from PIL import Image, ImageDraw, ImageFont
from pystray import Icon, Menu, MenuItem

from .client import router


def _make_icon(text: str) -> Image.Image:
    img = Image.new("RGB", (64, 64), (20, 20, 28))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", 36)
    except OSError:
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((64 - w) / 2 - bbox[0], (64 - h) / 2 - bbox[1]), text, fill=(170, 220, 255), font=font)
    return img


def run(web_url: str = "http://127.0.0.1:8000") -> None:
    state = {"count": "?", "down": False}
    icon = Icon("c6u", _make_icon("?"), "c6u router")

    def poll():
        while True:
            try:
                with router() as r:
                    s = r.get_status()
                state["count"] = str(s.clients_total)
                state["down"] = False
            except Exception:
                state["count"] = "!"
                state["down"] = True
            icon.icon = _make_icon(state["count"])
            icon.title = f"c6u — {state['count']} clients" + (" (unreachable)" if state["down"] else "")
            time.sleep(15)

    def on_open_web(_ic, _item):
        webbrowser.open(web_url)

    def on_reboot(_ic, _item):
        try:
            with router() as r:
                r.reboot()
        except Exception:
            pass

    def on_quit(ic, _item):
        ic.stop()

    icon.menu = Menu(
        MenuItem(lambda _: f"Clients: {state['count']}", None, enabled=False),
        Menu.SEPARATOR,
        MenuItem("Open web UI", on_open_web),
        MenuItem("Reboot router", on_reboot),
        Menu.SEPARATOR,
        MenuItem("Quit", on_quit),
    )

    threading.Thread(target=poll, daemon=True).start()
    icon.run()
