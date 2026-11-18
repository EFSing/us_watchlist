"""Evaluate a snapshot known at the decision cutoff."""

from datetime import datetime

from us_watchlist.domain.models import SessionWindow, UniverseSnapshot, require_utc


def eligible_symbols(
    snapshot: UniverseSnapshot, session: SessionWindow, cutoff: datetime
) -> tuple[str, ...]:
    require_utc(cutoff)
    if snapshot.effective_date > session.trading_date or snapshot.provenance.available_at > cutoff:
        raise ValueError("Universe snapshot was unavailable at the decision cutoff")
    members = {member.symbol: member for member in snapshot.members}
    if len(members) != len(snapshot.members):
        raise ValueError("Universe snapshot contains duplicate symbols")
    return tuple(sorted(member.symbol for member in members.values() if member.active))
