"""Versioned strategy interface receiving only in-memory validated inputs."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from us_watchlist.domain.models import MarketSnapshot, StrategyVersion
from us_watchlist.domain.screening import Evaluation


@dataclass(frozen=True)
class StrategyInput:
    cutoff: datetime
    eligible_symbols: tuple[str, ...]
    history: tuple[MarketSnapshot, ...]


class Strategy(Protocol):
    @property
    def version(self) -> StrategyVersion: ...

    def evaluate(self, inputs: StrategyInput) -> tuple[Evaluation, ...]: ...
