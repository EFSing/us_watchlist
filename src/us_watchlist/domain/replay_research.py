"""Immutable projections for research attached to existing screening matches."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from us_watchlist.domain.screening import Metrics

REFERENCE_V1 = "us_bc_reference_research_v1"
REFERENCE_V2 = "us_bc_reference_research_v2"
VOLUME_FIELDS = ("down_volume_share", "up_down_volume_ratio", "pullback_volume_decay_ratio")
PREFERENCES = ("LOW", "HIGH", "LOW")
TRANSITION = "W2_TO_W3_TRANSITION_PROXY"
UNCONFIRMED = "STRUCTURE_PROXY_UNAVAILABLE_OR_INVALID"


@dataclass(frozen=True)
class StructureObservation:
    stage: str
    reason: str | None = None
    points: tuple[tuple[str, date, Decimal], ...] = ()
    recovery_ratio: Decimal | None = None


@dataclass(frozen=True)
class VolumeCoordinate:
    status: str
    sample_size: int
    percentile: Decimal | None = None
    bucket: str | None = None
    judgment: str | None = None


@dataclass(frozen=True)
class VolumeMeasure:
    field: str
    value: Decimal | None
    missing_reason: str | None = None
    coordinate: VolumeCoordinate | None = None


@dataclass(frozen=True)
class PullbackVolume:
    anchor_day: date | None
    window_start: date | None
    window_end: date | None
    window_days: int | None
    up_days: int
    down_days: int
    flat_days: int
    measures: tuple[VolumeMeasure, ...]


@dataclass(frozen=True)
class ReferencePlan:
    trigger: Decimal
    stop: Decimal
    target: Decimal
    entry: Decimal
    rr: Decimal
    target_rule: str


@dataclass(frozen=True)
class PlanObservation:
    qualification: str
    qualification_reason: str | None = None
    plan: ReferencePlan | None = None
    missing_reason: str | None = None
    inputs: Metrics = ()


@dataclass(frozen=True)
class CandidateResearch:
    strategy_version: str
    symbol: str
    continuous_sessions: int
    source_gap: str
    structure: StructureObservation
    volume: PullbackVolume
    trade: PlanObservation

    @property
    def passed_b_numeric_gate(self) -> bool:
        return self.trade.qualification == "B_NUMERIC_QUALIFIED"

    @property
    def in_b_transition_cohort(self) -> bool:
        return self.passed_b_numeric_gate and self.structure.stage == TRANSITION


@dataclass(frozen=True)
class ReplayResearch:
    version: str
    reference_commit: str
    candidates: tuple[CandidateResearch, ...]
