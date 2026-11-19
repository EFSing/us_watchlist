"""Run independent B and C checks over the same local input."""

from hashlib import sha256
from pathlib import Path

from us_watchlist.app.replay import evaluate, prepare_replay
from us_watchlist.domain.replay_research import ReplayResearch
from us_watchlist.domain.screening import ReplayEvidence, ScreeningResult
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.reporting.replay_html import render_joint_replay
from us_watchlist.research.pullback import compare_b_volume
from us_watchlist.research.replay_observations import REFERENCE_COMMIT, VERSION, observe_candidate
from us_watchlist.strategies.b_breakout_retest import BreakoutRetestShape
from us_watchlist.strategies.c_trend_pullback import BALANCED_A, CONSERVATIVE_B, TrendPullback
from us_watchlist.strategies.contracts import StrategyInput


def evaluate_joint(inputs: StrategyInput) -> tuple[ScreeningResult, tuple[ScreeningResult, ...]]:
    return (
        evaluate(BreakoutRetestShape(), inputs),
        tuple(evaluate(TrendPullback(rule), inputs) for rule in (BALANCED_A, CONSERVATIVE_B)),
    )


def observe_joint(
    evidence: ReplayEvidence, inputs: StrategyInput, b: ScreeningResult, c: tuple[ScreeningResult, ...],
) -> ReplayResearch:
    latest = inputs.history[-1].session
    if latest.trading_date != evidence.trade_date or inputs.cutoff != evidence.cutoff:
        raise ValueError("Research must share the screening date and cutoff")
    matched = tuple(row for result in (b, *c) for row in result.evaluations if row.signal is not None)
    if any(row.signal.session != latest or row.signal.known_at != inputs.cutoff for row in matched):
        raise ValueError("Matched study candidates must share the completed screening session and cutoff")
    dates = tuple(snapshot.session.trading_date for snapshot in inputs.history)
    series_by_symbol = inputs.window(len(dates))
    source_gaps = dict(inputs.symbol_gaps)
    b_rows, c_rows = [], []
    for row in matched:
        is_b = row.signal.strategy == b.strategy
        observed = observe_candidate(
            row, dates, series_by_symbol[row.symbol], is_b=is_b, source_gap=source_gaps.get(row.symbol, ""),
        )
        (b_rows if is_b else c_rows).append(observed)
    return ReplayResearch(VERSION, REFERENCE_COMMIT, (*compare_b_volume(tuple(b_rows)), *c_rows))


def run_bc_offline(config_path: Path, artifact_dir: Path) -> Path:
    evidence, inputs = prepare_replay(config_path)
    b, c = evaluate_joint(inputs)
    report = observe_joint(evidence, inputs, b, c)
    html = render_joint_replay(evidence, b, c, research=report).encode("utf-8")
    report_sha = sha256(html).hexdigest()[:16]
    path = artifact_dir / evidence.mode / f"US_{evidence.trade_date}_regular_bc_{report_sha}.html"
    publish_once(path, html)
    return path
