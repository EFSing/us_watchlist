"""Run one recoverable US daily observation on a fresh Actions runner."""

import re
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

from us_watchlist.app.iwb_daily import (
    PUBLISHABLE, REPORT_FILES, RETRYABLE_COVERAGE, encode_receipt, observe_iwb, update_pool, verify_completed,
)
from us_watchlist.app.iwb_paper_automation import DEFAULT_PAPER_POLICY, roll_paper
from us_watchlist.integrations.github_artifacts import GitHubArtifacts
from us_watchlist.integrations.iwb_holdings import MAX_AGE_DAYS, read_holdings
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.integrations.paper_bundle import PAPER_PREFIX
from us_watchlist.integrations.xnys import (
    completed_session, is_session, new_york_date, new_york_wall_time, regular_windows,
)
from us_watchlist.integrations.yahoo_chart import wait_before_recapture

POOL_PREFIX = "us-iwb-v1-pool-"
DAILY_PREFIX = "us-iwb-v1-daily-"
RECHECK_AGE_DAYS = 5
SCHEDULE_SETTLEMENT_MINUTES = 30
SCHEDULE_LOCAL_TIME = time(17, 37)


def _scheduled_target(
    now: datetime, created: datetime, state: dict, dispatched_date: date | None = None,
) -> tuple[date, str | None]:
    if created > now:
        raise ValueError("IWB_SCHEDULE_CREATED_IN_FUTURE")
    created_date = new_york_date(created)
    day = dispatched_date or created_date
    due = new_york_wall_time(day, SCHEDULE_LOCAL_TIME).astimezone(UTC)
    state.update({"run_created_at": created.isoformat(), "scheduled_for_utc": due.isoformat()})
    if created_date != day:
        return day, "SKIPPED_SCHEDULE_EXPIRED"
    if not is_session(day):
        return day, "SKIPPED_XNYS_CLOSED"
    session, = regular_windows(day, 1)
    ready = session.closes_at + timedelta(minutes=SCHEDULE_SETTLEMENT_MINUTES)
    state.update({"session_close_utc": session.closes_at.isoformat(), "settlement_ready_at": ready.isoformat()})
    if new_york_date(now) != day:
        return day, "SKIPPED_SCHEDULE_EXPIRED"
    if created < due or now < ready:
        return day, "SKIPPED_NOT_READY"
    return day, None


