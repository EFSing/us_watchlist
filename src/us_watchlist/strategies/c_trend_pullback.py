"""US C price-structure research, from the two frozen CN C daily rules."""

from dataclasses import dataclass
from math import log
from statistics import fmean, median
from typing import Callable

from us_watchlist.domain.models import SessionBar, Signal, StrategyVersion
from us_watchlist.domain.screening import Evaluation, Metrics
from us_watchlist.strategies.contracts import StrategyInput

FAST_WINDOW = 20
VOLUME_WINDOW = 20


@dataclass(frozen=True)
class PullbackRule:
    name: str
    trend_window: int
    up_close_fraction: float
    pivot_radius: int
    pivot_separation: int
    maximum_pullback: int
    depth: tuple[float, float]
    support_tolerance: float
    rebound: tuple[float, float]
    resistance_tolerance: float


BALANCED_A = PullbackRule(
    "BALANCED_A", 60, 0.55, 2, 3, 20, (0.03, 0.12), 0.01, (0.02, 0.08), 0.01,
)
CONSERVATIVE_B = PullbackRule(
    "CONSERVATIVE_B", 90, 0.60, 3, 4, 25, (0.04, 0.15), 0.015, (0.02, 0.10), 0.015,
)


def _trend(closes: tuple[float, ...], rule: PullbackRule) -> tuple[bool, Metrics]:
    window = closes[-rule.trend_window:]
    fast, slow = fmean(window[-FAST_WINDOW:]), fmean(window)
    logs = tuple(map(log, window))
    center = (len(logs) - 1) / 2
    average = fmean(logs)
    slope = sum((i - center) * (value - average) for i, value in enumerate(logs)) / sum(
        (i - center) ** 2 for i in range(len(logs))
    )
    fraction = sum(after > before for before, after in zip(window, window[1:])) / (len(window) - 1)
    qualified = closes[-1] > fast > slow and slope > 0 and fraction >= rule.up_close_fraction
    return qualified, (
        ("Trend qualified", qualified), ("MA20", fast), ("Slow MA", slow),
        ("Log slope per session", slope), ("Up-close fraction", fraction),
    )


def _pivots(
    values: tuple[float, ...], radius: int, extreme: Callable[[tuple[float, ...]], float],
) -> tuple[int, ...]:
    return tuple(
        index for index in range(radius, len(values) - radius)
        if values[index] == extreme(values[index - radius:index + radius + 1])
    )


@dataclass(frozen=True)
class Pullback:
    peak: int
    low_one: int
    low_two: int
    rebound: int
    depth: float
    rebound_size: float


def _pullback(
    highs: tuple[float, ...], lows: tuple[float, ...], rule: PullbackRule,
) -> tuple[Pullback | None, str]:
    # All pivots and their right confirmation periods end by T-1.
    target = len(highs) - 1
    high_pivots = _pivots(highs[:-1], rule.pivot_radius, max)
    low_pivots = _pivots(lows[:-1], rule.pivot_radius, min)
    pairs = (
        (first, second)
        for position, second in reversed(tuple(enumerate(low_pivots)))
        for first in reversed(low_pivots[:position])
        if second - first >= rule.pivot_separation and lows[second] > lows[first]
    )
    reason = "NO_DISTINCT_HIGHER_LOW_PAIR"
    for first, second in pairs:
        if reason == "NO_DISTINCT_HIGHER_LOW_PAIR":
            reason = "NO_PRE_PULLBACK_PEAK"
        peak = next((index for index in reversed(high_pivots) if index < first), None)
        if peak is None:
            continue
        if reason == "NO_PRE_PULLBACK_PEAK":
            reason = "PULLBACK_DEPTH_OUTSIDE_CANDIDATE"
        if target - peak > rule.maximum_pullback + 2 * rule.pivot_radius:
            continue
        depth = (highs[peak] - min(lows[peak + 1:target])) / highs[peak]
        if not rule.depth[0] <= depth <= rule.depth[1]:
            continue
        reason = "NO_CONFIRMED_REBOUND_HIGH"
        rebound = next((index for index in reversed(high_pivots) if index > second), None)
        if rebound is None:
            continue
        rebound_size = (highs[rebound] - lows[second]) / lows[second]
        if rule.rebound[0] <= rebound_size <= rule.rebound[1]:
            return Pullback(peak, first, second, rebound, depth, rebound_size), "OK"
    return None, reason


def _relative_volume(volumes: tuple[int, ...]) -> Metrics:
    baseline = volumes[-VOLUME_WINDOW - 1:-1]
    middle = median(baseline)
    mad = median(abs(vol - middle) for vol in baseline)
    ratio = volumes[-1] / middle if middle else None
    z_score = (volumes[-1] - middle) / (1.4826 * mad) if mad else None
    return (
        ("RV_T", ratio if ratio is not None else "ZERO_BASELINE"),
        ("RV_T ≥ 2", ratio is not None and ratio >= 2.0),
        ("Robust volume z", z_score if z_score is not None else "ZERO_MAD"),
        ("Robust volume z ≥ 3", z_score is not None and z_score >= 3.0),
    )


