"""Versioned formulas for B and C reference plans."""

from decimal import ROUND_HALF_EVEN, Decimal

from us_watchlist.domain.models import SessionBar
from us_watchlist.domain.replay_research import PlanObservation, ReferencePlan
from us_watchlist.domain.screening import Metrics

_CENT = Decimal("0.01")
_BUFFER = Decimal("0.98")
_PRESSURE_FLOOR = Decimal("1.03")
_TREND_R = Decimal("2.5")
_C_STOP_RISK_WARNING = Decimal("0.09")
B_REQUIRED_SESSIONS = 120


def _cents(price: Decimal) -> Decimal:
    return price.quantize(_CENT, rounding=ROUND_HALF_EVEN)


def _mean_close(bars: tuple[SessionBar, ...], window: int) -> Decimal:
    return sum(bar.close for bar in bars[-window:]) / window


def _display_plan(
    trigger: Decimal, stop: Decimal, target: Decimal, entry: Decimal, target_rule: str,
) -> ReferencePlan | None:
    rounded_target = _cents(target)
    if not (0 < stop < trigger < rounded_target and stop < entry < rounded_target):
        return None
    rr = (rounded_target - entry) / (entry - stop)
    return ReferencePlan(trigger, stop, rounded_target, entry, rr, target_rule)


def _volume_buckets(bars: tuple[SessionBar, ...]) -> tuple[tuple[Decimal, int], ...]:
    window = bars[-B_REQUIRED_SESSIONS:]
    low, high = min(bar.low for bar in window), max(bar.high for bar in window)
    edges = tuple(low + (high - low) * i / 20 for i in range(1, 20))
    volumes = [0] * 20
    for bar in window:
        # Row volume belongs to the bin of its close; equality goes to the right.
        volumes[sum(bar.close >= edge for edge in edges)] += bar.volume
    return tuple(zip((low, *edges), volumes))


def _b_failure(reason: str, inputs: Metrics = (), *, unavailable: bool = False) -> PlanObservation:
    status = "B_NUMERIC_UNAVAILABLE" if unavailable else "B_NUMERIC_REJECTED"
    return PlanObservation(status, reason, missing_reason=reason, inputs=inputs)


def b_reference_plan(bars: tuple[SessionBar, ...], platform: Decimal | None) -> PlanObservation:
    return _b_plan(bars, platform, None, us_v2=False)


def b_us_reference_plan(
    bars: tuple[SessionBar, ...], platform: Decimal | None, breakout_index: int | None,
) -> PlanObservation:
    return _b_plan(bars, platform, breakout_index, us_v2=True)


