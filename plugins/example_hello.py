"""Example plugin — adds a `c6u hello` command and a /api/hello route.

Delete or edit as you like. Files in plugins/ starting with `_` are ignored.
"""
from __future__ import annotations


def register_cli(sub) -> None:
    p = sub.add_parser("hello", help="example plugin command")
    p.add_argument("name", nargs="?", default="world")
    p.set_defaults(func=lambda args: print(f"hi, {args.name}!"))


def register_web(app) -> None:
    @app.get("/api/hello")
    def _hello(name: str = "world"):
        return {"hello": name, "from": "plugin"}


def register_rule_actions(actions: dict) -> None:
    def _log(spec, event, _cfg):
        print(f"[plugin rule] {spec}  event={event}")
    actions.setdefault("log_to_stdout", _log)
