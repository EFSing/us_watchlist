"""Build B and C observations from their existing anchors and continuous histories."""

from datetime import date
from decimal import Decimal

from us_watchlist.domain.models import SessionBar
from us_watchlist.domain.replay_research import (
    REFERENCE_V1, REFERENCE_V2, UNCONFIRMED, CandidateResearch, StructureObservation,
)
from us_watchlist.domain.screening import B_US_V2, Evaluation
from us_watchlist.research.pullback import b_structure, pullback_volume
from us_watchlist.research.reference_plan import b_reference_plan, b_us_reference_plan, c_reference_plan

REFERENCE_COMMIT = "85abb04acb86e3396f635218e7087c00a0d8339a"


def research_version(b_version: str) -> str:
    return REFERENCE_V2 if b_version == B_US_V2 else REFERENCE_V1


def observe_candidate(
    row: Evaluation, dates: tuple[date, ...], series: tuple[SessionBar | None, ...], *,
    is_b: bool, source_gap: str,
) -> CandidateResearch:
    if row.signal is None or len(dates) != len(series) or not dates or row.signal.session.trading_date != dates[-1]:
        raise ValueError("Research requires the matched candidate's T-ending observation window")

    suffix = []
    for bar in reversed(series):
        if bar is None:
            break
        suffix.append(bar)
    bars = tuple(reversed(suffix))
    days = dates[len(dates) - len(bars):]
    by_date = {day.isoformat(): i for i, day in enumerate(days)}
    anchors = dict(row.structure)
    anchor = by_date.get(anchors.get("Breakout date" if is_b else "Peak date"))

    if is_b:
        structure = b_structure(bars, days, anchor)
        price = anchors.get("Platform")
        platform = price if anchor is not None and isinstance(price, Decimal) else None
        if row.signal.strategy.version == B_US_V2:
            trade = b_us_reference_plan(bars, platform, anchor)
        else:
            trade = b_reference_plan(bars, platform)
    else:
        support = by_date.get(anchors.get("First low date"))
        rebound = by_date.get(anchors.get("Rebound date"))
        if (anchor is not None and support is not None and rebound is not None
                and anchor < support < rebound < len(bars) - 1):
            peak_price, support_price, rebound_price = bars[anchor].high, bars[support].low, bars[rebound].high
            structure = StructureObservation("C_CLOSE_REBOUND_CONFIRMED", points=(
                ("C_PRIOR_HIGH", days[anchor], peak_price),
                ("C_SUPPORT_FLOOR", days[support], support_price),
                ("C_REBOUND_HIGH", days[rebound], rebound_price),
            ))
        else:
            peak_price = support_price = rebound_price = None
            structure = StructureObservation(UNCONFIRMED, "C_STRUCTURE_ANCHORS_UNAVAILABLE")
        trade = c_reference_plan(bars, peak_price, support_price, rebound_price)

    return CandidateResearch(
        row.signal.strategy.version, row.symbol, len(bars), source_gap, structure,
        pullback_volume(bars, days, anchor), trade,
    )
