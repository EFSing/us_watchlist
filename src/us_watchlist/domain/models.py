"""Immutable values shared by the US equities layers."""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

MARKET = "US"


class SessionKind(StrEnum):
    REGULAR = "regular"
    PRE_MARKET = "pre_market"
    AFTER_HOURS = "after_hours"
    IBKR_OVERNIGHT = "ibkr_overnight"


class PriceBasis(StrEnum):
    RAW = "raw"
    ADJUSTED = "adjusted"
    SPLIT_ADJUSTED = "split_adjusted"


def require_utc(value: datetime) -> None:
    if not isinstance(value, datetime) or value.utcoffset() != timedelta(0):
        raise ValueError("Timestamps must use UTC")


def require_symbol(symbol: str) -> None:
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*", symbol):
        raise ValueError(f"Invalid canonical US ticker: {symbol!r}")


@dataclass(frozen=True)
class SessionWindow:
    trading_date: date
    kind: SessionKind
    opens_at: datetime
    closes_at: datetime

    def __post_init__(self) -> None:
        if type(self.trading_date) is not date:
            raise ValueError("Trading date must be a calendar date")
        require_utc(self.opens_at)
        require_utc(self.closes_at)
        if self.opens_at >= self.closes_at:
            raise ValueError("Session open must precede session close")


@dataclass(frozen=True)
class Provenance:
    source: str
    snapshot_id: str
    available_at: datetime

    def __post_init__(self) -> None:
        require_utc(self.available_at)
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (self.source, self.snapshot_id)
        ):
            raise ValueError("Source and snapshot identity are required")


@dataclass(frozen=True)
class UniverseMember:
    symbol: str
    active: bool

    def __post_init__(self) -> None:
        require_symbol(self.symbol)
        if type(self.active) is not bool:
            raise ValueError("Member status must be a boolean")


@dataclass(frozen=True)
class UniverseSnapshot:
    effective_date: date
    provenance: Provenance
    members: tuple[UniverseMember, ...]

    def __post_init__(self) -> None:
        if type(self.effective_date) is not date:
            raise ValueError("Universe effective date must be a calendar date")


@dataclass(frozen=True)
class SessionBar:
    symbol: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int

    def __post_init__(self) -> None:
        require_symbol(self.symbol)
        prices = (self.open, self.high, self.low, self.close)
        if any(not price.is_finite() or price <= 0 for price in prices):
            raise ValueError("OHLC prices must be finite and positive")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Inconsistent OHLC range")
        if type(self.volume) is not int or self.volume < 0:
            raise ValueError("Volume must be a nonnegative integer")


@dataclass(frozen=True)
class MarketSnapshot:
    session: SessionWindow
    provenance: Provenance
    price_basis: PriceBasis
    bars: tuple[SessionBar, ...]


@dataclass(frozen=True)
class StrategyVersion:
    name: str
    version: str


@dataclass(frozen=True)
class Signal:
    """A strategy candidate at a specified cutoff."""

    symbol: str
    strategy: StrategyVersion
    session: SessionWindow
    known_at: datetime

    def __post_init__(self) -> None:
        require_symbol(self.symbol)
        require_utc(self.known_at)
        if self.known_at < self.session.closes_at:
            raise ValueError("Signal cutoff must follow the completed input session")


@dataclass(frozen=True)
class RunObservation:
    """Read-only projection of the inputs used for a single smoke run."""

    session: SessionWindow
    cutoff: datetime
    universe: Provenance
    prices: Provenance
    price_basis: PriceBasis
    eligible_symbols: tuple[str, ...]
    observed_symbols: tuple[str, ...]

    @property
    def missing_symbols(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.eligible_symbols) - set(self.observed_symbols)))
