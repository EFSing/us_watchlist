"""Restore and advance the Actions paper ledger from verified daily archives."""

import json
from datetime import date, datetime
from pathlib import Path

from us_watchlist.app.iwb_daily import REPORT_FILES
from us_watchlist.app.iwb_paper import replay_archive
from us_watchlist.domain.paper import POSITION_PROTOCOL, Mode, check_policy
from us_watchlist.integrations.github_artifacts import Artifact, GitHubArtifacts
from us_watchlist.integrations.local_artifacts import publish_once, read_artifact
from us_watchlist.integrations.paper_bundle import PAPER_PREFIX, publish_bundle, verify_bundle
from us_watchlist.integrations.paper_ledger import study_identity
from us_watchlist.integrations.xnys import sessions_between
from us_watchlist.reporting.paper_html import account_mail_text

DEFAULT_PAPER_POLICY = Path("configs/iwb_paper_us_b_v2.json")


def roll_paper(
    archive: GitHubArtifacts, catalog: dict[str, Artifact], workspace: Path,
    start: date, target: date, policy_path: Path, *,
    canonical: Path, report_sha256: str, available_at: datetime | None, daily_prefix: str,
) -> tuple[Path, dict, bool]:
    policy = json.loads(read_artifact(policy_path))
    check_policy(policy, POSITION_PROTOCOL)
    study = {"mode": Mode.PROSPECTIVE, "first_session": str(start), "protocol": POSITION_PROTOCOL, "policy": policy}
    name = PAPER_PREFIX + str(target)
    bundle = workspace / "paper_bundle"
    if name in catalog:
        archive.restore_paper_bundle(catalog[name], bundle)
        _, receipt, _, _ = verify_bundle(bundle, target, report_sha256=report_sha256, expected_study=study)
        return bundle, receipt, False

    dates = sessions_between(start, target)
    root = workspace / "paper_ledger"
    ledger = root / Mode.PROSPECTIVE / study_identity(study)
    previous = next((day for day in reversed(dates[:-1]) if PAPER_PREFIX + str(day) in catalog), None)
    remaining = dates
    head = None
    if previous is not None:
        restored = workspace / "paper_previous"
        archive.restore_paper_bundle(catalog[PAPER_PREFIX + str(previous)], restored)
        _, receipt, _, _ = verify_bundle(restored, previous, expected_study=study)
        head = receipt["ledger_sha256"]
        previous_index = dates.index(previous) + 1
        publish_once(ledger / "study.json", read_artifact(restored / "study.json"))
        for day in dates[:previous_index]:
            publish_once(ledger / str(day) / "day.json", read_artifact(restored / "days" / f"{day}.json"))
        remaining = dates[previous_index:]

    for day in remaining:
        if day == target:
            daily, published_at = canonical, available_at
        else:
            artifact = catalog.get(daily_prefix + str(day))
            if artifact is None:
                raise ValueError(f"PAPER_REQUIRED_DAILY_ARTIFACT_MISSING {day}")
            daily, published_at = workspace / "paper_daily" / str(day), artifact.created_at
            archive.restore(artifact, daily, REPORT_FILES)
        if published_at is None:
            raise ValueError(f"PAPER_DAILY_AVAILABILITY_MISSING {day}")
        _, view = replay_archive(
            root, start, day, directory=daily, policy=policy, initialize=day == start, expect_previous=head,
            protocol=POSITION_PROTOCOL, mode=Mode.PROSPECTIVE, available_at=published_at, combined=day == target,
        )
        head = view["ledger_sha256"]

    receipt = publish_bundle(bundle, ledger, view, account_mail_text(view))
    verify_bundle(bundle, target, report_sha256=report_sha256, expected_study=study)
    return bundle, receipt, True
