"""Versioned US B rules over a common first-breakout evaluator."""

from dataclasses import dataclass
from decimal import Decimal

from us_watchlist.domain.models import SessionBar, Signal, StrategyVersion
from us_watchlist.domain.screening import B_SHAPE_V1, B_US_V2, Evaluation, Metrics
from us_watchlist.strategies.contracts import StrategyInput

HISTORY_SESSIONS = 76


@dataclass(frozen=True)
class BreakoutRule:
    version: StrategyVersion
    breakout_volume: Decimal
    min_change: Decimal
    max_change: Decimal
    atr_multiple: Decimal
    retest_upper: Decimal
    retest_volume: Decimal
    ma50_floor: Decimal | None = None
    max_drawdown: Decimal | None = None


SHAPE_V1 = BreakoutRule(
    StrategyVersion("B", B_SHAPE_V1), Decimal("1.8"), Decimal("0.03"), Decimal("0.03"),
    Decimal(0), Decimal("1.04"), Decimal("0.7"),
)
US_B_V2 = BreakoutRule(
    StrategyVersion("B", B_US_V2), Decimal("1.5"), Decimal("0.02"), Decimal("0.04"),
    Decimal("0.75"), Decimal("1.045"), Decimal("0.75"), Decimal("0.995"), Decimal("0.10"),
)


def _minimum_change(bars: tuple[SessionBar, ...], i: int, rule: BreakoutRule) -> Decimal:
    if not rule.atr_multiple:
        return rule.min_change
    true_range = sum(
        max(bars[k].high - bars[k].low, abs(bars[k].high - bars[k - 1].close),
            abs(bars[k].low - bars[k - 1].close))
        for k in range(i - 14, i)
    )
    atr_pct = (true_range / Decimal(14)) / bars[i - 1].close
    return max(rule.min_change, min(rule.max_change, rule.atr_multiple * atr_pct))


def _turn(closes: list[Decimal], end: int) -> bool:
    return closes[end - 1] >= closes[end - 2] or 5 * closes[end - 1] >= sum(closes[end - 5:end])


def _shape(
    bars: tuple[SessionBar, ...], dates: tuple[str, ...], rule: BreakoutRule,
) -> tuple[str, Metrics, Metrics]:
    closes = [bar.close for bar in bars]
    volumes = [bar.volume for bar in bars]
    latest = closes[-1]
    breakout_num, breakout_den = rule.breakout_volume.as_integer_ratio()
    retest_num, retest_den = rule.retest_volume.as_integer_ratio()
    for i in range(len(bars) - 15, len(bars) - 1):
        base = max(closes[i - 60:i])
        baseline = sum(volumes[i - 20:i])
        if closes[i] <= base or breakout_den * 20 * volumes[i] < breakout_num * baseline:
            continue
        required = _minimum_change(bars, i, rule)
        if rule.atr_multiple:
            change_ok = closes[i] / closes[i - 1] - 1 >= required
        else:
            change_ok = closes[i] >= (1 + required) * closes[i - 1]
        if not change_ok:
            continue

        pullback_volumes = volumes[i + 1:]
        near = base * Decimal("0.97") <= latest <= base * rule.retest_upper
        turn = _turn(closes, len(closes))
        contracted = retest_den * sum(pullback_volumes) < retest_num * volumes[i] * len(pullback_volumes)
        trend_ok, controlled_ok = True, True
        if rule.ma50_floor is not None:
            ma50 = sum(closes[-50:]) / Decimal(50)
            ma50_prev5 = sum(closes[-55:-5]) / Decimal(50)
            trend_ok = latest > ma50 and ma50 >= ma50_prev5 * rule.ma50_floor
        if rule.max_drawdown is not None:
            peak = max(closes[i:])
            controlled_ok = (peak - min(closes[i + 1:])) / peak <= rule.max_drawdown
        matched = near and contracted and turn and trend_ok and controlled_ok
        reason = "SHAPE_MATCH" if matched else "FIRST_BREAKOUT_RETEST_FAILED"
        structure = (
            ("Breakout date", dates[i]), ("Platform", base), ("Close / platform", latest / base),
            ("Near platform", near), ("Turn strength", turn),
        )
        if rule.version.version == B_US_V2:
            fresh_turn = i + 1 == len(bars) - 1 or not _turn(closes, len(closes) - 1)
            structure += (
                ("Trend MA50", trend_ok), ("Controlled pullback", controlled_ok),
                ("Fresh turn", fresh_turn), ("Breakout min change", required),
            )
        # V1 retains the original JSON number representation of the displayed ratios.
        numerator = Decimal if rule.version.version == B_US_V2 else int
        volume = (
            ("Breakout volume / prior 20d mean", numerator(20 * volumes[i]) / baseline if baseline else "Zero baseline"),
            ("Retest mean volume / breakout", numerator(sum(pullback_volumes)) / (len(pullback_volumes) * volumes[i])
             if volumes[i] else "Zero breakout volume"),
            ("Retest contracted", contracted),
        )
        return reason, structure, volume
    return "NO_QUALIFYING_BREAKOUT", (), ()


class BreakoutRetestShape:
    version = SHAPE_V1.version

    def __init__(self, rule: BreakoutRule = SHAPE_V1):
        self.rule = rule
        self.version = rule.version

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
            reason, structure, volume = _shape(bars, dates, self.rule)
            signal = (
                Signal(symbol, self.version, latest, inputs.cutoff)
                if reason == "SHAPE_MATCH" else None
            )
            result.append(Evaluation(symbol, reason, len(bars), signal, structure, volume))
        return tuple(result)
