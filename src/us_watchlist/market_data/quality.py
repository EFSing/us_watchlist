"""Point-in-time validation for a completed, explicitly labeled session."""

from dataclasses import replace
from datetime import date, datetime

from us_watchlist.domain.models import MarketSnapshot, PriceBasis, SessionBar, SessionKind, require_utc


def completed_bars(
    snapshot: MarketSnapshot, symbols: tuple[str, ...], cutoff: datetime
) -> tuple[SessionBar, ...]:
    require_utc(cutoff)
    if snapshot.provenance.available_at < snapshot.session.closes_at:
        raise ValueError("Completed bars cannot be available before the session closes")
    if snapshot.provenance.available_at > cutoff:
        raise ValueError("Completed market snapshot was unavailable at the decision cutoff")
    bars = {bar.symbol: bar for bar in snapshot.bars}
    if len(bars) != len(snapshot.bars):
        raise ValueError("Market snapshot contains duplicate bars")
    return tuple(bars[symbol] for symbol in sorted(symbols) if symbol in bars)


def regular_history(
    history: tuple[MarketSnapshot, ...],
    target: date,
    symbols: tuple[str, ...],
    cutoff: datetime,
    adjustments_known_at: datetime,
) -> tuple[MarketSnapshot, ...]:
    require_utc(cutoff)
    require_utc(adjustments_known_at)
    if adjustments_known_at > cutoff:
        raise ValueError("Split adjustments were unavailable at the decision cutoff")
    if not history or history[-1].session.trading_date != target:
        raise ValueError("The last expected regular session must equal the target trading date")
    if cutoff.date() != target:
        raise ValueError("B decision cutoff must be on the target UTC date")

    result = []
    previous = None
    for snapshot in history:
        session = snapshot.session
        if session.kind != SessionKind.REGULAR:
            raise ValueError("B replay accepts only regular sessions")
        if not session.opens_at.date() == session.trading_date == session.closes_at.date():
            raise ValueError("Regular session UTC dates must agree with the trading date")
        if previous and (
            session.trading_date <= previous.trading_date or session.opens_at < previous.closes_at
        ):
            raise ValueError("Expected sessions must be ordered, unique and non-overlapping")
        if snapshot.price_basis != PriceBasis.SPLIT_ADJUSTED:
            raise ValueError("B replay requires split-adjusted price and volume")
        result.append(replace(snapshot, bars=completed_bars(snapshot, symbols, cutoff)))
        previous = session
    return tuple(result)