def _b_plan(
    bars: tuple[SessionBar, ...], platform: Decimal | None, breakout_index: int | None, *, us_v2: bool,
) -> PlanObservation:
    if len(bars) < B_REQUIRED_SESSIONS:
        return _b_failure("B_HISTORY_LT_120", unavailable=True)
    if platform is None:
        return _b_failure("B_PLATFORM_UNAVAILABLE", unavailable=True)
    if us_v2 and (breakout_index is None or not 60 <= breakout_index < len(bars) - 1):
        return _b_failure("B_BREAKOUT_UNAVAILABLE", unavailable=True)

    close = bars[-1].close
    ma5, ma20 = (_mean_close(bars, window) for window in (5, 20))
    chg10 = (close / bars[-11].close - 1) * 100
    chg20 = (close / bars[-21].close - 1) * 100
    bias20 = (close / ma20 - 1) * 100
    window = bars[-(120 if us_v2 else 250):]
    low = min(bar.low for bar in window)
    high = max(bar.high for bar in window)
    position = (close - low) / (high - low) if high > low else Decimal("0.5")
    inputs: Metrics = (
        ("signal_close", close), ("ma5", ma5), ("ma20", ma20), ("platform", platform),
        ("change_10_pct", chg10), ("change_20_pct", chg20), ("ma20_bias_pct", bias20),
        ("range_position", position), ("range_sessions", len(window)),
    )
    if close <= (5 if us_v2 else 2):
        return _b_failure("B_CLOSE_NOT_ABOVE_US_5" if us_v2 else "B_CLOSE_NOT_ABOVE_NOMINAL_2", inputs)
    if chg10 > (30 if us_v2 else 35) and bias20 > 15:
        return _b_failure("B_ACCELERATION_OVEREXTENDED", inputs)
    if position > (Decimal("0.92") if us_v2 else Decimal("0.9")) and chg20 > (35 if us_v2 else 40):
        return _b_failure("B_GAIN_EXHAUSTED", inputs)

    loud_bar = max(bars[-10:], key=lambda bar: bar.volume)
    low20 = min(bar.low for bar in bars[-20:])
    supports = (ma20, platform, loud_bar.low, low20)
    inputs += (("max_volume_bar_10_low", loud_bar.low), ("low20", low20))
    support = max((value for value in supports if value < close), default=None)
    if support is None:
        return _b_failure("B_NO_SUPPORT_BELOW_CLOSE", inputs)
    trigger, stop = _cents(max(platform, ma5)), _cents(support * _BUFFER)
    entry = max(_cents(close), trigger)
    risk_to_close = (close - stop) / close
    inputs += (("support", support), ("stop_before_rounding", support * _BUFFER), ("risk_to_close", risk_to_close))
    if us_v2:
        risk_to_entry = (entry - stop) / entry
        inputs += (("reference_entry", entry), ("risk_to_entry", risk_to_entry))
        if not (0 < risk_to_close <= Decimal("0.08") and 0 < risk_to_entry <= Decimal("0.08")):
            return _b_failure("B_STOP_DISTANCE_OUTSIDE_RANGE", inputs)
    elif not 0 < risk_to_close <= Decimal("0.09"):
        return _b_failure("B_STOP_DISTANCE_OUTSIDE_RANGE", inputs)

    if breakout_index is None:
        pressure, overhang, strongest, highs = _legacy_pressure(bars, close)
    else:
        pressure, overhang, strongest, highs = _prior_pressure(bars, close, breakout_index)
    target_rule = "B_PRESSURE" if pressure is not None else "B_TREND_2_5R"
    basis = entry if us_v2 else close
    target = pressure if pressure is not None else basis + _TREND_R * (basis - stop)
    rr = (target - close) / (close - stop)
    inputs += (*highs, ("overhang", overhang),
               ("target_before_rounding", target), ("rr_to_unrounded_close", rr), ("target_rule", target_rule))
    if strongest is not None:
        inputs += (("strongest_above_threshold_bin", strongest[0]), ("strongest_bin_volume", strongest[1]))
    plan = _display_plan(trigger, stop, target, entry, target_rule)
    gate_rr = rr
    if us_v2:
        inputs += (("plan_rr", plan.rr if plan is not None else None),)
        if plan is None:
            return PlanObservation(
                "B_NUMERIC_REJECTED", "B_RR_BELOW_TWO_AT_ENTRY", None, "REFERENCE_LEVEL_ORDER_INVALID", inputs,
            )
        gate_rr = plan.rr
    reason = None
    if gate_rr < 2:
        reason = "B_RR_BELOW_TWO_AT_ENTRY" if us_v2 else "B_RR_BELOW_TWO_AT_CLOSE"
    elif overhang > Decimal("0.5") and gate_rr < _TREND_R:
        reason = "B_OVERHANG_WITH_RR_BELOW_2_5"
    return PlanObservation(
        "B_NUMERIC_REJECTED" if reason else "B_NUMERIC_QUALIFIED", reason, plan,
        None if plan else "REFERENCE_LEVEL_ORDER_INVALID", inputs,
    )


