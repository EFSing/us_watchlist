"""Run or restore a research ledger without changing any production entry point."""

import json
from datetime import date
from pathlib import Path

from us_watchlist.app.paper_inputs import load_day
from us_watchlist.domain.paper import PROTOCOL, Mode, check_policy
from us_watchlist.integrations.local_artifacts import publish_once, read_artifact
from us_watchlist.integrations.paper_ledger import canonical, publish_day, restore_day, study_identity
from us_watchlist.integrations.xnys import sessions_between
from us_watchlist.reporting.paper_html import paper_mail_text, render_paper
from us_watchlist.tracking.paper import active_plans, apply_day, summarize


def run_study(
    root: Path, mode: Mode, start: date, target: date, policy: dict, *,
    evidence_loader=None, initialize: bool = False, expect_previous: str | None = None,
) -> tuple[Path, dict]:
    if mode not in (Mode.HISTORICAL_REPLAY, Mode.SYNTHETIC):
        raise ValueError("PAPER_PROSPECTIVE_DISABLED")
    if initialize and (evidence_loader is None or start != target):
        raise ValueError("PAPER_EXPLICIT_INITIALIZATION_REQUIRES_FIRST_SESSION_INPUT")
    check_policy(policy)
    dates = sessions_between(start, target)
    study = {"mode": mode, "first_session": start.isoformat(), "protocol": PROTOCOL, "policy": policy}
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
    for day in dates[:-1]:
        evidence, head = restore_day(directory / str(day) / "day.json", identity, head, str(day))
        apply_day(records, evidence, identity, policy)
    if expect_previous is not None and expect_previous != head:
        raise ValueError("PAPER_EXPECTED_PREDECESSOR_MISMATCH")

    output = directory / str(target)
    ledger = output / "day.json"
    if evidence_loader is None:
        evidence, digest = restore_day(ledger, identity, head, str(target))
        apply_day(records, evidence, identity, policy)
    else:
        evidence = evidence_loader({row["plan"]["symbol"] for row in active_plans(records)})
        if evidence["trade_date"] != target.isoformat():
            raise ValueError("PAPER_INPUT_TARGET_MISMATCH")
        apply_day(records, evidence, identity, policy)
        if initialize:
            publish_once(manifest, canonical(study))
        digest = publish_day(ledger, identity, head, evidence)

    view = {"study": study, "trade_date": str(target), "ledger_sha256": digest,
            "source": evidence["source"], "records": records, "performance": summarize(records)}
    publish_once(output / "paper-report.html", render_paper(view).encode("utf-8"))
    publish_once(output / "paper-email.txt", paper_mail_text(view).encode("utf-8"))
    return output, view


def replay_iwb(
    root: Path, start: date, target: date, *, directory: Path | None, policy_path: Path | None,
    initialize: bool, expect_previous: str | None,
) -> tuple[Path, str]:
    policy = json.loads(read_artifact(policy_path)) if policy_path is not None else {}
    output, view = run_study(
        root, Mode.HISTORICAL_REPLAY, start, target, policy,
        evidence_loader=(lambda symbols: load_day(directory, target, symbols)) if directory is not None else None,
        initialize=initialize, expect_previous=expect_previous,
    )
    return output, view["ledger_sha256"]
