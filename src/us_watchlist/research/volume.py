"""Descriptive volume study for the offline demonstration."""

from statistics import median

from us_watchlist.domain.models import SessionBar


def median_volume(bars: tuple[SessionBar, ...]) -> float | None:
    return median(bar.volume for bar in bars) if bars else None
