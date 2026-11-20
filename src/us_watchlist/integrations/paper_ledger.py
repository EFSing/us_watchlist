"""Immutable per-session inputs and predecessor verification for offline recovery."""

import json
from hashlib import sha256
from pathlib import Path

from us_watchlist.integrations.local_artifacts import publish_once, read_artifact


def canonical(value: dict) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


def study_identity(study: dict) -> str:
    return sha256(canonical(study)).hexdigest()


def _envelope(study_id: str, predecessor: str | None, evidence: dict) -> tuple[bytes, str]:
    body = {"study": study_id, "previous_sha256": predecessor, "evidence": evidence}
    digest = sha256(canonical(body)).hexdigest()
    return canonical({"body": body, "sha256": digest}), digest


def restore_day(path: Path, study_id: str, predecessor: str | None, trade_date: str) -> tuple[dict, str]:
    try:
        raw = read_artifact(path)
    except FileNotFoundError as error:
        raise FileNotFoundError(f"PAPER_LEDGER_DAY_MISSING {trade_date} {path}") from error
    envelope = json.loads(raw)
    evidence = envelope["body"]["evidence"]
    expected, digest = _envelope(study_id, predecessor, evidence)
    if raw != expected or evidence["trade_date"] != trade_date:
        raise ValueError(f"PAPER_LEDGER_INTEGRITY_CONFLICT {trade_date}")
    return evidence, digest


def publish_day(path: Path, study_id: str, predecessor: str | None, evidence: dict) -> str:
    body, digest = _envelope(study_id, predecessor, evidence)
    publish_once(path, body)
    return digest
