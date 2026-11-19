"""Select a local IWB version and observe a completed XNYS session with B and C."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

from us_watchlist.app.bc_offline import evaluate_joint, observe_joint
from us_watchlist.app.replay import prepare_input
from us_watchlist.domain.screening import IwbReportEvidence, ScreeningUniverse
from us_watchlist.integrations.iwb_holdings import MAX_AGE_DAYS, read_holdings, refresh_holdings, versions
from us_watchlist.integrations.local_artifacts import publish_once, read_artifact
from us_watchlist.integrations.replay_input import ReplayInput
from us_watchlist.integrations.xnys import completed_session, is_session, regular_windows
from us_watchlist.integrations.yahoo_chart import capture_yahoo, read_yahoo
from us_watchlist.reporting.replay_html import render_joint_replay
from us_watchlist.universe.eligibility import eligible_symbols

DEFAULT_POOL = Path(".runtime/data/iwb")
HISTORY_SESSIONS = 120
MIN_TARGET_COVERAGE_PERCENT = 95
PUBLISHABLE = {"SUCCESS", "PARTIAL_COVERAGE"}
RETRYABLE_COVERAGE = {"YAHOO_TARGET_COVERAGE_BELOW_FLOOR", "YAHOO_STRATEGY_HISTORY_UNAVAILABLE"}
REPORT_FILES = {"holdings.zip", "yahoo.zip", "plan.json", "inputs.json", "report.html", "run.json"}


def encode_receipt(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode("utf-8")


def report_identity(target: date) -> str:
    return f"US_{target}_regular_IWB_BC_v1"


def verify_completed(output: Path, target: date) -> dict:
    raw_inputs = read_artifact(output / "inputs.json")
    inputs = json.loads(raw_inputs)
    plan = json.loads(read_artifact(output / "plan.json"))
    run = json.loads(read_artifact(output / "run.json"))
    if (
        (plan["schema"], inputs["schema"], run["schema"]) != (
            "us_iwb_daily_plan_v1", "us_iwb_daily_inputs_v1", "us_iwb_daily_run_v1",
        )
        or (run["market"], run["session"], run["trade_date"], run["report_id"]) != (
            "US", "regular", target.isoformat(), report_identity(target),
        )
        or any(inputs.get(key) != value for key, value in plan.items() if key != "schema")
        or any(run.get(key) != value for key, value in inputs.items() if key != "schema")
        or run["status"] not in PUBLISHABLE
        or run["listed_equities"] <= 0
        or not run["listed_equities"] * MIN_TARGET_COVERAGE_PERCENT <= run["target_bars"] * 100 <= run["listed_equities"] * 100
    ):
        raise ValueError(f"IWB_ARCHIVED_RUN_RECEIPT_MISMATCH {target}")
    if sha256(raw_inputs).hexdigest() != run["input_sha256"]:
        raise ValueError("IWB_ARCHIVED_INPUT_SHA_MISMATCH")
    for name, key in (("yahoo.zip", "yahoo_zip_sha256"), ("holdings.zip", "holdings_zip_sha256"),
                      ("report.html", "report_sha256")):
        if sha256(read_artifact(output / name)).hexdigest() != run[key]:
            raise ValueError(f"IWB_ARCHIVED_FILE_SHA_MISMATCH {name}")
    holdings = read_holdings(output / "holdings.zip")
    if (holdings.day.isoformat(), holdings.snapshot.provenance.snapshot_id) != (
        run["holdings_date"], run["holdings_csv_sha256"],
    ):
        raise ValueError("IWB_ARCHIVED_POOL_RECEIPT_MISMATCH")
    return run


def update_pool(root: Path, requested: date | None) -> dict:
    latest = completed_session(datetime.now(UTC))
    through = requested or latest
    if not is_session(through) or through > latest:
        raise ValueError(f"IWB_REFRESH_REQUIRES_COMPLETED_XNYS_SESSION {through}")
    path, version = refresh_holdings(root, requested, through)
    previous = versions(root, version.day)[:-1]
    before = read_holdings(previous[-1][1]).snapshot.members if previous else ()
    previous_status = {member.symbol: member.active for member in before}
    current = {member.symbol: member.active for member in version.snapshot.members}
    return {
        "path": str(path), "holdings_date": version.day.isoformat(),
        "source": version.snapshot.provenance.source, "sha256": version.snapshot.provenance.snapshot_id,
        "available_at": version.snapshot.provenance.available_at.isoformat(),
        "equity_count": len(current), "listed_count": sum(current.values()),
        "non_equity_rows": version.non_equity_rows, "inactive": dict(version.inactive),
        "previous_holdings_date": previous[-1][0].isoformat() if previous else None,
        "added": sorted(current.keys() - previous_status.keys()) if previous else [],
        "removed": sorted(previous_status.keys() - current.keys()),
        "listing_status_changed": sorted(
            symbol for symbol in current.keys() & previous_status.keys() if current[symbol] != previous_status[symbol]
        ),
    }


def observe_iwb(target: date, pool: Path, output: Path, code_sha: str | None = None) -> dict:
    now = datetime.now(UTC)
    session, = regular_windows(target, 1)
    if session.closes_at >= now:
        raise ValueError(f"XNYS_SESSION_NOT_CLOSED {target}")
    frozen_holdings = output / "holdings.zip"
    if not frozen_holdings.exists():
        local = versions(pool, target)
        if not local:
            raise ValueError(f"IWB_NO_LOCAL_VERSION for {target}")
        day, selected = local[-1]
        if read_holdings(selected).day != day:
            raise ValueError(f"IWB_VERSION_FILENAME_DATE_MISMATCH {selected.name}")
        publish_once(frozen_holdings, read_artifact(selected))
    holdings = read_holdings(frozen_holdings)
    snapshot = holdings.snapshot
    age = (target - holdings.day).days
    if not 0 <= age <= MAX_AGE_DAYS or not is_session(holdings.day):
        raise ValueError(f"IWB_STALE_OR_INVALID_FOR_TARGET holdings={holdings.day} target={target} max_age_days={MAX_AGE_DAYS}")
    symbols = eligible_symbols(snapshot, session, now)
    plan = {
        "schema": "us_iwb_daily_plan_v1", "market": "US", "trade_date": target.isoformat(), "session": "regular",
        "report_id": report_identity(target), "code_sha": code_sha,
        "holdings_date": holdings.day.isoformat(), "holdings_source": snapshot.provenance.source,
        "holdings_available_at": snapshot.provenance.available_at.isoformat(),
        "holdings_csv_sha256": snapshot.provenance.snapshot_id,
        "holdings_zip_sha256": sha256(read_artifact(frozen_holdings)).hexdigest(),
        "holdings_age_days": age, "holdings_max_age_days": MAX_AGE_DAYS,
        "base_equities": len(snapshot.members), "listed_equities": len(symbols),
        "excluded_non_equity_rows": holdings.non_equity_rows, "inactive_equities": dict(holdings.inactive),
        "history_sessions": HISTORY_SESSIONS, "minimum_target_coverage_percent": MIN_TARGET_COVERAGE_PERCENT,
    }
    publish_once(output / "plan.json", encode_receipt(plan))
    quote_path = output / "yahoo.zip"
    if not quote_path.is_file():
        capture_yahoo(quote_path, target, symbols, snapshot.provenance, HISTORY_SESSIONS, official_iwb=True)
    quotes = read_artifact(quote_path)
    digest = sha256(quotes).hexdigest()
    history, observed, calendar, gaps = read_yahoo(
        quotes, digest, target, symbols, snapshot.provenance, official_iwb=True,
    )
    if len(history) != HISTORY_SESSIONS:
        raise ValueError("IWB_DAILY_YAHOO_SESSION_COUNT_MISMATCH")
    inputs_record = {
        **plan, "schema": "us_iwb_daily_inputs_v1", "yahoo_zip_sha256": digest,
        "observed_at": observed.isoformat(), "calendar": calendar,
        "session_close_utc": session.closes_at.isoformat(),
    }
    input_payload = encode_receipt(inputs_record)
    input_sha = sha256(input_payload).hexdigest()
    publish_once(output / "inputs.json", input_payload)
    pool_data = ScreeningUniverse(snapshot, holdings.day, len(snapshot.members), len(symbols), "LOCAL_IWB")
    evidence, inputs = prepare_input(ReplayInput(
        "iwb_yahoo_observation", target, observed, pool_data, history, None, input_sha, calendar, gaps,
    ))
    target_bars = {bar.symbol for bar in inputs.history[-1].bars}
    b, c = evaluate_joint(inputs)
    failed = any(result.error is not None for result in (b, *c))
    coverage_ok = len(target_bars) * 100 >= len(symbols) * MIN_TARGET_COVERAGE_PERCENT
    partial = bool(holdings.inactive or gaps or len(target_bars) != len(symbols) or any(
        row.reason == "INCOMPLETE_HISTORY" for result in (b, *c) for row in result.evaluations
    ))
    if failed:
        status = "FAILED_STRATEGY"
    elif not coverage_ok:
        status = "YAHOO_TARGET_COVERAGE_BELOW_FLOOR"
    elif any(all(row.reason == "INCOMPLETE_HISTORY" for row in result.evaluations) for result in (b, *c)):
        status = "YAHOO_STRATEGY_HISTORY_UNAVAILABLE"
    else:
        status = "PARTIAL_COVERAGE" if partial else "SUCCESS"
    evidence = replace(evidence, iwb=IwbReportEvidence(
        holdings.inactive, holdings.non_equity_rows, MAX_AGE_DAYS, len(target_bars), status,
    ))
    research = observe_joint(evidence, inputs, b, c)
    report = render_joint_replay(evidence, b, c, research=research).encode("utf-8")
    report_sha = sha256(report).hexdigest()
    publish_once(output / "report.html", report)
    run = {
        **inputs_record, "schema": "us_iwb_daily_run_v1", "input_sha256": input_sha,
        "report_sha256": report_sha, "status": status, "target_bars": len(target_bars),
        "missing_target_bars": sorted(set(symbols) - target_bars), "symbol_diagnostics": dict(gaps),
        "strategies": {result.strategy.version: {
            "matches": sum(row.signal is not None for row in result.evaluations),
            "incomplete_history": sum(row.reason == "INCOMPLETE_HISTORY" for row in result.evaluations),
            "evaluated": len(result.evaluations), "error": result.error,
        } for result in (b, *c)},
    }
    publish_once(output / "run.json", encode_receipt(run))
    return run
