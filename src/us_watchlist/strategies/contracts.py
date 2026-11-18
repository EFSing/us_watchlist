"""Versioned strategy interface receiving only in-memory validated inputs."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from us_watchlist.domain.models import MarketSnapshot, SessionBar, StrategyVersion
from us_watchlist.domain.screening import Evaluation


@dataclass(frozen=True)
class StrategyInput:
    cutoff: datetime
    eligible_symbols: tuple[str, ...]
    history: tuple[MarketSnapshot, ...]
    symbol_gaps: tuple[tuple[str, str], ...] = ()

    def window(self, sessions: int) -> dict[str, tuple[SessionBar | None, ...]]:
        daily = [{bar.symbol: bar for bar in snapshot.bars} for snapshot in self.history[-sessions:]]
        return {symbol: tuple(day.get(symbol) for day in daily) for symbol in self.eligible_symbols}

    def incomplete(
        self, symbol: str, expected: int, series: tuple[SessionBar | None, ...], source_gap: str,
    ) -> Evaluation:
        missing = [snapshot.session.trading_date.isoformat()
                   for snapshot, bar in zip(self.history[-len(series):], series) if bar is None]
        details = [source_gap] if source_gap else []
        if len(series) < expected:
            details.append(f"Only {len(series)} of {expected} expected calendar sessions supplied")
        if missing:
            dates = ", ".join(missing[-5:])
            details.append(f"{len(missing)} missing session(s), latest {dates}")
        return Evaluation(symbol, "INCOMPLETE_HISTORY", len(series) - len(missing), data_gap=" · ".join(details))


class Strategy(Protocol):
    @property
    def version(self) -> StrategyVersion: ...

    def evaluate(self, inputs: StrategyInput) -> tuple[Evaluation, ...]: ...
