"""The local, single-date US B replay."""

from pathlib import Path

from us_watchlist.domain.screening import ScreeningReport
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.integrations.replay_input import read_replay
from us_watchlist.market_data.quality import regular_history
from us_watchlist.reporting.replay_html import render_replay
from us_watchlist.strategies.b_breakout_retest import BreakoutRetestShape
from us_watchlist.strategies.contracts import StrategyInput
from us_watchlist.universe.eligibility import eligible_symbols


def run_b_offline(config_path: Path, artifact_dir: Path) -> Path:
    data = read_replay(config_path)
    if not data.history:
        raise ValueError("Expected a regular-session calendar")
    eligible = eligible_symbols(data.seed, data.history[-1].session, data.cutoff)
    if (data.target_date - data.seed.effective_date).days > data.max_seed_age_days:
        raise ValueError("The IWB holdings date exceeds max_seed_age_days")

    history = regular_history(
        data.history, data.target_date, eligible, data.cutoff, data.adjustments_known_at
    )
    strategy = BreakoutRetestShape()
    evaluated = strategy.evaluate(StrategyInput(data.cutoff, eligible, history))
    report = ScreeningReport(
        data.target_date, data.cutoff, data.mode, strategy.version, data.seed.effective_date,
        data.seed.provenance, len(data.seed.members), history[-1].provenance.source,
        data.adjustments_known_at, data.input_sha256, evaluated,
    )
    path = (
        artifact_dir / data.mode
        / f"US_{data.target_date}_regular_{strategy.version.version}_{data.input_sha256[:16]}.html"
    )
    publish_once(path, render_replay(report).encode("utf-8"))
    return path
