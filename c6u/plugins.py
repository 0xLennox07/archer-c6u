"""Plugin system.

Drop any `.py` file into `plugins/` at the repo root. On startup, every such
file is imported and its optional hooks are registered:

    # plugins/my_plugin.py
    def register_cli(sub):
        p = sub.add_parser("hello")
        p.set_defaults(func=lambda args: print("hi from my plugin"))

    def register_rule_actions(actions):
        # actions is c6u.rules.ACTIONS
        actions["slack_msg"] = lambda spec, event, cfg: ...

    def register_web(app):
        @app.get("/api/hello")
        def _hello(): return {"hello": "world"}

    def register_daemon_loop(add_loop, stop):
        # add_loop(interval_s, func, name) — called by daemon
        add_loop(120, lambda: print("tick"), "my-tick")

Any of those four entrypoints is optional.
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

from . import config as cfg_mod

log = logging.getLogger(__name__)

PLUGINS_DIR = cfg_mod.ROOT / "plugins"
_LOADED: dict[str, object] = {}


def discover() -> list[Path]:
    if not PLUGINS_DIR.exists():
        return []
    out: list[Path] = []
    for p in sorted(PLUGINS_DIR.glob("*.py")):
        if p.name.startswith("_"):
            continue
        out.append(p)
    return out


def _load_module(path: Path):
    mod_name = f"c6u_plugin_{path.stem}"
    if mod_name in _LOADED:
        return _LOADED[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[attr-defined]
    except Exception as e:
        log.warning("plugin %s failed to import: %s", path.name, e)
        return None
    _LOADED[mod_name] = mod
    return mod


def load_all() -> list[object]:
    mods: list[object] = []
    for path in discover():
        mod = _load_module(path)
        if mod is not None:
            mods.append(mod)
    return mods


def register_cli(sub) -> list[str]:
    """Called from cli.build_parser(). Invokes register_cli(sub) in every plugin."""
    names: list[str] = []
    for mod in load_all():
        fn = getattr(mod, "register_cli", None)
        if callable(fn):
            try:
                fn(sub)
                names.append(getattr(mod, "__name__", "?"))
            except Exception as e:
                log.warning("plugin register_cli failed: %s", e)
    return names


def register_rule_actions(actions: dict) -> list[str]:
    names: list[str] = []
    for mod in load_all():
        fn = getattr(mod, "register_rule_actions", None)
        if callable(fn):
            try:
                fn(actions)
                names.append(getattr(mod, "__name__", "?"))
            except Exception as e:
                log.warning("plugin register_rule_actions failed: %s", e)
    return names


def register_web(app) -> list[str]:
    names: list[str] = []
    for mod in load_all():
        fn = getattr(mod, "register_web", None)
        if callable(fn):
            try:
                fn(app)
                names.append(getattr(mod, "__name__", "?"))
            except Exception as e:
                log.warning("plugin register_web failed: %s", e)
    return names


def register_daemon_loops(add_loop, stop) -> list[str]:
    names: list[str] = []
    for mod in load_all():
        fn = getattr(mod, "register_daemon_loop", None)
        if callable(fn):
            try:
                fn(add_loop, stop)
                names.append(getattr(mod, "__name__", "?"))
            except Exception as e:
                log.warning("plugin register_daemon_loop failed: %s", e)
    return names


def info() -> list[dict]:
    out = []
    for path in discover():
        mod = _load_module(path)
        out.append({
            "file": path.name,
            "name": getattr(mod, "__name__", None) if mod else None,
            "doc": (getattr(mod, "__doc__", "") or "").strip().splitlines()[0] if mod else "",
            "hooks": [h for h in ("register_cli", "register_rule_actions",
                                   "register_web", "register_daemon_loop")
                      if mod and callable(getattr(mod, h, None))],
        })
    return out
