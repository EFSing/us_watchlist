"""Installed entry point for the offline demonstration."""

from argparse import ArgumentParser
from decimal import DecimalException
from pathlib import Path

from us_watchlist.app.smoke import run_smoke


def main() -> int:
    parser = ArgumentParser(prog="us-watchlist", description="US equities engineering skeleton")
    subcommands = parser.add_subparsers(dest="command", required=True)
    smoke = subcommands.add_parser("smoke", help="Build an HTML report using synthetic input")
    smoke.add_argument("--config", type=Path, default=Path("configs/smoke.toml"))
    args = parser.parse_args()

    try:
        print(run_smoke(args.config, Path(".runtime/artifacts/smoke")))
    except (OSError, KeyError, TypeError, ValueError, DecimalException) as error:
        parser.exit(1, f"us-watchlist smoke: {error}\n")
    return 0
