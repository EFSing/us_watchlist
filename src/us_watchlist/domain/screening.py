"""Read-only results shared between strategy, orchestration and report layers."""

from dataclasses import dataclass
from datetime import date, datetime

from us_watchlist.domain.models import Provenance, Signal, StrategyVersion


@dataclass(frozen=True)
class Evaluation:
    symbol: str
    reason: str
    sessions_available: int
    signal: Signal | None = None


@dataclass(frozen=True)
class ScreeningReport:
    trade_date: date
    cutoff: datetime
    mode: str
    strategy: StrategyVersion
    seed_date: date
    seed: Provenance
    seed_size: int
    history_source: str
    adjustments_known_at: datetime
    input_sha256: str
    evaluations: tuple[Evaluation, ...]
