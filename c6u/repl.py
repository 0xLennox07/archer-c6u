"""Interactive shell (REPL) using cmd.Cmd.

Runs any c6u CLI subcommand. Type `help` for the full list.
"""
from __future__ import annotations

import cmd
import shlex

from rich.console import Console

console = Console()


class C6UShell(cmd.Cmd):
    intro = "c6u interactive shell — type `help` or `exit`."
    prompt = "c6u> "

    def do_exit(self, _arg):
        """exit the shell."""
        return True
    do_quit = do_EOF = do_exit

    def default(self, line: str):
        from .cli import build_parser
        parser = build_parser()
        try:
            argv = shlex.split(line)
        except ValueError as e:
            console.print(f"[red]{e}[/red]"); return
        if not argv:
            return
        try:
            ns = parser.parse_args(argv)
            ns.func(ns)
        except SystemExit:
            pass
        except Exception as e:
            console.print(f"[red]{e}[/red]")

    def emptyline(self):
        pass


def run() -> None:
    try:
        import readline  # noqa: F401  (just to enable history+arrow keys if present)
    except ImportError:
        pass
    C6UShell().cmdloop()
