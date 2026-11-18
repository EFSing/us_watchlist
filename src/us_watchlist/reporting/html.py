"""Render an offline, self-contained presentation of validated input coverage."""

from html import escape

from us_watchlist.domain.models import MARKET, RunObservation


def render_smoke(
    observation: RunObservation, median_volume: float | None, input_sha256: str
) -> str:
    session = observation.session
    facts = {
        "Session": session.kind.value,
        "Window (UTC)": f"{session.opens_at.isoformat()} to {session.closes_at.isoformat()}",
        "Decision cutoff (UTC)": observation.cutoff.isoformat(),
        "Universe snapshot": (
            f"{observation.universe.source} / {observation.universe.snapshot_id}"
            f" · {observation.universe.available_at.isoformat()}"
        ),
        "Market snapshot": (
            f"{observation.prices.source} / {observation.prices.snapshot_id}"
            f" · {observation.prices.available_at.isoformat()}"
        ),
        "Input SHA-256": input_sha256,
        "Price basis": observation.price_basis.value,
        "Eligible": ", ".join(observation.eligible_symbols) or "None",
        "Completed bars": ", ".join(observation.observed_symbols) or "None",
        "Missing bars": ", ".join(observation.missing_symbols) or "None",
        "Median volume": f"{median_volume:,}" if median_volume is not None else "Unavailable",
    }
    rows = "\n".join(f"<dt>{label}</dt><dd>{escape(value)}</dd>" for label, value in facts.items())
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{MARKET} watchlist smoke · {session.trading_date}</title>
<h1>{MARKET} watchlist smoke · {session.trading_date}</h1>
<p>Synthetic input coverage</p>
<dl>
{rows}
</dl>
</html>
"""
