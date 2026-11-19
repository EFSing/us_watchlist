"""Read-only results shared between strategy, orchestration and report layers."""

from dataclasses import dataclass
from datetime import date, datetime

from decimal import Decimal

from us_watchlist.domain.models import PriceBasis, Provenance, Signal, StrategyVersion, UniverseSnapshot

Metrics = tuple[tuple[str, str | int | float | Decimal | bool], ...]


@dataclass(frozen=True)
class Evaluation:
    symbol: str
    reason: str
    sessions_available: int
    signal: Signal | None = None
    structure: Metrics = ()
    volume: Metrics = ()
    data_gap: str = ""


@dataclass(frozen=True)
class ScreeningUniverse:
    snapshot: UniverseSnapshot
    holdings_date: date
    seed_count: int
    active_count: int
    status: str


@dataclass(frozen=True)
class IwbReportEvidence:
    inactive: tuple[tuple[str, str], ...]
    non_equity_rows: int
    max_age_days: int
    target_bars: int
    status: str


@dataclass(frozen=True)
class ReplayEvidence:
    trade_date: date
    cutoff: datetime
    mode: str
    candidate_date: date
    seed_date: date
    seed: Provenance
    seed_size: int
    active_size: int
    candidate_size: int
    candidate_status: str
    history: Provenance
    first_session: date
    expected_sessions: int
    calendar_source: str
    price_basis: PriceBasis
    adjustments_known_at: datetime | None
    input_sha256: str
    iwb: IwbReportEvidence | None = None


@dataclass(frozen=True)
class ScreeningResult:
    strategy: StrategyVersion
    evaluations: tuple[Evaluation, ...]
    error: str | None = None
