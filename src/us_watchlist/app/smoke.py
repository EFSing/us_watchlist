"""Coordinate the offline input-validation and report flow."""

from pathlib import Path

from us_watchlist.domain.models import MARKET
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.integrations.smoke_fixture import read_fixture
from us_watchlist.market_data.quality import completed_bars
from us_watchlist.reporting.html import render_smoke
from us_watchlist.research.volume import median_volume
from us_watchlist.tracking.observations import observe_inputs
from us_watchlist.universe.eligibility import eligible_symbols


def run_smoke(config_path: Path, artifact_dir: Path) -> Path:
    universe, market, cutoff, digest = read_fixture(config_path)
    eligible = eligible_symbols(universe, market.session, cutoff)
    bars = completed_bars(market, eligible, cutoff)
    observation = observe_inputs(universe, market, cutoff, eligible, bars)
    report = render_smoke(observation, median_volume(bars), digest)
    session = observation.session
    path = artifact_dir / f"{MARKET}_{session.trading_date.isoformat()}_{session.kind.value}.html"
    publish_once(path, report.encode("utf-8"))
    return path
