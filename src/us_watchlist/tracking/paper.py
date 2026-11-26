"""Deterministic research-only opening fills, daily marks and stop exits."""

from collections import Counter
from datetime import datetime
from decimal import Decimal
from hashlib import sha256

from us_watchlist.domain.paper import (
    B_VERSION, POSITION_PROTOCOL, PROTOCOL, RETIRED_STRATEGIES, STRATEGIES, Status, cohort, needs_structure,
)
from us_watchlist.tracking.paper_position import PositionIndicators, close_position

# From the reference Paper Tracking position replay. Prices from today's
# range can change tomorrow's stop, or schedule an exit for tomorrow's open.
_MFE_TRIGGER_R = Decimal(2)
_MFE_GIVEBACK_R = Decimal(1)


def active_plans(records: dict):
    return (row for row in records.values() if row["status"] in (Status.PENDING, Status.OPEN))


def _event(row: dict, day: dict, status: Status, reason: str, **details) -> None:
    row["status"] = status
    row["history"].append({
        "trade_date": day["trade_date"], "observed_at": day["source"]["observed_at"],
        "input_sha256": day["source"]["input_sha256"], "protocol": row["plan"].get("protocol", PROTOCOL),
        "status": status, "reason": reason, **details,
    })


def _open_check(plan: dict, opening: Decimal, policy: dict) -> tuple[Status, str, dict]:
    levels = plan["levels"]
    trigger, stop, target, reference = (Decimal(levels[key]) for key in ("trigger", "stop", "target", "entry"))
    facts = {"opening": str(opening)}
    if opening <= stop:
        return Status.NOT_FILLED, "OPEN_AT_OR_BELOW_STOP", facts
    if opening < trigger:
        return Status.NOT_FILLED, "OPEN_BELOW_TRIGGER", facts
    if opening >= target:
        return Status.NOT_FILLED, "OPEN_AT_OR_ABOVE_TARGET", facts

    actual_rr = (target - opening) / (opening - stop)
    upside = (target - opening) / opening
    premium = (opening - reference) / reference
    facts.update(actual_rr=str(actual_rr), target_upside=str(upside), open_premium=str(premium))
    if not policy:
        return Status.UNAVAILABLE, "ENTRY_POLICY_UNSET", facts
    rule = policy.get(plan["strategy_version"], {}).get(cohort(plan))
    if rule is None:
        return Status.NOT_FILLED, "COHORT_NOT_ENABLED", facts
    model = rule["exit_model"]
    if plan.get("protocol") == POSITION_PROTOCOL and needs_structure(model):
        origin = plan["structure_origin"]
        if origin is None:
            return Status.UNAVAILABLE, "POSITION_STRUCTURE_UNAVAILABLE", facts
        floor = Decimal(origin["points"][origin["floor_anchor"]][1])
        if model["reject_open_at_or_below_structure"] and opening <= floor:
            return Status.NOT_FILLED, "OPEN_AT_OR_BELOW_STRUCTURE", facts
    for key, actual, compare, reason in (
        ("max_open_premium", premium, Decimal.__gt__, "OPEN_ABOVE_CONFIGURED_PREMIUM"),
        ("min_target_upside", upside, Decimal.__lt__, "TARGET_UPSIDE_BELOW_CONFIGURED_MINIMUM"),
        ("min_actual_rr", actual_rr, Decimal.__lt__, "RR_BELOW_CONFIGURED_MINIMUM"),
    ):
        if rule[key] is not None and compare(actual, Decimal(rule[key])):
            return Status.NOT_FILLED, reason, facts
    return Status.OPEN, "FILLED_AT_T1_OPEN", {**facts, "exit_model": model}


