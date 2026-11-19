"""Load a US regular-session replay manifest and its immutable inputs."""

import csv
import tomllib
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from io import StringIO
from pathlib import Path

from us_watchlist.domain.models import (
    MARKET, MarketSnapshot, PriceBasis, Provenance, SessionBar, SessionKind, SessionWindow,
)
from us_watchlist.integrations.pipeline_iwb import PipelineCandidates, read_pipeline_candidates
from us_watchlist.integrations.yahoo_chart import read_yahoo


@dataclass(frozen=True)
class ReplayInput:
    mode: str
    target_date: date
    cutoff: datetime
    candidates: PipelineCandidates
    history: tuple[MarketSnapshot, ...]
    adjustments_known_at: datetime | None
    input_sha256: str
    calendar_source: str
    symbol_gaps: tuple[tuple[str, str], ...] = ()


def _rows(payload: bytes, columns: tuple[str, ...]):
    rows = csv.DictReader(StringIO(payload.decode("utf-8-sig"), newline=""))
    if rows.fieldnames != list(columns):
        raise ValueError(f"Expected CSV columns: {', '.join(columns)}")
    for row in rows:
        if None in row or None in row.values():
            raise ValueError(f"Incorrect CSV field count at line {rows.line_num}")
        yield row


def _manifest(path: Path) -> tuple[dict, str, PipelineCandidates]:
    payload = path.read_bytes()
    config = tomllib.loads(payload.decode("utf-8"))
    mode = config["mode"]
    if config["market"] != MARKET or mode not in {"synthetic", "offline_replay", "yahoo_observation"}:
        raise ValueError("Expected a US synthetic, offline_replay or yahoo_observation manifest")
    target_date = config["target_date"]
    max_age = config["max_seed_age_days"]
    if type(target_date) is not date or type(max_age) is not int or max_age < 0:
        raise ValueError("Specify target_date and a nonnegative max_seed_age_days")
    if config["session"] != SessionKind.REGULAR:
        raise ValueError("Offline screening accepts only regular sessions")

    iwb = config["iwb"]
    artifact = (path.parent / iwb["file"]).read_bytes()
    candidates = read_pipeline_candidates(
        artifact,
        artifact=iwb["artifact"],
        artifact_sha256=iwb["sha256"],
        uploaded_at=iwb["uploaded_at"],
        synthetic=mode == "synthetic",
    )
    if candidates.snapshot.effective_date > target_date:
        raise ValueError("The Candidate report date follows the target trading date")
    if (target_date - candidates.holdings_date).days > max_age:
        raise ValueError("The IWB holdings date exceeds max_seed_age_days")
    return config, sha256(payload).hexdigest(), candidates


def yahoo_capture_request(path: Path) -> tuple[Path, date, tuple[str, ...], Provenance]:
    config, _, candidates = _manifest(path)
    return _capture_request(path, config, candidates)


def _capture_request(
    path: Path, config: dict, candidates: PipelineCandidates,
) -> tuple[Path, date, tuple[str, ...], Provenance]:
    if config["mode"] != "yahoo_observation" or "cutoff" in config:
        raise ValueError("Yahoo observation requires capture time as the cutoff")
    return (
        path.parent / config["history"]["bundle"], config["target_date"],
        tuple(member.symbol for member in candidates.snapshot.members), candidates.snapshot.provenance,
    )


def read_replay(path: Path) -> ReplayInput:
    config, input_sha, candidates = _manifest(path)
    mode = config["mode"]
    target_date = config["target_date"]
    if mode == "yahoo_observation":
        bundle, _, symbols, provenance = _capture_request(path, config, candidates)
        history, observed, calendar_source, gaps = read_yahoo(
            bundle.read_bytes(), config["history"]["bundle_sha256"], target_date, symbols, provenance,
        )
        return ReplayInput(mode, target_date, observed, candidates, history, None,
                           input_sha, calendar_source, gaps)

    prices = config["history"]
    calendar = (path.parent / prices["calendar"]).read_bytes()
    ohlcv = (path.parent / prices["ohlcv"]).read_bytes()
    calendar_sha = sha256(calendar).hexdigest()
    ohlcv_sha = sha256(ohlcv).hexdigest()
    if (calendar_sha, ohlcv_sha) != (prices["calendar_sha256"], prices["ohlcv_sha256"]):
        raise ValueError("Calendar or OHLCV SHA-256 does not match the manifest")

    windows = []
    entries: dict[date, list[SessionBar]] = {}
    for row in _rows(calendar, ("date", "opens_at", "closes_at", "ohlcv_available_at")):
        day = date.fromisoformat(row["date"])
        if day in entries:
            raise ValueError("Calendar contains a duplicate session date")
        entries[day] = []
        session = SessionWindow(
            day, SessionKind.REGULAR, datetime.fromisoformat(row["opens_at"]),
            datetime.fromisoformat(row["closes_at"]),
        )
        provenance = Provenance(
            prices["source"], f"{ohlcv_sha}/{day}", datetime.fromisoformat(row["ohlcv_available_at"])
        )
        windows.append((session, provenance))

    for row in _rows(ohlcv, ("date", "symbol", "open", "high", "low", "close", "volume")):
        day = date.fromisoformat(row["date"])
        if day not in entries:
            raise ValueError(f"OHLCV date is absent from the expected calendar: {day}")
        entries[day].append(
            SessionBar(
                row["symbol"], Decimal(row["open"]), Decimal(row["high"]),
                Decimal(row["low"]), Decimal(row["close"]), int(row["volume"]),
            )
        )
    basis = PriceBasis(prices["price_basis"])
    history = tuple(
        MarketSnapshot(session, provenance, basis, tuple(entries[session.trading_date]))
        for session, provenance in windows
    )
    return ReplayInput(
        mode, target_date, config["cutoff"], candidates, history,
        prices["adjustments_known_at"], input_sha, prices.get("calendar_source", "Manifest calendar CSV"),
    )
