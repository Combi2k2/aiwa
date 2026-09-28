"""Command line: parses arguments and dispatches to `aiwa.commands`."""

from __future__ import annotations

import argparse

from dotenv import load_dotenv

from aiwa import config as config_mod
from aiwa.core.events import Category


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiwa", description="AI watcher")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("start", help="run the daemon (tray app) in the foreground")
    check = sub.add_parser("check", help="show recent activity with categories, and findings")
    check.add_argument("--all", action="store_true", help="list every segment, not just the last 15")
    focus = sub.add_parser("focus", help="focus intensity now and over the last hour, or for a past day")
    focus.add_argument("--span", type=int, default=60, help="minutes of history to chart (default 60)")
    focus.add_argument("--date", help="replay a whole day hour by hour, e.g. 2026-09-28")
    categorize = sub.add_parser("categorize", help="list remembered categories, or set one")
    categorize.add_argument("key", nargs="?", help='an app like "Slack", or a website domain like "github.com"')
    categorize.add_argument("category", nargs="?", choices=[c.value for c in Category])
    track = sub.add_parser("track", help="list tracked apps, or track one")
    track.add_argument("app", nargs="?")
    untrack = sub.add_parser("untrack", help="stop tracking an app added with `track` or a popup")
    untrack.add_argument("app")
    sub.add_parser("config", help="print the config file path")
    autostart = sub.add_parser("autostart", help="start aiwa automatically at login")
    autostart.add_argument("action", choices=["install", "uninstall", "status"])
    args = parser.parse_args(argv)

    load_dotenv(config_mod.CONFIG_PATH.parent / ".env")
    load_dotenv()  # a .env in the current directory, for development

    if args.command == "config":
        config_mod.load()  # creates the default file on first run
        print(config_mod.CONFIG_PATH)
        return 0
    config = config_mod.load()

    # Imported per command, so e.g. Qt only loads for `start`.
    from aiwa.commands.data import ActivityWatchUnavailable

    try:
        if args.command == "start":
            from aiwa.app import run

            return run(config)
        if args.command == "check":
            from aiwa.commands import check as command

            return command.run(config, show_all=args.all)
        if args.command == "focus":
            from aiwa.commands import focus as command

            return command.run(config, span_minutes=args.span, day=args.date)
        if args.command in ("track", "untrack"):
            from aiwa.commands import track as command

            return command.run(config, args.app, remove=args.command == "untrack")
        if args.command == "categorize":
            from aiwa.commands import categorize as command

            return command.run(args.key, args.category)
        from aiwa.commands import autostart as command

        return command.run(args.action)
    except ActivityWatchUnavailable as e:
        print(e)
        return 1
