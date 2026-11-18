"""Installed entry point for the offline demonstration."""

from argparse import ArgumentParser
from decimal import DecimalException
from pathlib import Path

from us_watchlist.app.b_offline import run_b_offline
from us_watchlist.app.smoke import run_smoke


def main() -> int:
    parser = ArgumentParser(prog="us-watchlist", description="US equities engineering skeleton")
    subcommands = parser.add_subparsers(dest="command", required=True)
    smoke = subcommands.add_parser("smoke", help="Build an HTML report using synthetic input")
    smoke.add_argument("--config", type=Path, default=Path("configs/smoke.toml"))
    b_offline = subcommands.add_parser("b-offline", help="Replay the US B shape on a local bundle")
    b_offline.add_argument("--config", type=Path, default=Path("configs/b_demo/replay.toml"))
    args = parser.parse_args()

    try:
        if args.command == "b-offline":
            print(run_b_offline(args.config, Path(".runtime/artifacts/b-offline")))
        else:
            print(run_smoke(args.config, Path(".runtime/artifacts/smoke")))
    except (OSError, KeyError, TypeError, ValueError, DecimalException) as error:
        parser.exit(1, f"us-watchlist {args.command}: {error}\n")
    return 0
