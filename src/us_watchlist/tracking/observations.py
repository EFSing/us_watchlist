"""Capture the data actually available to the smoke flow."""

from datetime import datetime

from us_watchlist.domain.models import MarketSnapshot, RunObservation, SessionBar, UniverseSnapshot


def observe_inputs(
    universe: UniverseSnapshot,
    market: MarketSnapshot,
    cutoff: datetime,
    eligible: tuple[str, ...],
    bars: tuple[SessionBar, ...],
) -> RunObservation:
    return RunObservation(
        session=market.session,
        cutoff=cutoff,
        universe=universe.provenance,
        prices=market.provenance,
        price_basis=market.price_basis,
        eligible_symbols=eligible,
        observed_symbols=tuple(bar.symbol for bar in bars),
    )
