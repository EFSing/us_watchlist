"""US B shape only, derived from the first-breakout logic in A-share B v1.1."""

from decimal import Decimal

from us_watchlist.domain.models import SessionBar, Signal, StrategyVersion
from us_watchlist.domain.screening import Evaluation
from us_watchlist.strategies.contracts import StrategyInput

HISTORY_SESSIONS = 76


def _shape_reason(bars: list[SessionBar]) -> str:
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    latest = closes[-1]
    for i in range(len(bars) - 15, len(bars) - 1):
        base = max(closes[i - 60:i])
        # 1.8 times the mean of 20 volumes, written as an exact integer comparison.
        if (
            closes[i] <= base
            or 200 * volumes[i] < 18 * sum(volumes[i - 20:i])
            or closes[i] < Decimal("1.03") * closes[i - 1]
        ):
            continue

        pullback_volumes = volumes[i + 1:]
        if (
            base * Decimal("0.97") <= latest <= base * Decimal("1.04")
            and 10 * sum(pullback_volumes) < 7 * volumes[i] * len(pullback_volumes)
            and (latest >= closes[-2] or 5 * latest >= sum(closes[-5:]))
        ):
            return "SHAPE_MATCH"
        return "FIRST_BREAKOUT_RETEST_FAILED"
    return "NO_QUALIFYING_BREAKOUT"


class BreakoutRetestShape:
    version = StrategyVersion("B", "us_breakout_retest_shape_v1")

    def evaluate(self, inputs: StrategyInput) -> tuple[Evaluation, ...]:
        if len(inputs.history) != HISTORY_SESSIONS:
            raise ValueError(f"B expects {HISTORY_SESSIONS} validated sessions")

        by_symbol: dict[str, list[SessionBar]] = {symbol: [] for symbol in inputs.eligible_symbols}
        for snapshot in inputs.history:
            for bar in snapshot.bars:
                by_symbol[bar.symbol].append(bar)

        latest = inputs.history[-1].session
        result = []
        for symbol, bars in by_symbol.items():
            if len(bars) != HISTORY_SESSIONS:
                result.append(Evaluation(symbol, "INCOMPLETE_HISTORY", len(bars)))
                continue
            reason = _shape_reason(bars)
            signal = (
                Signal(symbol, self.version, latest, inputs.cutoff)
                if reason == "SHAPE_MATCH" else None
            )
            result.append(Evaluation(symbol, reason, len(bars), signal))
        return tuple(result)
