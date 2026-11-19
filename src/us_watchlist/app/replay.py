"""Validate a shared US input before evaluating any strategy."""

from pathlib import Path

from us_watchlist.domain.screening import ReplayEvidence, ScreeningResult
from us_watchlist.integrations.replay_input import ReplayInput, read_replay
from us_watchlist.market_data.quality import regular_history
from us_watchlist.strategies.contracts import Strategy, StrategyInput
from us_watchlist.universe.eligibility import eligible_symbols


def prepare_replay(config_path: Path) -> tuple[ReplayEvidence, StrategyInput]:
    return prepare_input(read_replay(config_path))


def prepare_input(data: ReplayInput) -> tuple[ReplayEvidence, StrategyInput]:
    if not data.history:
        raise ValueError("Expected a regular-session calendar")
    pool = data.candidates
    eligible = eligible_symbols(pool.snapshot, data.history[-1].session, data.cutoff)
    history = regular_history(
        data.history, data.target_date, eligible, data.cutoff, data.adjustments_known_at,
    )
    evidence = ReplayEvidence(
        data.target_date, data.cutoff, data.mode, pool.snapshot.effective_date, pool.holdings_date,
        pool.snapshot.provenance, pool.seed_count, pool.active_count, len(eligible), pool.status,
        history[-1].provenance, history[0].session.trading_date, len(history),
        data.calendar_source, history[-1].price_basis, data.adjustments_known_at, data.input_sha256,
    )
    return evidence, StrategyInput(data.cutoff, eligible, history, data.symbol_gaps)


def evaluate(strategy: Strategy, inputs: StrategyInput) -> ScreeningResult:
    try:
        return ScreeningResult(strategy.version, strategy.evaluate(inputs))
    except Exception as error:
        return ScreeningResult(strategy.version, (), f"{type(error).__name__}: {error}")
