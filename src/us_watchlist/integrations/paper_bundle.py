"""Publish and verify a portable snapshot of the continuous paper ledger."""

import json
from datetime import date
from hashlib import sha256
from pathlib import Path

from us_watchlist.domain.paper import POSITION_PROTOCOL, Mode, check_policy
from us_watchlist.integrations.github_artifacts import MAX_ARTIFACT_BYTES
from us_watchlist.integrations.local_artifacts import publish_once, read_artifact
from us_watchlist.integrations.paper_ledger import canonical, restore_day, study_identity
from us_watchlist.integrations.xnys import sessions_between

PAPER_PREFIX = "us-iwb-v1-paper-"
_SCHEMA = "us_iwb_paper_bundle_v1"


def publish_bundle(output: Path, ledger: Path, view: dict, summary: str) -> dict:
    study = view["study"]
    start, target = map(date.fromisoformat, (study["first_session"], view["trade_date"]))
    report = read_artifact(ledger / str(target) / "report.html")
    summary_bytes = summary.encode("utf-8")
    receipt = {
        "schema": _SCHEMA, "trade_date": str(target), "study_id": study_identity(study),
        "ledger_sha256": view["ledger_sha256"], "canonical_report_sha256": view["source"]["report_sha256"],
        "combined_report_sha256": sha256(report).hexdigest(), "paper_summary_sha256": sha256(summary_bytes).hexdigest(),
    }
    payloads = {
        "study.json": canonical(study), "combined-report.html": report, "paper-summary.txt": summary_bytes,
    }
    for day in sessions_between(start, target):
        payloads[f"days/{day}.json"] = read_artifact(ledger / str(day) / "day.json")
    payloads["paper-receipt.json"] = canonical(receipt)
    if sum(map(len, payloads.values())) > MAX_ARTIFACT_BYTES:
        raise ValueError("PAPER_BUNDLE_TOO_LARGE")
    for name, body in payloads.items():
        publish_once(output / name, body)
    return receipt


def verify_bundle(
    directory: Path, target: date, *, report_sha256: str | None = None, expected_study: dict | None = None,
) -> tuple[dict, dict, bytes, bytes]:
    raw_study = read_artifact(directory / "study.json")
    study = json.loads(raw_study)
    receipt = json.loads(read_artifact(directory / "paper-receipt.json"))
    identity = study_identity(study)
    if (set(study) != {"mode", "first_session", "protocol", "policy"} or raw_study != canonical(study)
            or study["mode"] != Mode.PROSPECTIVE or study["protocol"] != POSITION_PROTOCOL
            or (expected_study is not None and study != expected_study)
            or (receipt["schema"], receipt["trade_date"], receipt["study_id"]) != (_SCHEMA, str(target), identity)):
        raise ValueError("PAPER_BUNDLE_IDENTITY_MISMATCH")
    check_policy(study["policy"], study["protocol"])
    dates = sessions_between(date.fromisoformat(study["first_session"]), target)
    days = directory / "days"
    if {path.name for path in days.iterdir()} != {f"{day}.json" for day in dates}:
        raise ValueError("PAPER_BUNDLE_SESSION_SET_MISMATCH")
    digest = None
    for day in dates:
        evidence, digest = restore_day(days / f"{day}.json", identity, digest, str(day))
    source_sha = evidence["source"]["report_sha256"]
    if (receipt["ledger_sha256"] != digest or receipt["canonical_report_sha256"] != source_sha
            or (report_sha256 is not None and source_sha != report_sha256)):
        raise ValueError("PAPER_BUNDLE_CANONICAL_OR_LEDGER_SHA_MISMATCH")

    combined = read_artifact(directory / "combined-report.html")
    summary = read_artifact(directory / "paper-summary.txt")
    if sha256(combined).hexdigest() != receipt["combined_report_sha256"]:
        raise ValueError("PAPER_BUNDLE_COMBINED_REPORT_SHA_MISMATCH")
    if sha256(summary).hexdigest() != receipt["paper_summary_sha256"]:
        raise ValueError("PAPER_BUNDLE_SUMMARY_SHA_MISMATCH")
    return study, receipt, combined, summary
