"""Causal close decisions for the versioned US research position protocol."""

from collections import deque
from datetime import datetime
from decimal import Decimal


class PositionIndicators:
    """Keep the Wilder accumulator and only the bars needed for pivot confirmation."""

    def __init__(self, model: dict, seeds: list, entry_date: str):
        self.entry_date = entry_date
        self.pivot = model["pivot"]
        trail = model["atr_trail"]
        self.period = trail["period"] if trail else 0
        self.atr = None
        self.previous_close = None
        self.ranges_count = 0
        self.ranges_sum = Decimal(0)
        radius = self.pivot["radius"] if self.pivot else 0
        self.bars = deque(maxlen=2 * radius + 1 if radius else 0)
        self.index = 0
        self.provisional = None
        self.protected_index = None
        for _, prices in seeds[-(self.period + 1):] if self.period else ():
            self._update_atr(tuple(map(Decimal, prices)))
        for day, prices in seeds[-radius:] if radius else ():
            self._append(day, tuple(map(Decimal, prices)))

    def _update_atr(self, prices: tuple) -> None:
        _, high, low, close = prices
        if self.previous_close is not None:
            true_range = max(high - low, abs(high - self.previous_close), abs(low - self.previous_close))
            if self.atr is None:
                self.ranges_count += 1
                self.ranges_sum += true_range
                if self.ranges_count == self.period:
                    self.atr = self.ranges_sum / self.period
            else:
                self.atr = (self.atr * (self.period - 1) + true_range) / self.period
        self.previous_close = close

    def _append(self, day: str, prices: tuple) -> None:
        self.bars.append((self.index, day, prices[1], prices[2]))
        self.index += 1

    def observe(self, day: str, prices: tuple, floor: Decimal | None) -> dict | None:
        if self.period:
            self._update_atr(prices)
        if not self.pivot:
            return None

        self._append(day, prices)
        if len(self.bars) < self.bars.maxlen:
            return None
        bars, radius = list(self.bars), self.pivot["radius"]
        index, pivot_date, high, low = bars[radius]
        if pivot_date <= self.entry_date:
            return None
        left, right = bars[:radius], bars[radius + 1:]
        # Keep the first equal extreme. A bar qualifying in both directions
        # supplies neither leg because daily data cannot order its extremes.
        low_pivot = low < min(bar[3] for bar in left) and low <= min(bar[3] for bar in right)
        high_pivot = high > max(bar[2] for bar in left) and high >= max(bar[2] for bar in right)
        if low_pivot and high_pivot:
            return None

        candidate = None
        rebound_date = None
        if self.pivot["require_rebound"]:
            if low_pivot and (self.provisional is None or low < self.provisional[2]):
                self.provisional = (index, pivot_date, low)
            elif high_pivot and self.provisional is not None:
                if high > self.provisional[2]:
                    candidate, rebound_date = self.provisional, pivot_date
                self.provisional = None
        elif low_pivot:
            candidate = (index, pivot_date, low)

        if candidate is None:
            return None
        index, pivot_date, low = candidate
        if low <= floor or (
            self.protected_index is not None and index - self.protected_index < self.pivot["min_separation"]
        ):
            return None
        self.protected_index = index
        return {"pivot_date": pivot_date, "confirmed_on": day, "price": str(low), "rebound_date": rebound_date}


def close_position(position: dict, indicators: PositionIndicators, day: dict, prices: tuple) -> str:
    model = position["exit_model"]
    if not any(model[key] for key in ("structure_exit", "atr_trail", "profit_protection")):
        return "CLOSE_MARK"
    observed = day["source"]["observed_at"]
    if datetime.fromisoformat(observed) >= datetime.fromisoformat(day["next_opens_at"]):
        return "LATE_CLOSE_EVIDENCE"

    close = prices[3]
    stop = Decimal(position["stop"])
    floor_text = position["structural_floor"]
    floor = Decimal(floor_text) if floor_text is not None else None
    low = indicators.observe(day["trade_date"], prices, floor)
    if low is not None:
        floor = Decimal(low["price"])
        position.update(structural_floor=low["price"], protected_low={**low, "available_at": observed})

    protection = None
    profit = model["profit_protection"]
    if profit is not None:
        entry = Decimal(position["entry"])
        one_r = entry - Decimal(position["initial_stop"])
        maximum_high = Decimal(position["maximum_high"])
        if maximum_high - entry >= Decimal(profit["trigger_r"]) * one_r:
            protection = maximum_high - Decimal(profit["giveback_r"]) * one_r
            position["protection_floor"] = str(protection)

    reasons = []
    if model["structure_exit"] and close < floor:
        reasons.append("STRUCTURE_NEXT_OPEN")
    if protection is not None and close < protection:
        reasons.append("PROFIT_PROTECTION_NEXT_OPEN")
    if reasons:
        position["pending_exit"] = {
            "session": day["next_session"], "confirmed_on": day["trade_date"],
            "available_at": observed, "reasons": reasons,
        }
        return "STRUCTURE_EXIT_ARMED" if reasons[0] == "STRUCTURE_NEXT_OPEN" else "PROFIT_PROTECTION_ARMED"

    candidates = {}
    trail = model["atr_trail"]
    protected = position.get("protected_low")
    atr = indicators.atr
    if trail and protected is not None and atr is not None:
        candidate = Decimal(protected["price"]) - Decimal(trail["multiple"]) * atr
        position["structure_atr"] = str(atr)
        position["structure_stop_candidate"] = str(candidate)
        if stop < candidate < close:
            candidates["STRUCTURE_STOP"] = candidate
    if protection is not None and stop < protection <= close:
        candidates["PROFIT_STOP"] = protection
    if not candidates:
        return "CLOSE_MARK"
    next_stop = max(candidates.values())
    position.update(stop=str(next_stop), stop_sources=[source for source, value in candidates.items() if value == next_stop])
    return "STOP_RAISED_FOR_NEXT_SESSION"
