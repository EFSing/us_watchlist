"""Contracts shared by the IWB research ledger and its companion views."""

from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType

from us_watchlist.domain.models import PriceBasis

PROTOCOL = "us_iwb_paper_open_v1"
POSITION_PROTOCOL = "us_iwb_paper_position_v2"
STRATEGIES = {
    "us_breakout_retest_shape_v1": "B 突破回踩",
    "us_c_trend_pullback_balanced_a_v1": "C 均衡",
}
RETIRED_STRATEGIES = {
    "us_c_trend_pullback_conservative_b_v1": "C 保守",
}
STRATEGY_LABELS = MappingProxyType(STRATEGIES | RETIRED_STRATEGIES)
B_VERSION = next(iter(STRATEGIES))
BASIS = PriceBasis.YAHOO_CHART_QUOTE


class Mode(StrEnum):
    HISTORICAL_REPLAY = "HISTORICAL_REPLAY"
    PROSPECTIVE = "PROSPECTIVE"
    SYNTHETIC = "SYNTHETIC"


class Status(StrEnum):
    PENDING = "PENDING"
    NOT_FILLED = "NOT_FILLED"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    UNAVAILABLE = "UNAVAILABLE"


def cohort(plan: dict) -> str:
    return f"{plan['qualification']}:{plan['risk_warning']}"


def needs_structure(model: dict) -> bool:
    return bool(model["structure_exit"] or model["atr_trail"] or model["reject_open_at_or_below_structure"])


def seed_sessions(model: dict) -> int:
    pivot, trail = model["pivot"], model["atr_trail"]
    return max(pivot["radius"] if pivot else 0, trail["period"] + 1 if trail else 0)


def _check_decimal(value, *, positive: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    try:
        number = Decimal(value)
    except InvalidOperation:
        return False
    return number.is_finite() and (number > 0 if positive else number >= 0)


def _check_position_model(model) -> None:
    if not isinstance(model, dict) or set(model) != {
        "reject_open_at_or_below_structure", "structure_exit", "pivot", "atr_trail", "profit_protection",
    } or any(type(model[key]) is not bool for key in ("reject_open_at_or_below_structure", "structure_exit")):
        raise ValueError("PAPER_INVALID_POSITION_MODEL")
    pivot, trail, profit = model["pivot"], model["atr_trail"], model["profit_protection"]
    if pivot is not None and (
        not isinstance(pivot, dict) or set(pivot) != {"radius", "min_separation", "require_rebound"}
        or type(pivot["require_rebound"]) is not bool
        or any(type(pivot[key]) is not int or pivot[key] < 1 for key in ("radius", "min_separation"))
        or (not model["structure_exit"] and trail is None)
    ):
        raise ValueError("PAPER_INVALID_PIVOT_POLICY")
    if trail is not None and (
        not isinstance(trail, dict) or set(trail) != {"period", "multiple"} or pivot is None
        or type(trail["period"]) is not int or trail["period"] < 1
        or not _check_decimal(trail["multiple"], positive=True)
    ):
        raise ValueError("PAPER_INVALID_ATR_POLICY")
    if profit is not None and (
        not isinstance(profit, dict) or set(profit) != {"trigger_r", "giveback_r"}
        or not _check_decimal(profit["trigger_r"], positive=True)
        or not _check_decimal(profit["giveback_r"])
    ):
        raise ValueError("PAPER_INVALID_PROFIT_POLICY")


def check_policy(policy: dict, protocol: str = PROTOCOL) -> None:
    """Each strategy/cohort can explicitly opt into a research model."""
    if protocol not in (PROTOCOL, POSITION_PROTOCOL):
        raise ValueError("PAPER_UNSUPPORTED_PROTOCOL")
    if not isinstance(policy, dict) or not all(isinstance(cohorts, dict) for cohorts in policy.values()):
        raise ValueError("PAPER_INVALID_POLICY")
    if set(policy) - STRATEGIES.keys():
        raise ValueError("PAPER_UNKNOWN_POLICY_STRATEGY")
    for version, cohorts in policy.items():
        qualifications = ("B_NUMERIC_QUALIFIED", "B_NUMERIC_REJECTED") if version == B_VERSION else ("C_PRICE_RESEARCH",)
        allowed = {f"{qualification}:{risk}" for qualification in qualifications for risk in (
            ("UNKNOWN",) if version == B_VERSION else ("WARNING", "CLEAR")
        )}
        if set(cohorts) - allowed:
            raise ValueError("PAPER_UNKNOWN_POLICY_COHORT")
        for rule in cohorts.values():
            if not isinstance(rule, dict) or set(rule) != {
                "min_actual_rr", "min_target_upside", "max_open_premium", "exit_model",
            }:
                raise ValueError("PAPER_POLICY_REQUIRES_EXPLICIT_LIMITS")
            if protocol == POSITION_PROTOCOL:
                _check_position_model(rule["exit_model"])
            elif rule["exit_model"] not in ("FIXED_STOP", "LEGACY_R_PROTECTION"):
                raise ValueError("PAPER_UNSUPPORTED_EXIT_MODEL")
            for key in ("min_actual_rr", "min_target_upside", "max_open_premium"):
                value = rule[key]
                if value is not None and not _check_decimal(value):
                    raise ValueError(f"PAPER_INVALID_POLICY_LIMIT {key}")