def _volume_path(closes: tuple[float, ...], volumes: tuple[int, ...], start: int) -> Metrics:
    pullback = volumes[start:-1]
    reference = volumes[max(0, start - VOLUME_WINDOW):start]
    baseline = median(reference)
    ratio = median(pullback) / baseline if baseline else None
    if ratio is None:
        path = "UNDETERMINED"
    elif ratio <= 0.80:
        path = "CONTRACTED_OBSERVABLE"
    elif ratio >= 1.20:
        path = "EXPANDED_OBSERVABLE"
    else:
        path = "MIXED_OBSERVABLE"
    midpoint = (len(pullback) + 1) // 2
    first = median(pullback[:midpoint])
    half_ratio = median(pullback[midpoint:]) / first if first and pullback[midpoint:] else "UNAVAILABLE"
    up, down = [], []
    for i in range(start, len(closes) - 1):
        if closes[i] > closes[i - 1]:
            up.append(volumes[i])
        elif closes[i] < closes[i - 1]:
            down.append(volumes[i])
    if min(len(up), len(down)) < 2:
        directional = "INSUFFICIENT_DIRECTIONAL_DAYS"
    elif not median(down):
        directional = "ZERO_DOWN_DIRECTIONAL_VOLUME"
    else:
        directional = median(up) / median(down)
    return (
        ("Pullback / baseline median volume", ratio if ratio is not None else "ZERO_REFERENCE_VOLUME"),
        ("Pullback volume path", path), ("Second / first half median volume", half_ratio),
        ("Up / down median volume", directional), ("Up days", len(up)), ("Down days", len(down)),
    )


def _screen(
    bars: tuple[SessionBar, ...], dates: tuple[str, ...], rule: PullbackRule,
) -> tuple[str, Metrics, Metrics]:
    closes = tuple(float(bar.close) for bar in bars)
    highs = tuple(float(bar.high) for bar in bars)
    lows = tuple(float(bar.low) for bar in bars)
    volumes = tuple(bar.volume for bar in bars)
    trend_ok, trend = _trend(closes, rule)
    pullback, structural_status = _pullback(highs, lows, rule)
    volume = _relative_volume(volumes)
    if pullback is None:
        return structural_status, trend, volume

    floor, ceiling = lows[pullback.low_one], lows[pullback.low_two]
    start = pullback.peak + 1
    close_t, open_t = closes[-1], float(bars[-1].open)
    prior_close_break = any(close < floor for close in closes[start:-1])
    if close_t < floor:
        support = "T_CLOSE_BREAK"
    elif prior_close_break:
        support = "PULLBACK_SUPPORT_DESTROYED"
    elif lows[-1] < floor:
        support = "T_INTRADAY_PUNCTURE_RECOVERED"
    elif any(low < floor for low in lows[start:-1]):
        support = "PULLBACK_INTRADAY_PUNCTURE_RECOVERED"
    else:
        support = "INTACT"
    support_ok = close_t >= floor and not prior_close_break

    span = highs[-1] - lows[-1]
    location = (close_t - lows[-1]) / span if span else float(close_t >= open_t)
    confirmation = close_t > max(highs[pullback.rebound], closes[-2], open_t) and location >= 0.60
    peak_high = highs[pullback.peak]
    resistance_distance = peak_high / close_t - 1.0
    structure = trend + (
        ("Peak date", dates[pullback.peak]), ("Prior high", peak_high), ("Pullback depth", pullback.depth),
        ("First low date", dates[pullback.low_one]), ("Second low date", dates[pullback.low_two]),
        ("Support floor", floor), ("Support ceiling", ceiling), ("Support status", support),
        ("Support display buffer", floor * rule.support_tolerance),
        ("Rebound date", dates[pullback.rebound]), ("Rebound high", highs[pullback.rebound]),
        ("Rebound size", pullback.rebound_size), ("T close location", location), ("Confirmation", confirmation),
        ("Stage resistance distance", resistance_distance),
        ("Near stage resistance", 0 <= resistance_distance <= rule.resistance_tolerance),
    )
    if not trend_ok:
        reason = "TREND_NOT_QUALIFIED"
    elif not support_ok:
        reason = support
    elif not confirmation:
        reason = "REBOUND_NOT_CONFIRMED"
    else:
        reason = "TREND_PULLBACK_REBOUND_SUPPORT_MATCH"
    return reason, structure, volume + _volume_path(closes, volumes, start)


class TrendPullback:
    def __init__(self, rule: PullbackRule):
        self.rule = rule
        self.version = StrategyVersion(f"C · {rule.name}", f"us_c_trend_pullback_{rule.name.lower()}_v1")

    def evaluate(self, inputs: StrategyInput) -> tuple[Evaluation, ...]:
        latest = inputs.history[-1].session
        dates = tuple(snapshot.session.trading_date.isoformat() for snapshot in inputs.history)
        source_gaps = dict(inputs.symbol_gaps)
        required = self.rule.trend_window
        result = []
        for symbol, series in inputs.window(len(dates)).items():
            bars = []
            for bar in reversed(series):
                if bar is None:
                    break
                bars.append(bar)
            if len(bars) < required:
                result.append(inputs.incomplete(symbol, required, series[-required:], source_gaps.get(symbol, "")))
                continue
            reason, structure, volume = _screen(tuple(reversed(bars)), dates[-len(bars):], self.rule)
            signal = (Signal(symbol, self.version, latest, inputs.cutoff)
                      if reason == "TREND_PULLBACK_REBOUND_SUPPORT_MATCH" else None)
            result.append(Evaluation(symbol, reason, len(bars), signal, structure, volume))
        return tuple(result)