def _bucket_overhang(buckets: tuple[tuple[Decimal, int], ...], close: Decimal, total_volume: int) -> Decimal:
    above = sum(volume for price, volume in buckets if price > close * Decimal("1.02"))
    return Decimal(above) / total_volume if total_volume else Decimal(0)


def _legacy_pressure(bars: tuple[SessionBar, ...], close: Decimal):
    buckets = _volume_buckets(bars)
    overhang = _bucket_overhang(buckets, close, sum(volume for _, volume in buckets))
    threshold = close * _PRESSURE_FLOOR
    h60 = max(bar.high for bar in bars[-60:])
    h120 = max(bar.high for bar in bars[-120:])
    strongest = max((bucket for bucket in buckets if bucket[0] > threshold), key=lambda item: item[1], default=None)
    resistance = (h60, h120) if strongest is None else (h60, h120, strongest[0])
    pressure = min((price for price in resistance if price > threshold), default=None)
    return pressure, overhang, strongest, (("high60", h60), ("high120", h120))


def _prior_pressure(bars: tuple[SessionBar, ...], close: Decimal, breakout_index: int):
    prior = bars[-B_REQUIRED_SESSIONS:breakout_index]
    post_high = max(bar.high for bar in bars[breakout_index:])
    highs: Metrics = (("post_breakout_high", post_high),)
    if not prior:
        return None, Decimal(0), None, highs

    prior_high = max(bar.high for bar in prior)
    buckets = _volume_buckets(prior)
    total_volume = sum(volume for _, volume in buckets)
    overhang = _bucket_overhang(buckets, close, total_volume)
    threshold = close * _PRESSURE_FLOOR
    resistance = []
    if prior_high > threshold and prior_high > post_high * Decimal("1.005"):
        resistance.append(prior_high)
    strongest = None
    if overhang >= Decimal("0.15"):
        strongest = max(
            ((price, volume) for price, volume in buckets
             if price > max(threshold, post_high) and 20 * volume >= total_volume),
            key=lambda item: item[1], default=None,
        )
        if strongest is not None:
            resistance.append(strongest[0])
    return min(resistance, default=None), overhang, strongest, (("prior_high", prior_high), *highs)


def c_reference_plan(
    bars: tuple[SessionBar, ...], peak: Decimal | None, support: Decimal | None, rebound: Decimal | None,
) -> PlanObservation:
    if len(bars) < 5 or peak is None or support is None or rebound is None:
        return PlanObservation("C_PRICE_RESEARCH", missing_reason="C_STRUCTURE_OR_MA5_UNAVAILABLE")
    close = bars[-1].close
    ma5 = _mean_close(bars, 5)
    trigger, stop = _cents(max(rebound, ma5)), _cents(support * _BUFFER)
    pressure = peak > close * _PRESSURE_FLOOR
    target_rule = "C_PRIOR_HIGH" if pressure else "C_TREND_2_5R"
    target = peak if pressure else close + _TREND_R * (close - stop)
    inputs: Metrics = (
        ("signal_close", close), ("ma5", ma5), ("prior_high", peak), ("support_floor", support),
        ("rebound_high", rebound), ("stop_before_rounding", support * _BUFFER),
        ("target_before_rounding", target), ("target_rule", target_rule),
    )
    plan = _display_plan(trigger, stop, target, trigger, target_rule)
    if plan is not None:
        risk_to_entry = (plan.entry - plan.stop) / plan.entry
        risk_to_close = (close - plan.stop) / close
        inputs += (
            ("risk_to_entry", risk_to_entry), ("risk_to_close", risk_to_close),
            ("stop_risk_warning_threshold", _C_STOP_RISK_WARNING),
            ("stop_risk_warning", max(risk_to_entry, risk_to_close) > _C_STOP_RISK_WARNING),
        )
    return PlanObservation(
        "C_PRICE_RESEARCH", plan=plan, missing_reason=None if plan else "REFERENCE_LEVEL_ORDER_INVALID", inputs=inputs,
    )
