"""Point-in-time validation for a completed, explicitly labeled session."""

from datetime import datetime

from us_watchlist.domain.models import MarketSnapshot, SessionBar, require_utc


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
