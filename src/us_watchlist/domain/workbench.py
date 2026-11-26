"""Display data for a completed-session watchlist."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from us_watchlist.domain.models import SessionBar
from us_watchlist.domain.replay_research import CandidateResearch
from us_watchlist.domain.screening import Evaluation


@dataclass(frozen=True)
class QuoteSummary:
    symbol: str
    name: str
    english_name: str
    sector: str
    style: str
    market_weight: Decimal | None
    issuer: str
    close: Decimal
    daily_change: Decimal | None


@dataclass(frozen=True)
class Breadth:
    count: int
    sample: int

    @property
    def ratio(self) -> Decimal | None:
        return Decimal(self.count) / self.sample if self.sample else None


@dataclass(frozen=True)
class MarketGroup:
    name: str
    style: str
    sample: int
    daily_median: Decimal | None
    change_20_median: Decimal | None
    above_ma20: Breadth
    b_matches: int


@dataclass(frozen=True)
class MarketPulse:
    eligible: int
    observed: int
    up: int
    down: int
    flat: int
    above_ma20: Breadth
    above_ma60: Breadth
    near_high60: Breadth
    environment: str
    styles: tuple[MarketGroup, ...]
    sectors: tuple[MarketGroup, ...]


@dataclass(frozen=True)
class ChartDay:
    day: date
    bar: SessionBar
    ma20: Decimal | None


@dataclass(frozen=True)
class BCandidate:
    evaluation: Evaluation
    research: CandidateResearch
    quote: QuoteSummary
    platform: Decimal
    retest_ratio: Decimal | None
    position_120: Decimal | None
    chart: tuple[ChartDay, ...]
    risk_to_close: Decimal | None
    supplemental: bool = False
    same_issuer: bool = False

    @property
    def distance_to_platform(self) -> Decimal:
        return self.quote.close / self.platform - 1


@dataclass(frozen=True)
class BWatch:
    quote: QuoteSummary
    platform: Decimal
    distance_to_platform: Decimal
    retest_ratio: Decimal


@dataclass(frozen=True)
class Workbench:
    pulse: MarketPulse
    core: tuple[BCandidate, ...]
    other: tuple[BCandidate, ...]
    watch: tuple[BWatch, ...]
    c_quotes: tuple[QuoteSummary, ...]