def _manual_target(now: datetime, requested: date | None) -> date:
    latest = completed_session(now)
    day = requested or latest
    if not is_session(day) or day > latest:
        raise ValueError(f"MANUAL_TARGET_REQUIRES_COMPLETED_XNYS_SESSION {day}")
    return day


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
    current: bool, code_sha: str, state: dict, outputs: dict[str, str], *, scheduled: bool,
    paper_start: date | None = None, paper_policy_path: Path = DEFAULT_PAPER_POLICY,
) -> str:
    catalog = archive.catalog()
    name = DAILY_PREFIX + target.isoformat()

    def publish_paper(directory: Path, run: dict, available_at: datetime | None) -> None:
        bundle, receipt, created = roll_paper(
            archive, catalog, workspace, paper_start, target, paper_policy_path, canonical=directory,
            report_sha256=run["report_sha256"], available_at=available_at, daily_prefix=DAILY_PREFIX,
        )
        state["paper"] = {**receipt, "reused": not created}
        if created:
            outputs.update(paper_name=PAPER_PREFIX + str(target), paper_dir=str(bundle))
        if "email_report_dir" in outputs:
            outputs["paper_bundle_dir"] = str(bundle)

    if name in catalog:
        existing = catalog[name]
        restored = workspace / "restored"
        archive.restore(existing, restored, REPORT_FILES)
        previous = verify_completed(restored, target)
        if holdings_date is not None and previous["holdings_date"] != holdings_date.isoformat():
            raise ValueError("IWB_PUBLISHED_REPORT_USES_ANOTHER_VERSION")
        state["existing_report"] = {"run_id": existing.run_id, "report_sha256": previous["report_sha256"]}
        if not scheduled:
            outputs["email_report_dir"] = str(restored)
        if paper_start is not None and (not scheduled or PAPER_PREFIX + str(target) in catalog):
            publish_paper(restored, previous, existing.created_at)
        return "REUSED_PUBLISHED_REPORT"

    pool = workspace / "pool"
    _prepare_pool(archive, catalog, pool, target, holdings_date, current, state, outputs)
    for attempt in range(1, 3):
        started = datetime.now(UTC)
        if scheduled and new_york_date(started) != target:
            return "SKIPPED_SCHEDULE_EXPIRED"
        output = workspace / f"attempt-{attempt}"
        record = {"attempt": attempt, "started_at": started.isoformat()}
        state["attempts"].append(record)
        outputs[f"diagnostic_attempt_{attempt}"] = str(output)
        run = observe_iwb(target, pool, output, code_sha, require_yahoo_close=scheduled)
        outcome = run["status"]
        record.update({"status": outcome, "yahoo_zip_sha256": run["yahoo_zip_sha256"],
                       "holdings_csv_sha256": run["holdings_csv_sha256"], "target_bars": run["target_bars"]})
        if scheduled and new_york_date(datetime.fromisoformat(run["observed_at"])) != target:
            record["status"] = "SKIPPED_SCHEDULE_EXPIRED"
            return record["status"]
        if outcome in PUBLISHABLE:
            verified = verify_completed(output, target)
            record["report_sha256"] = run["report_sha256"]
            outputs.pop(f"diagnostic_attempt_{attempt}")
            outputs.update({"report_name": name, "report_dir": str(output), "email_report_dir": str(output)})
            if paper_start is not None:
                publish_paper(output, verified, datetime.now(UTC))
            return outcome
        if outcome not in RETRYABLE_COVERAGE or attempt == 2:
            return outcome
        wait_before_recapture()
    raise AssertionError("Daily observation exhausted its retry loop")


def automate_iwb(
    workspace: Path, archive: GitHubArtifacts, code_sha: str, *, scheduled: bool,
    trade_date: date | None = None, holdings_date: date | None = None, vps_trade_date: date | None = None,
    paper_enabled: bool = False, paper_start_date: date | None = None, paper_policy_path: Path = DEFAULT_PAPER_POLICY,
) -> tuple[dict, dict[str, str]]:
    now = datetime.now(UTC)
    trigger = "schedule" if scheduled else "workflow_dispatch"
    if vps_trade_date is not None:
        trigger = "vps_schedule"
    automatic = scheduled or vps_trade_date is not None
    state = {"schema": "us_iwb_actions_attempt_v1", "started_at": now.isoformat(), "code_sha": code_sha,
             "trigger": trigger, "attempts": []}
    diagnostic = workspace / "workflow.json"
    outputs = {"diagnostic_receipt": str(diagnostic)}
    try:
        if not re.fullmatch(r"[0-9a-f]{40}", code_sha):
            raise ValueError("IWB_INVALID_CODE_SHA")
        if automatic:
            if trade_date is not None or holdings_date is not None:
                raise ValueError("IWB_SCHEDULE_DISALLOWS_MANUAL_DATES")
            if scheduled and vps_trade_date is not None:
                raise ValueError("IWB_NATIVE_SCHEDULE_DISALLOWS_VPS_DATE")
            created = archive.schedule_created_at(code_sha, event="workflow_dispatch" if vps_trade_date else "schedule")
            day, skip = _scheduled_target(now, created, state, vps_trade_date)
        else:
            day, skip = _manual_target(now, trade_date), None
        state["trade_date"] = day.isoformat()
        outputs["target"] = day.isoformat()
        paper_start = paper_start_date if paper_enabled and paper_start_date is not None and day >= paper_start_date else None
        state["status"] = skip or _execute(
            archive, workspace, day, holdings_date, day == completed_session(now), code_sha, state, outputs,
            scheduled=automatic, paper_start=paper_start, paper_policy_path=paper_policy_path,
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
