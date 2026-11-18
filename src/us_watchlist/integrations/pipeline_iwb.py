"""Read a complete IWB membership projection from a pipeline report artifact."""

import json
import re
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


def read_iwb_seed(
    payload: bytes,
    *,
    artifact: str,
    artifact_sha256: str,
    uploaded_at: datetime,
    synthetic: bool,
) -> UniverseSnapshot:
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

    members = []
    for row in records:
        if (
            row["market"] != MARKET
            or row["source"] != IWB_SOURCE
            or date.fromisoformat(row["source_as_of"]) != seed_date
            or row["lifecycle_status"] not in LIFECYCLE_STATES
        ):
            raise ValueError("IWB audit contains an inconsistent market, source, date or lifecycle")
        members.append(UniverseMember(row["symbol"], active=row["lifecycle_status"] == "ACTIVE"))
    if len({member.symbol for member in members}) != count:
        raise ValueError("IWB audit contains duplicate canonical symbols")
    return UniverseSnapshot(seed_date, provenance, tuple(members))
