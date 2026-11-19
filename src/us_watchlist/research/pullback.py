"""Frozen CN pullback observations adapted to validated, T-ending US bars."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

from us_watchlist.domain.models import SessionBar
from us_watchlist.domain.replay_research import (
    PREFERENCES, TRANSITION, UNCONFIRMED, VOLUME_FIELDS, CandidateResearch, PullbackVolume,
    StructureObservation, VolumeCoordinate, VolumeMeasure,
)


def b_structure(bars: tuple[SessionBar, ...], dates: tuple[date, ...], i: int | None) -> StructureObservation:
    t = len(bars) - 1
    if i is None or not 60 <= i < t:
        return StructureObservation(UNCONFIRMED, "BASE_OR_BREAKOUT_WINDOW_UNAVAILABLE")
    l0 = min(range(i - 60, i), key=lambda j: bars[j].low)
    h1 = max(range(i, t), key=lambda j: bars[j].high)
    points = (("L0", dates[l0], bars[l0].low), ("H1", dates[h1], bars[h1].high))
    if h1 + 1 >= t:
        return StructureObservation(UNCONFIRMED, "NO_COMPLETE_POST_H1_PULLBACK_DAY", points)
    l2 = min(range(h1 + 1, t), key=lambda j: bars[j].low)
    points += (("L2", dates[l2], bars[l2].low),)
    low, peak, retest = (point[2] for point in points)
    if not low < retest < peak:
        return StructureObservation(UNCONFIRMED, "INVALID_L0_L2_H1_ORDER_OR_DENOMINATOR", points)
    recovery = (bars[t].close - retest) / (peak - retest)
    stage = "EARLY_PULLBACK" if recovery < Decimal("0.5") else TRANSITION if recovery <= 1 else "POST_H1_CONTINUATION_PROXY"
    return StructureObservation(stage, points=points, recovery_ratio=recovery)


def pullback_volume(bars: tuple[SessionBar, ...], dates: tuple[date, ...], i: int | None) -> PullbackVolume:
    if i is None or not 0 <= i < len(bars) - 1:
        return PullbackVolume(None, None, None, None, 0, 0, 0, tuple(
            VolumeMeasure(field, None, "PULLBACK_ANCHOR_UNAVAILABLE") for field in VOLUME_FIELDS
        ))
    window = bars[i + 1:-1]
    days = len(window)
    if not window:
        return PullbackVolume(dates[i], None, None, 0, 0, 0, 0, tuple(
            VolumeMeasure(field, None, "NO_PULLBACK_WINDOW") for field in VOLUME_FIELDS
        ))
    up, down = [], []
    for previous, bar in zip(bars[i:-2], window):
        if bar.close > previous.close:
            up.append(bar.volume)
        elif bar.close < previous.close:
            down.append(bar.volume)
    total = sum(bar.volume for bar in window)
    down_total = sum(down)
    share = (Decimal(down_total) / total, None) if total else (None, "INVALID_PULLBACK_VOLUME_SUM")
    if not up or not down:
        directional = (None, "NO_UP_OR_DOWN_DAY")
    elif not down_total:
        directional = (None, "INVALID_UP_OR_DOWN_VOLUME")
    else:
        directional = (Decimal(sum(up) * len(down)) / (down_total * len(up)), None)
    split = days // 2
    first = sum(bar.volume for bar in window[:split])
    if days < 4:
        decay = (None, "PULLBACK_WINDOW_LT_4")
    elif not first:
        decay = (None, "INVALID_PULLBACK_HALF_VOLUME")
    else:
        decay = (Decimal((total - first) * split) / (first * (days - split)), None)
    measures = tuple(VolumeMeasure(field, *data) for field, data in zip(VOLUME_FIELDS, (share, directional, decay)))
    return PullbackVolume(dates[i], dates[i + 1], dates[-2], days, len(up), len(down), days - len(up) - len(down), measures)


def _in_cohort(row: CandidateResearch) -> bool:
    return row.structure.stage == TRANSITION and row.trade.qualification == "B_NUMERIC_QUALIFIED"


def _coordinate(row: CandidateResearch, value: Decimal | None, sample: list[Decimal], preference: str) -> VolumeCoordinate:
    size = len(sample)
    if row.structure.stage != TRANSITION:
        return VolumeCoordinate("NOT_PRIMARY_COHORT", size)
    if not _in_cohort(row):
        return VolumeCoordinate("B_NUMERIC_QUALIFICATION_NOT_MET", size)
    if value is None:
        return VolumeCoordinate("FEATURE_UNAVAILABLE", size)
    if size < 3:
        return VolumeCoordinate("INSUFFICIENT_CROSS_SECTION", size)
    # Twice the average rank, so the 1/3 and 2/3 boundaries are exact.
    rank = 2 * sum(item < value for item in sample) + sum(item == value for item in sample) + 1
    bucket = "LOW" if 3 * rank <= 2 * size else "MID" if 3 * rank <= 4 * size else "HIGH"
    judgment = "NEUTRAL" if bucket == "MID" else "PREFERRED" if bucket == preference else "DEVIATION"
    return VolumeCoordinate("ANALYSIS_COORDINATE_ONLY", size, Decimal(rank) / (2 * size), bucket, judgment)


def compare_b_volume(rows: tuple[CandidateResearch, ...]) -> tuple[CandidateResearch, ...]:
    eligible = tuple(row for row in rows if _in_cohort(row))
    samples = [
        [measure.value for row in eligible if (measure := row.volume.measures[i]).value is not None]
        for i in range(len(VOLUME_FIELDS))
    ]
    return tuple(
        replace(row, volume=replace(row.volume, measures=tuple(
            replace(item, coordinate=_coordinate(row, item.value, sample, preference))
            for item, sample, preference in zip(row.volume.measures, samples, PREFERENCES)
        )))
        for row in rows
    )
