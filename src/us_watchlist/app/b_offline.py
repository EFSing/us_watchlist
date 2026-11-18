"""Run the local US B shape diagnostic."""

from pathlib import Path

from us_watchlist.app.replay import evaluate, prepare_replay
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.reporting.replay_html import render_replay
from us_watchlist.strategies.b_breakout_retest import BreakoutRetestShape


def run_b_offline(config_path: Path, artifact_dir: Path) -> Path:
    evidence, inputs = prepare_replay(config_path)
    result = evaluate(BreakoutRetestShape(), inputs)
    path = (
        artifact_dir / evidence.mode
        / f"US_{evidence.trade_date}_regular_{result.strategy.version}_{evidence.input_sha256[:16]}.html"
    )
    publish_once(path, render_replay(evidence, (result,)).encode("utf-8"))
    return path
