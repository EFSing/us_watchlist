"""Read the published US Candidate projection from a pipeline report artifact."""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from us_watchlist.domain.models import MARKET, Provenance, UniverseMember, UniverseSnapshot

IWB_SOURCE = "iShares_IWB_OFFICIAL_HOLDINGS"
ARTIFACT = re.compile(
    r"https://github\.com/EFSing/stock-data-pipeline/actions/runs/[0-9]+/artifacts/[0-9]+"
)
LIFECYCLE_STATES = {"ACTIVE", "UNLISTED_OR_NO_MARKET", "WHEN_ISSUED"}


@dataclass(frozen=True)
class PipelineCandidates:
    snapshot: UniverseSnapshot
    holdings_date: date
    seed_count: int
    active_count: int
    status: str


def read_pipeline_candidates(
    payload: bytes,
    *,
    artifact: str,
    artifact_sha256: str,
    uploaded_at: datetime,
    synthetic: bool,
) -> PipelineCandidates:
    digest = sha256(payload).hexdigest()
    if digest != artifact_sha256:
        raise ValueError("IWB artifact SHA-256 does not match the recorded checksum")
    if synthetic:
        if not artifact.startswith("synthetic:"):
            raise ValueError("Synthetic IWB input requires a synthetic artifact identity")
        report = json.loads(payload)
    else:
        if not ARTIFACT.fullmatch(artifact):
            raise ValueError("IWB receipt must identify a stock-data-pipeline run artifact")
        try:
            with ZipFile(BytesIO(payload)) as archive:
                report = json.loads(archive.read("daily-report.json"))
        except BadZipFile as error:
            raise ValueError("Expected the original stock-data-pipeline report ZIP") from error

    if report["market"] != MARKET:
        raise ValueError("IWB input requires a US daily report")
    provenance = Provenance(artifact, digest, uploaded_at)
    generated_at = datetime.fromisoformat(report["generated_at"])
    if generated_at.utcoffset() is None or generated_at > uploaded_at:
        raise ValueError("The IWB artifact upload must follow the offset-aware report timestamp")
    report_date = date.fromisoformat(report["as_of_date"])
    candidate = report["candidate_markets"][MARKET]
    if candidate["market"] != MARKET or date.fromisoformat(candidate["as_of_date"]) != report_date:
        raise ValueError("IWB candidate audit market or report date does not match its envelope")

    seed_date = date.fromisoformat(candidate["seed_source_as_of"])
    records = candidate["candidate_records"]
    count = candidate["seed_count"]
    if seed_date > report_date or type(count) is not int or count <= 0 or len(records) != count:
        raise ValueError("Expected a complete dated IWB audit with one row per original seed")

    if candidate["universe_snapshot_status"] != "AVAILABLE":
        raise ValueError("The pipeline Candidate universe snapshot is unavailable")
    outcome = candidate["candidate_selection_outcome"]
    if outcome not in {"CANDIDATES_INCLUDED", "NO_CANDIDATES"}:
        raise ValueError(f"The pipeline did not publish Candidate membership: {outcome}")
    members = {}
    for row in records:
        if (
            row["market"] != MARKET
            or row["source"] != IWB_SOURCE
            or date.fromisoformat(row["source_as_of"]) != seed_date
            or row["lifecycle_status"] not in LIFECYCLE_STATES
        ):
            raise ValueError("IWB audit contains an inconsistent market, source, date or lifecycle")
        symbol = row["symbol"]
        active = row["lifecycle_status"] == "ACTIVE"
        included = row["included"]
        if symbol in members:
            raise ValueError("IWB audit contains duplicate canonical symbols")
        if type(included) is not bool or (included and not active):
            raise ValueError("Inconsistent pipeline Candidate inclusion flag")
        members[symbol] = UniverseMember(symbol, active)

    selected = candidate["candidate_included_symbols"]
    selected_count = candidate["candidate_included_count"]
    if (
        type(selected) is not list or type(selected_count) is not int
        or len(selected) != selected_count
        or len(set(selected)) != selected_count
        or set(selected) != {row["symbol"] for row in records if row["included"]}
        or bool(selected) != (outcome == "CANDIDATES_INCLUDED")
    ):
        raise ValueError("Published Candidate count, symbol list and audit flags disagree")
    return PipelineCandidates(
        UniverseSnapshot(report_date, provenance, tuple(members[symbol] for symbol in sorted(selected))),
        seed_date, count, sum(member.active for member in members.values()), candidate["candidate_status"],
    )
