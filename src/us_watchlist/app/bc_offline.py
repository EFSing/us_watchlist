"""Run independent B and C checks over the same local input."""

from hashlib import sha256
from pathlib import Path

from us_watchlist.app.replay import evaluate, prepare_replay
from us_watchlist.domain.screening import ScreeningResult
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.reporting.replay_html import render_joint_replay
from us_watchlist.strategies.b_breakout_retest import BreakoutRetestShape
from us_watchlist.strategies.c_trend_pullback import BALANCED_A, CONSERVATIVE_B, TrendPullback
from us_watchlist.strategies.contracts import StrategyInput


def evaluate_joint(inputs: StrategyInput) -> tuple[ScreeningResult, tuple[ScreeningResult, ...]]:
    return (
        evaluate(BreakoutRetestShape(), inputs),
        tuple(evaluate(TrendPullback(rule), inputs) for rule in (BALANCED_A, CONSERVATIVE_B)),
    )


def run_bc_offline(config_path: Path, artifact_dir: Path) -> Path:
    evidence, inputs = prepare_replay(config_path)
    b, c = evaluate_joint(inputs)
    html = render_joint_replay(evidence, b, c).encode("utf-8")
    report_sha = sha256(html).hexdigest()[:16]
    path = artifact_dir / evidence.mode / f"US_{evidence.trade_date}_regular_bc_{report_sha}.html"
    publish_once(path, html)
    return path
