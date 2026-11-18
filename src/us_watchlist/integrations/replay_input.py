"""Load the local B replay manifest, calendar and session OHLCV."""

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
    UniverseSnapshot,
)
from us_watchlist.integrations.pipeline_iwb import read_iwb_seed


@dataclass(frozen=True)
class ReplayInput:
    mode: str
    target_date: date
    cutoff: datetime
    max_seed_age_days: int
    seed: UniverseSnapshot
    history: tuple[MarketSnapshot, ...]
    adjustments_known_at: datetime
    input_sha256: str


def _rows(payload: bytes, columns: tuple[str, ...]):
    rows = csv.DictReader(StringIO(payload.decode("utf-8-sig"), newline=""))
    if rows.fieldnames != list(columns):
        raise ValueError(f"Expected CSV columns: {', '.join(columns)}")
    for row in rows:
        if None in row or None in row.values():
            raise ValueError(f"Incorrect CSV field count at line {rows.line_num}")
        yield row


def read_replay(path: Path) -> ReplayInput:
    payload = path.read_bytes()
    config = tomllib.loads(payload.decode("utf-8"))
    mode = config["mode"]
    if config["market"] != MARKET or mode not in {"synthetic", "offline_replay"}:
        raise ValueError("B requires a US synthetic or offline_replay manifest")
    target_date = config["target_date"]
    max_age = config["max_seed_age_days"]
    if type(target_date) is not date or type(max_age) is not int or max_age < 0:
        raise ValueError("Specify target_date and a nonnegative max_seed_age_days")
    if config["session"] != SessionKind.REGULAR:
        raise ValueError("B replay accepts only regular sessions")

    iwb = config["iwb"]
    artifact = (path.parent / iwb["file"]).read_bytes()
    seed = read_iwb_seed(
        artifact,
        artifact=iwb["artifact"],
        artifact_sha256=iwb["sha256"],
        uploaded_at=iwb["uploaded_at"],
        synthetic=mode == "synthetic",
    )

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
        mode, target_date, config["cutoff"], max_age, seed, history,
        prices["adjustments_known_at"], sha256(payload).hexdigest(),
    )
