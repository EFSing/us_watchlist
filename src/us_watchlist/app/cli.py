"""Installed entry point for the offline demonstration."""

import json
from argparse import ArgumentParser
from datetime import date
from decimal import DecimalException
from pathlib import Path

from us_watchlist.app.b_offline import run_b_offline
from us_watchlist.app.bc_offline import run_bc_offline
from us_watchlist.app.iwb_automation import automate_iwb
from us_watchlist.app.iwb_daily import DEFAULT_POOL, PUBLISHABLE, observe_iwb, update_pool, verify_completed
from us_watchlist.app.iwb_notifications import send_iwb_email
from us_watchlist.app.iwb_paper import replay_iwb
from us_watchlist.app.smoke import run_smoke
from us_watchlist.integrations.github_artifacts import GitHubArtifacts, write_workflow_outputs
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
    refresh = subcommands.add_parser("iwb-refresh", help="Download and validate an official IWB holdings version")
    refresh.add_argument("--pool-dir", type=Path, default=DEFAULT_POOL)
    refresh.add_argument("--holdings-date", type=date.fromisoformat, help="Request an exact historical holdings date")
    daily = subcommands.add_parser("iwb-report", help="Build a B+C observation from the local IWB base")
    daily.add_argument("--trade-date", type=date.fromisoformat, required=True)
    daily.add_argument("--pool-dir", type=Path, default=DEFAULT_POOL)
    daily.add_argument("--output", type=Path, required=True)
    daily.add_argument("--code-sha")
    verify = subcommands.add_parser("iwb-verify", help="Verify the receipts and hashes in an archived IWB report")
    verify.add_argument("--trade-date", type=date.fromisoformat, required=True)
    verify.add_argument("--directory", type=Path, required=True)
    automation = subcommands.add_parser("iwb-automation", help="Run one repository Actions observation")
    automation.add_argument("--workspace", type=Path, required=True)
    automation.add_argument("--event", choices=("schedule", "workflow_dispatch"), required=True)
    automation.add_argument("--trade-date", type=date.fromisoformat)
    automation.add_argument("--holdings-date", type=date.fromisoformat)
    automation.add_argument("--code-sha", required=True)
    mail = subcommands.add_parser("iwb-email", help="Email one verified, archived IWB B+C report")
    mail.add_argument("--directory", type=Path, required=True)
    mail.add_argument("--trade-date", type=date.fromisoformat, required=True)
    paper = subcommands.add_parser("iwb-paper", help="Replay or restore an offline IWB paper ledger")
    paper.add_argument("--ledger-root", type=Path, required=True)
    paper.add_argument("--start-date", type=date.fromisoformat, required=True)
    paper.add_argument("--trade-date", type=date.fromisoformat, required=True)
    paper.add_argument("--directory", type=Path, help="Verified IWB archive, omit to restore existing ledger")
    paper.add_argument("--initialize", action="store_true", help="Explicitly create the first session")
    paper.add_argument("--policy", type=Path, help="Explicit offline research parameters, omit for evidence only")
    paper.add_argument("--expect-previous", help="Expected prior ledger SHA-256 from an independent receipt")
    args = parser.parse_args()

    try:
        if args.command == "b-offline":
            print(run_b_offline(args.config, Path(".runtime/artifacts/b-offline")))
        elif args.command == "bc-offline":
            print(run_bc_offline(args.config, Path(".runtime/artifacts/bc-offline")))
        elif args.command == "capture-yahoo":
            bundle, target, symbols, provenance = yahoo_capture_request(args.config)
            digest, count = capture_yahoo(bundle, target, symbols, provenance, args.sessions)
            print(f"{bundle}\nSHA-256 {digest}\nResponses {count}/{len(symbols)}")
        elif args.command == "iwb-refresh":
            print(json.dumps(update_pool(args.pool_dir, args.holdings_date), ensure_ascii=True))
        elif args.command == "iwb-report":
            run = observe_iwb(args.trade_date, args.pool_dir, args.output, args.code_sha)
            print(json.dumps(run, ensure_ascii=True))
            return int(run["status"] not in PUBLISHABLE)
        elif args.command == "iwb-verify":
            run = verify_completed(args.directory, args.trade_date)
            print(f"{run['report_id']} · {run['status']} · SHA-256 {run['report_sha256']}")
        elif args.command == "iwb-automation":
            state, outputs = automate_iwb(
                args.workspace, GitHubArtifacts(), args.code_sha, scheduled=args.event == "schedule",
                trade_date=args.trade_date, holdings_date=args.holdings_date,
            )
            write_workflow_outputs(outputs)
            print(json.dumps(state, ensure_ascii=True))
            return int(state["status"] not in PUBLISHABLE | {
                "REUSED_PUBLISHED_REPORT", "SKIPPED_XNYS_CLOSED",
            })
        elif args.command == "iwb-email":
            send_iwb_email(args.directory, args.trade_date)
            print(f"IWB_EMAIL_SENT {args.trade_date}")
        elif args.command == "iwb-paper":
            output, digest = replay_iwb(
                args.ledger_root, args.start_date, args.trade_date, directory=args.directory, policy_path=args.policy,
                initialize=args.initialize, expect_previous=args.expect_previous,
            )
            print(f"{output}\nPAPER_LEDGER_SHA256 {digest}")
        else:
            print(run_smoke(args.config, Path(".runtime/artifacts/smoke")))
    except (OSError, ImportError, KeyError, TypeError, ValueError, DecimalException) as error:
        parser.exit(1, f"us-watchlist {args.command}: {error}\n")
    return 0
