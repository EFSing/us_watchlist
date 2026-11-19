"""Run one recoverable US daily observation on a fresh Actions runner."""

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from us_watchlist.app.iwb_daily import (
    PUBLISHABLE, REPORT_FILES, RETRYABLE_COVERAGE, encode_receipt, observe_iwb, update_pool, verify_completed,
)
from us_watchlist.integrations.github_artifacts import GitHubArtifacts
from us_watchlist.integrations.iwb_holdings import MAX_AGE_DAYS, read_holdings
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.integrations.xnys import completed_session, is_session, new_york_date, regular_windows
from us_watchlist.integrations.yahoo_chart import wait_before_recapture

POOL_PREFIX = "us-iwb-v1-pool-"
DAILY_PREFIX = "us-iwb-v1-daily-"
RECHECK_AGE_DAYS = 5
SCHEDULE_SETTLEMENT_MINUTES = 30


def _target(now: datetime, scheduled: bool, requested: date | None) -> tuple[date, str | None]:
    if scheduled:
        day = new_york_date(now)
        if not is_session(day):
            return day, "SKIPPED_XNYS_CLOSED"
        if now < regular_windows(day, 1)[0].closes_at + timedelta(minutes=SCHEDULE_SETTLEMENT_MINUTES):
            return day, "SKIPPED_NOT_READY"
        return day, None
    day = requested or completed_session(now)
    if not is_session(day) or day > completed_session(now):
        raise ValueError(f"MANUAL_TARGET_REQUIRES_COMPLETED_XNYS_SESSION {day}")
    return day, None


def _prepare_pool(
    archive: GitHubArtifacts, catalog: dict, pool: Path, target: date, exact: date | None,
    current: bool, state: dict, outputs: dict[str, str],
) -> None:
    if exact is not None and not 0 <= (target - exact).days <= MAX_AGE_DAYS:
        raise ValueError(f"IWB_REQUESTED_VERSION_OUTSIDE_TARGET_WINDOW {exact}")
    candidates = []
    for name in catalog:
        if name.startswith(POOL_PREFIX):
            day = date.fromisoformat(name.removeprefix(POOL_PREFIX))
            if day <= target and (exact is None or exact == day):
                candidates.append(day)
    latest = max(candidates, default=None)
    # Restore only an admissible archived version. A historical manual recovery can specify an exact date.
    if latest is not None and (target - latest).days <= MAX_AGE_DAYS:
        filename = f"IWB_{latest}.zip"
        archived = catalog[POOL_PREFIX + latest.isoformat()]
        archive.restore(archived, pool, {filename})
        receipt = read_holdings(pool / filename)
        if receipt.day != latest:
            raise ValueError("IWB_RESTORED_VERSION_DATE_MISMATCH")
        state["pool_restored"] = {"date": latest.isoformat(), "run_id": archived.run_id}
    elif not current and exact is None:
        raise ValueError("IWB_NO_RETAINED_VERSION_FOR_BACKFILL: provide an official holdings_date")

    refresh = (exact is not None and latest is None) or (
        exact is None and current and (latest is None or (target - latest).days >= RECHECK_AGE_DAYS)
    )
    if refresh:
        outcome = update_pool(pool, exact)
        state["pool_refresh"] = outcome
        new_date = date.fromisoformat(outcome["holdings_date"])
        if new_date > target or (latest is not None and new_date < latest):
            raise ValueError("IWB_REFRESH_REGRESSED_OR_EXCEEDS_TARGET")
        name = POOL_PREFIX + outcome["holdings_date"]
        if name not in catalog:
            outputs["pool_name"] = name
            outputs["pool_file"] = outcome["path"]


def _execute(
    archive: GitHubArtifacts, workspace: Path, target: date, holdings_date: date | None,
    current: bool, code_sha: str, state: dict, outputs: dict[str, str],
) -> str:
    catalog = archive.catalog()
    name = DAILY_PREFIX + target.isoformat()
    if name in catalog:
        existing = catalog[name]
        restored = workspace / "restored"
        archive.restore(existing, restored, REPORT_FILES)
        previous = verify_completed(restored, target)
        if holdings_date is not None and previous["holdings_date"] != holdings_date.isoformat():
            raise ValueError("IWB_PUBLISHED_REPORT_USES_ANOTHER_VERSION")
        state["existing_report"] = {"run_id": existing.run_id, "report_sha256": previous["report_sha256"]}
        return "REUSED_PUBLISHED_REPORT"

    pool = workspace / "pool"
    _prepare_pool(archive, catalog, pool, target, holdings_date, current, state, outputs)
    for attempt in range(1, 3):
        output = workspace / f"attempt-{attempt}"
        record = {"attempt": attempt, "started_at": datetime.now(UTC).isoformat()}
        state["attempts"].append(record)
        outputs[f"diagnostic_attempt_{attempt}"] = str(output)
        run = observe_iwb(target, pool, output, code_sha)
        outcome = run["status"]
        record.update({"status": outcome, "yahoo_zip_sha256": run["yahoo_zip_sha256"],
                       "holdings_csv_sha256": run["holdings_csv_sha256"], "target_bars": run["target_bars"]})
        if outcome in PUBLISHABLE:
            verify_completed(output, target)
            record["report_sha256"] = run["report_sha256"]
            outputs.pop(f"diagnostic_attempt_{attempt}")
            outputs.update({"report_name": name, "report_dir": str(output)})
            return outcome
        if outcome not in RETRYABLE_COVERAGE or attempt == 2:
            return outcome
        wait_before_recapture()
    raise AssertionError("Daily observation exhausted its retry loop")


def automate_iwb(
    workspace: Path, archive: GitHubArtifacts, code_sha: str, *, scheduled: bool,
    trade_date: date | None = None, holdings_date: date | None = None,
) -> tuple[dict, dict[str, str]]:
    now = datetime.now(UTC)
    state = {"schema": "us_iwb_actions_attempt_v1", "started_at": now.isoformat(), "code_sha": code_sha,
             "trigger": "schedule" if scheduled else "workflow_dispatch", "attempts": []}
    diagnostic = workspace / "workflow.json"
    outputs = {"diagnostic_receipt": str(diagnostic)}
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", code_sha):
            raise ValueError("IWB_INVALID_CODE_SHA")
        day, skip = _target(now, scheduled, trade_date)
        state["trade_date"] = day.isoformat()
        outputs["target"] = day.isoformat()
        state["status"] = skip or _execute(
            archive, workspace, day, holdings_date, day == completed_session(now), code_sha, state, outputs,
        )
    except (OSError, KeyError, TypeError, ValueError, ArithmeticError) as error:
        state["status"] = "FAILED"
        state["error"] = f"{type(error).__name__}: {error}"
        if state["attempts"] and "status" not in state["attempts"][-1]:
            state["attempts"][-1]["status"] = "FAILED"
    state["finished_at"] = datetime.now(UTC).isoformat()
    publish_once(diagnostic, encode_receipt(state))
    outputs["status"] = state["status"]
    return state, outputs
