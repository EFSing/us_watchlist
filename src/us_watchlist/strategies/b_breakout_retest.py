"""US B shape only, derived from the first-breakout logic in A-share B v1.1."""

from decimal import Decimal

from us_watchlist.domain.models import SessionBar, Signal, StrategyVersion
from us_watchlist.domain.screening import Evaluation, Metrics
from us_watchlist.strategies.contracts import StrategyInput

HISTORY_SESSIONS = 76


def _shape(
    bars: tuple[SessionBar, ...], dates: tuple[str, ...],
) -> tuple[str, Metrics, Metrics]:
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    latest = closes[-1]
    for i in range(len(bars) - 15, len(bars) - 1):
        base = max(closes[i - 60:i])
        baseline = sum(volumes[i - 20:i])
        # 1.8 times the mean of 20 volumes, written as an exact integer comparison.
        if (
            closes[i] <= base
            or 200 * volumes[i] < 18 * baseline
            or closes[i] < Decimal("1.03") * closes[i - 1]
        ):
            continue

        pullback_volumes = volumes[i + 1:]
        near = base * Decimal("0.97") <= latest <= base * Decimal("1.04")
        turn = latest >= closes[-2] or 5 * latest >= sum(closes[-5:])
        contracted = 10 * sum(pullback_volumes) < 7 * volumes[i] * len(pullback_volumes)
        reason = "SHAPE_MATCH" if near and contracted and turn else "FIRST_BREAKOUT_RETEST_FAILED"
        structure = (
            ("Breakout date", dates[i]), ("Platform", base), ("Close / platform", latest / base),
            ("Near platform", near), ("Turn strength", turn),
        )
        volume = (
            ("Breakout volume / prior 20d mean", 20 * volumes[i] / baseline if baseline else "Zero baseline"),
            ("Retest mean volume / breakout", sum(pullback_volumes) / (len(pullback_volumes) * volumes[i])
             if volumes[i] else "Zero breakout volume"),
            ("Retest contracted", contracted),
        )
        return reason, structure, volume
    return "NO_QUALIFYING_BREAKOUT", (), ()


class BreakoutRetestShape:
    version = StrategyVersion("B", "us_breakout_retest_shape_v1")

    def evaluate(self, inputs: StrategyInput) -> tuple[Evaluation, ...]:
        latest = inputs.history[-1].session
        dates = tuple(s.session.trading_date.isoformat() for s in inputs.history[-HISTORY_SESSIONS:])
        source_gaps = dict(inputs.symbol_gaps)
        result = []
        for symbol, series in inputs.window(HISTORY_SESSIONS).items():
            bars = tuple(bar for bar in series if bar is not None)
            if len(bars) < HISTORY_SESSIONS:
                result.append(inputs.incomplete(symbol, HISTORY_SESSIONS, series, source_gaps.get(symbol, "")))
                continue
            reason, structure, volume = _shape(bars, dates)
            signal = (
                Signal(symbol, self.version, latest, inputs.cutoff)
                if reason == "SHAPE_MATCH" else None
            )
            result.append(Evaluation(symbol, reason, len(bars), signal, structure, volume))
        return tuple(result)