def _mark(row: dict, day: dict, quote: dict, opening: Decimal, high: Decimal, low: Decimal, close: Decimal) -> None:
    position = row["position"]
    versioned = row["plan"].get("protocol") == POSITION_PROTOCOL
    pending_exit = position.get("pending_exit")
    entry = Decimal(position["entry"])
    stop = Decimal(position["stop"])
    target = Decimal(row["plan"]["levels"]["target"])
    one_r = entry - Decimal(position["initial_stop"])
    price, upper, lower = close, high, low
    status, reason = Status.OPEN, "CLOSE_MARK"
    if pending_exit is not None:
        if pending_exit["session"] != day["trade_date"]:
            raise ValueError("PAPER_EXPECTED_EXIT_SESSION_MISMATCH")
        price = upper = lower = opening
        status, reason = Status.CLOSED, pending_exit["reasons"][0]
    elif position.get("exit_next_open"):
        price = upper = lower = opening
        status, reason = Status.CLOSED, "PROFIT_PROTECTION_NEXT_OPEN"
    elif opening <= stop:
        price = upper = lower = opening
        status, reason = Status.CLOSED, "GAP_THROUGH_STOP"
    elif low <= stop:
        price, upper, lower = stop, opening, stop
        status, reason = Status.CLOSED, "ACTIVE_STOP_TOUCHED" if versioned else "FIXED_STOP_TOUCHED"
    # On a stop day, only the open and the simulated stop execution are
    # ordered. Daily extremes after the exit cannot affect excursions.
    change = price - entry
    mfe_r = max(Decimal(position["mfe_r"]), (upper - entry) / one_r)
    position = {
        **position, "latest_price": str(price), "priced_on": day["trade_date"],
        "pnl_per_unit": str(change), "return": str(change / entry), "r": str(change / one_r),
        "mfe_r": str(mfe_r),
        "mae_r": str(min(Decimal(position["mae_r"]), (lower - entry) / one_r)),
        "target_seen": position["target_seen"] or (upper >= target and (not versioned or status == Status.OPEN)),
    }
    if not versioned or status == Status.OPEN:
        position["anchor"] = quote["current"]
    if not versioned:
        position["structure"] = quote["structures"].get(row["plan"]["strategy_version"], "STRUCTURE_NOT_AVAILABLE")
    if versioned:
        position.update(
            active_stop_at_open=str(stop), active_stop_sources=position["stop_sources"],
            maximum_high=str(max(Decimal(position["maximum_high"]), upper)),
            max_mfe_drawdown_r=str(max(Decimal(position["max_mfe_drawdown_r"]), mfe_r - change / one_r)),
            structure_stop_candidate=None, structure_atr=None, next_stop_session=None,
        )
    if status == Status.CLOSED:
        position.update(exit_date=day["trade_date"], exit_price=str(price), exit_reason=reason)
        if versioned:
            reasons = list(pending_exit["reasons"]) if pending_exit else [reason]
            if pending_exit and opening <= stop:
                reasons.append("GAP_THROUGH_STOP")
            position.update(exit_reasons=reasons, pending_exit=None)
            del row["_indicators"]
    elif versioned:
        reason = close_position(position, row["_indicators"], day, (opening, high, low, close))
        if reason == "LATE_CLOSE_EVIDENCE":
            row["suspended_at"] = day["trade_date"]
        else:
            position["structure"] = quote["structures"].get(row["plan"]["strategy_version"], "STRUCTURE_NOT_AVAILABLE")
            position["next_stop_session"] = day["next_session"]
    elif position["exit_model"] == "LEGACY_R_PROTECTION" and mfe_r >= _MFE_TRIGGER_R:
        floor = entry + (mfe_r - _MFE_GIVEBACK_R) * one_r
        if close < floor:
            position.update(exit_next_open=True, protection_floor=str(floor))
            reason = "PROFIT_PROTECTION_ARMED"
        elif floor > stop:
            position.update(stop=str(floor), protection_floor=str(floor))
            reason = "STOP_RAISED_FOR_NEXT_SESSION"
    row["position"] = position
    details = {"observation": Status.UNAVAILABLE} if reason == "LATE_CLOSE_EVIDENCE" else {}
    _event(row, day, status, reason, position=position, **details)


