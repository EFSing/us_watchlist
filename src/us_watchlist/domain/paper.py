"""Contracts shared by the IWB research ledger and its companion views."""

from decimal import Decimal
from enum import StrEnum

from us_watchlist.domain.models import PriceBasis

PROTOCOL = "us_iwb_paper_open_v1"
STRATEGIES = {
    "us_breakout_retest_shape_v1": "B 突破回踩",
    "us_c_trend_pullback_balanced_a_v1": "C 均衡",
    "us_c_trend_pullback_conservative_b_v1": "C 保守",
}
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


def check_policy(policy: dict) -> None:
    """Each strategy/cohort can explicitly opt into a research model."""
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
            if rule["exit_model"] not in ("FIXED_STOP", "LEGACY_R_PROTECTION"):
                raise ValueError("PAPER_UNSUPPORTED_EXIT_MODEL")
            for key in ("min_actual_rr", "min_target_upside", "max_open_premium"):
                value = rule[key]
                if value is not None and (
                    not isinstance(value, str) or not Decimal(value).is_finite() or Decimal(value) < 0
                ):
                    raise ValueError(f"PAPER_INVALID_POLICY_LIMIT {key}")
