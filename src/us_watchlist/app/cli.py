"""Installed entry point for the offline demonstration."""

from argparse import ArgumentParser
from decimal import DecimalException
from pathlib import Path

from us_watchlist.app.b_offline import run_b_offline
from us_watchlist.app.bc_offline import run_bc_offline
from us_watchlist.app.smoke import run_smoke
from us_watchlist.integrations.replay_input import yahoo_capture_request
from us_watchlist.integrations.yahoo_chart import capture_yahoo


def main() -> int:
    parser = ArgumentParser(prog="us-watchlist", description="US equities engineering skeleton")
    subcommands = parser.add_subparsers(dest="command", required=True)
    smoke = subcommands.add_parser("smoke", help="Build an HTML report using synthetic input")
    smoke.add_argument("--config", type=Path, default=Path("configs/smoke.toml"))
    b_offline = subcommands.add_parser("b-offline", help="Replay the US B shape on a local bundle")
    b_offline.add_argument("--config", type=Path, default=Path("configs/b_demo/replay.toml"))
    bc_offline = subcommands.add_parser("bc-offline", help="Build a joint US B+C offline report")
    bc_offline.add_argument("--config", type=Path, default=Path("configs/b_demo/replay.toml"))
    yahoo = subcommands.add_parser("capture-yahoo", help="Freeze Yahoo Chart data for a local offline observation")
    yahoo.add_argument("--config", type=Path, required=True)
    yahoo.add_argument("--sessions", type=int, default=120)
    args = parser.parse_args()

    try:
        if args.command == "b-offline":
            print(run_b_offline(args.config, Path(".runtime/artifacts/b-offline")))
        elif args.command == "bc-offline":
            print(run_bc_offline(args.config, Path(".runtime/artifacts/bc-offline")))
        elif args.command == "capture-yahoo":
            bundle, date, symbols, provenance = yahoo_capture_request(args.config)
            digest, count = capture_yahoo(bundle, date, symbols, provenance, args.sessions)
            print(f"{bundle}\nSHA-256 {digest}\nResponses {count}/{len(symbols)}")
        else:
            print(run_smoke(args.config, Path(".runtime/artifacts/smoke")))
    except (OSError, ImportError, KeyError, TypeError, ValueError, DecimalException) as error:
        parser.exit(1, f"us-watchlist {args.command}: {error}\n")
    return 0