def _advance(row: dict, day: dict, policy: dict) -> None:
    plan = row["plan"]
    pending = row["status"] == Status.PENDING
    quote = day["quotes"][plan["symbol"]]
    anchor = plan["anchor"] if pending else row["position"]["anchor"]
    current, previous = quote["current"], quote["previous"]
    reason = None
    if pending and day["trade_date"] != plan["expected_entry"]:
        raise ValueError("PAPER_EXPECTED_T1_SESSION_MISMATCH")
    if pending and datetime.fromisoformat(plan["created_at"]) >= datetime.fromisoformat(day["opens_at"]):
        reason = "SIGNAL_NOT_KNOWN_BEFORE_T1_OPEN"
    elif row.get("suspended_at"):
        reason = "UNRESOLVED_PRIOR_GAP"
    elif current is None or previous is None:
        reason = "MISSING_OR_SPLIT_UNVERIFIED_YAHOO_BAR"
    elif tuple(map(Decimal, previous)) != tuple(map(Decimal, anchor)):
        reason = "PRIOR_PRICE_BASIS_CHANGED"
    if reason:
        if not pending:
            row.setdefault("suspended_at", day["trade_date"])
        _event(row, day, Status.UNAVAILABLE if pending else Status.OPEN, reason,
               observation=Status.UNAVAILABLE, diagnostic=quote["diagnostic"])
        return

    opening, high, low, close = map(Decimal, current)
    if pending:
        status, reason, facts = _open_check(plan, opening, policy)
        _event(row, day, status, reason, **facts)
        if status != Status.OPEN:
            return
        stop = plan["levels"]["stop"]
        row["position"] = {
            "entry_date": day["trade_date"], "entry": str(opening), "units": 1,
            "initial_stop": stop, "stop": stop, "initial_rr": facts["actual_rr"],
            "exit_model": facts["exit_model"], "exit_next_open": False,
            "mfe_r": "0", "mae_r": "0", "target_seen": False,
        }
        if plan.get("protocol") == POSITION_PROTOCOL:
            origin = plan["structure_origin"]
            floor = origin["points"][origin["floor_anchor"]][1] if origin is not None else None
            row["position"].pop("exit_next_open")
            row["position"].update(
                initial_structural_floor=floor, structural_floor=floor, pending_exit=None,
                stop_sources=["INITIAL_STOP"], maximum_high=str(opening), max_mfe_drawdown_r="0",
                structure=plan["structure"]["stage"],
            )
            row["_indicators"] = PositionIndicators(facts["exit_model"], plan["seeds"], day["trade_date"])
    _mark(row, day, quote, opening, high, low, close)


def apply_day(records: dict, day: dict, study_id: str, policy: dict, protocol: str = PROTOCOL) -> None:
    """Advance exact successive sessions before adding newly discovered plans."""
    for row in active_plans(records):
        _advance(row, day, policy)
    for candidate in day["candidates"]:
        symbol, version = candidate["symbol"], candidate["strategy_version"]
        plan_id = sha256(f"{study_id}/{day['trade_date']}/{version}/{symbol}".encode()).hexdigest()
        if plan_id in records:
            raise ValueError(f"PAPER_PLAN_IDENTITY_CONFLICT {plan_id}")
        plan = {
            **candidate, "plan_id": plan_id, "signal_date": day["trade_date"], "expected_entry": day["next_session"],
            "created_at": day["source"]["observed_at"], "source": day["source"],
            "anchor": day["quotes"][symbol]["current"],
        }
        if protocol == POSITION_PROTOCOL:
            plan.update(protocol=protocol, seeds=day["seeds"].get(symbol, []))
        plan["simulation_eligibility"] = (
            "NO_REFERENCE_LEVELS" if not plan["levels"] else "POLICY_UNSET" if not policy
            else "CONDITIONAL_T1" if cohort(plan) in policy.get(version, {}) else "COHORT_NOT_ENABLED"
        )
        row = {"plan": plan, "history": [], "position": None}
        records[plan_id] = row
        if not plan["levels"]:
            _event(row, day, Status.UNAVAILABLE, "REFERENCE_LEVELS_UNAVAILABLE",
                   diagnostic=plan["reference_missing_reason"])
        elif plan["anchor"] is None:
            _event(row, day, Status.UNAVAILABLE, "SIGNAL_PRICE_BASIS_UNAVAILABLE",
                   diagnostic=day["quotes"][symbol]["diagnostic"])
        else:
            _event(row, day, Status.PENDING, "PLAN_CREATED")


def summarize(records: dict, *, include_empty_retired: bool = False) -> list[dict]:
    groups = {version: [] for version in STRATEGIES}
    planned = {row["plan"]["strategy_version"] for row in records.values()}
    groups.update({version: [] for version in RETIRED_STRATEGIES if include_empty_retired or version in planned})
    groups.update({name: [] for name in (
        "B_NUMERIC_QUALIFIED", "B_NUMERIC_REJECTED", "B_NUMERIC_UNAVAILABLE", "WARNING", "CLEAR", "UNKNOWN",
    )})
    for row in records.values():
        plan = row["plan"]
        groups[plan["strategy_version"]].append(row)
        if plan["strategy_version"] == B_VERSION:
            groups[plan["qualification"]].append(row)
        groups[plan["risk_warning"]].append(row)
    stats = []
    for name, group in groups.items():
        counts = Counter(row["status"] for row in group)
        realized = [Decimal(row["position"]["r"]) for row in group if row["status"] == Status.CLOSED]
        total = sum(realized, Decimal(0))
        stats.append({"group": name, **{status: counts[status] for status in Status},
                      "win_rate": sum(value > 0 for value in realized) / len(realized) if realized else None,
                      "mean_r": total / len(realized) if realized else None, "total_r": total})
    return stats
