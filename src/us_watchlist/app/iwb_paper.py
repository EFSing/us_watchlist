"""Run or restore a research ledger without changing any production entry point."""

import json
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path

from us_watchlist.app.paper_inputs import load_day
from us_watchlist.domain.models import require_utc
from us_watchlist.domain.paper import BASIS, B_VERSION, POSITION_PROTOCOL, PROTOCOL, Mode, check_policy
from us_watchlist.domain.replay_research import REFERENCE_V1
from us_watchlist.domain.screening import B_SHAPE_V1
from us_watchlist.integrations.local_artifacts import publish_once, read_artifact
from us_watchlist.integrations.paper_ledger import canonical, publish_day, restore_day, study_identity
from us_watchlist.integrations.xnys import next_session, regular_windows, sessions_between
from us_watchlist.reporting.paper_html import paper_mail_text, render_combined_paper, render_paper
from us_watchlist.tracking.paper import active_plans, apply_day, summarize


def _check_position_day(day: dict, current, following) -> None:
    if (day["trade_date"], day["opens_at"], day["closes_at"], day["next_session"], day["next_opens_at"]) != (
        str(current.trading_date), current.opens_at.isoformat(), current.closes_at.isoformat(),
        str(following.trading_date), following.opens_at.isoformat(),
    ):
        raise ValueError("PAPER_POSITION_SESSION_MISMATCH")
    observed = datetime.fromisoformat(day["source"]["observed_at"])
    require_utc(observed)
    if observed < current.closes_at or day["source"]["price_basis"] != BASIS:
        raise ValueError("PAPER_POSITION_EVIDENCE_MISMATCH")

    seeds = day["seeds"]
    length = max(map(len, seeds.values()), default=0)
    if length:
        expected = [str(item.trading_date) for item in regular_windows(current.trading_date, length)]
        for symbol, bars in seeds.items():
            if bars and (
                [trade_date for trade_date, _ in bars] != expected[-len(bars):]
                or bars[-1][1] != day["quotes"][symbol]["current"]
            ):
                raise ValueError("PAPER_POSITION_SEED_MISMATCH")


def _combined_source(root: Path, expected: str, report: bytes | None) -> bytes:
    if not isinstance(expected, str) or len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        raise ValueError("PAPER_COMBINED_INVALID_REPORT_SHA")
    path = root / ".report-sources" / f"{expected}.bin"
    from_archive = report is not None
    if report is None:
        try:
            report = read_artifact(path)
        except FileNotFoundError as error:
            raise FileNotFoundError(
                "PAPER_COMBINED_SOURCE_MISSING: provide --directory with the original IWB archive"
            ) from error
    if sha256(report).hexdigest() != expected:
        raise ValueError("PAPER_REPORT_SHA_MISMATCH")
    if from_archive:
        publish_once(path, report)
    return report


def _publish_paper_view(path: Path, view: dict, daily: bytes | None, b_version: str) -> None:
    def render(projection: dict, *, company_labels: bool) -> bytes:
        if daily is not None:
            return render_combined_paper(daily, projection, company_labels=company_labels)
        return render_paper(projection, company_labels=company_labels).encode("utf-8")

    body = render(view, company_labels=True)
    try:
        publish_once(path, body)
    except ValueError:
        # Accept exact bytes from before company labels or the retirement of empty performance rows.
        existing = read_artifact(path)
        if existing != render(view, company_labels=False):
            legacy = {**view, "performance": summarize(view["records"], b_version=b_version, include_empty_retired=True)}
            if existing not in (render(legacy, company_labels=True), render(legacy, company_labels=False)):
                raise


def run_study(
    root: Path, mode: Mode, start: date, target: date, policy: dict, *,
    evidence_loader=None, initialize: bool = False, expect_previous: str | None = None, protocol: str = PROTOCOL,
    combined: bool = False, archived_report: bytes | None = None,
) -> tuple[Path, dict]:
    if mode not in (Mode.HISTORICAL_REPLAY, Mode.SYNTHETIC):
        raise ValueError("PAPER_PROSPECTIVE_DISABLED")
    if initialize and (evidence_loader is None or start != target):
        raise ValueError("PAPER_EXPLICIT_INITIALIZATION_REQUIRES_FIRST_SESSION_INPUT")
    check_policy(policy, protocol)
    dates = sessions_between(start, target)
    windows = regular_windows(next_session(target), len(dates) + 1) if protocol == POSITION_PROTOCOL else ()
    study = {"mode": mode, "first_session": start.isoformat(), "protocol": protocol, "policy": policy}
    identity = study_identity(study)
    directory = root / mode / identity
    manifest = directory / "study.json"
    if not initialize:
        try:
            saved_study = read_artifact(manifest)
        except FileNotFoundError as error:
            raise FileNotFoundError(f"PAPER_STUDY_MANIFEST_MISSING {manifest}") from error
        if saved_study != canonical(study):
            raise ValueError("PAPER_STUDY_MANIFEST_CONFLICT")

    records = {}
    head = None

    def advance(evidence: dict, index: int) -> None:
        if evidence["trade_date"] != dates[index].isoformat():
            raise ValueError("PAPER_INPUT_TARGET_MISMATCH")
        if windows:
            _check_position_day(evidence, windows[index], windows[index + 1])
        apply_day(records, evidence, identity, policy, protocol)

    for index, day in enumerate(dates[:-1]):
        evidence, head = restore_day(directory / str(day) / "day.json", identity, head, str(day))
        advance(evidence, index)
    if expect_previous is not None and expect_previous != head:
        raise ValueError("PAPER_EXPECTED_PREDECESSOR_MISMATCH")

    output = directory / str(target)
    ledger = output / "day.json"
    if evidence_loader is None:
        evidence, digest = restore_day(ledger, identity, head, str(target))
    else:
        evidence = evidence_loader({row["plan"]["symbol"] for row in active_plans(records)})
    advance(evidence, len(dates) - 1)
    daily = _combined_source(root, evidence["source"]["report_sha256"], archived_report) if combined else None
    if evidence_loader is not None:
        if initialize:
            publish_once(manifest, canonical(study))
        digest = publish_day(ledger, identity, head, evidence)

    for row in records.values():
        row.pop("_indicators", None)
    b_version = B_SHAPE_V1 if evidence["source"]["research_version"] == REFERENCE_V1 else B_VERSION
    view = {"study": study, "trade_date": str(target), "ledger_sha256": digest,
            "source": evidence["source"], "records": records, "performance": summarize(records, b_version=b_version)}
    _publish_paper_view(output / ("report.html" if daily is not None else "paper-report.html"), view, daily, b_version)
    if daily is None:
        publish_once(output / "paper-email.txt", paper_mail_text(view).encode("utf-8"))
    return output, view


def replay_iwb(
    root: Path, start: date, target: date, *, directory: Path | None, policy_path: Path | None,
    initialize: bool, expect_previous: str | None, protocol: str = PROTOCOL, combined: bool = False,
) -> tuple[Path, str]:
    policy = json.loads(read_artifact(policy_path)) if policy_path is not None else {}
    position_policy = policy if protocol == POSITION_PROTOCOL else None
    output, view = run_study(
        root, Mode.HISTORICAL_REPLAY, start, target, policy,
        evidence_loader=(
            lambda symbols: load_day(directory, target, symbols, position_policy=position_policy)
        ) if directory is not None else None,
        initialize=initialize, expect_previous=expect_previous, protocol=protocol,
        combined=combined,
        archived_report=read_artifact(directory / "report.html") if combined and directory is not None else None,
    )
    return output, view["ledger_sha256"]
