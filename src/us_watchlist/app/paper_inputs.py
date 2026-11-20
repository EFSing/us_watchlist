"""Build the ledger's point-in-time input from one immutable IWB observation."""

from datetime import date
from decimal import Decimal
from pathlib import Path

from us_watchlist.app.iwb_daily import verify_completed
from us_watchlist.domain.paper import BASIS, B_VERSION, STRATEGIES
from us_watchlist.domain.replay_research import VOLUME_FIELDS
from us_watchlist.integrations.iwb_holdings import read_holdings
from us_watchlist.integrations.local_artifacts import read_artifact
from us_watchlist.integrations.paper_archive import quote_prices, read_report_records
from us_watchlist.integrations.xnys import next_session
from us_watchlist.integrations.yahoo_chart import read_yahoo
from us_watchlist.market_data.quality import regular_history
from us_watchlist.universe.eligibility import eligible_symbols


def _candidate(row: dict) -> dict:
    version, symbol = row["strategy_version"], row["symbol"]
    trade = row["trade"]
    qualification = trade["qualification"]
    allowed = (("B_NUMERIC_QUALIFIED", "B_NUMERIC_REJECTED", "B_NUMERIC_UNAVAILABLE")
               if version == B_VERSION else ("C_PRICE_RESEARCH",))
    if qualification not in allowed:
        raise ValueError(f"PAPER_UNRECOGNIZED_QUALIFICATION {symbol} {version}")
    levels = trade["plan"]
    if levels is not None:
        trigger, stop, target, entry, rr = (Decimal(levels[key]) for key in ("trigger", "stop", "target", "entry", "rr"))
        if not (0 < stop < min(trigger, entry) <= max(trigger, entry) < target and rr > 0):
            raise ValueError(f"PAPER_INVALID_REFERENCE_LEVELS {symbol} {version}")
    warning = dict(trade["inputs"]).get("stop_risk_warning")
    if warning is not None and type(warning) is not bool:
        raise ValueError(f"PAPER_INVALID_RISK_WARNING {symbol} {version}")
    volume = row["volume"]["measures"]
    if tuple(measure["field"] for measure in volume) != VOLUME_FIELDS:
        raise ValueError(f"PAPER_VOLUME_FIELDS_MISMATCH {symbol} {version}")
    return {
        "symbol": symbol, "strategy_version": version, "matched": True,
        "qualification": qualification, "qualification_reason": trade["qualification_reason"],
        "risk_warning": {None: "UNKNOWN", True: "WARNING", False: "CLEAR"}[warning],
        "structure": row["structure"], "volume": volume, "levels": levels,
        "reference_missing_reason": trade["missing_reason"],
    }


def _screening(run: dict, records: dict, listed: tuple[str, ...]) -> tuple[list[dict], dict]:
    research = records["record-research"]
    identity = (run["trade_date"], run["observed_at"], run["input_sha256"], "iwb_yahoo_observation")
    keys = ("trade_date", "cutoff", "manifest_sha256", "mode")
    if tuple(research[key] for key in keys) != identity or research["price_basis"] != BASIS:
        raise ValueError("PAPER_RESEARCH_IDENTITY_MISMATCH")
    grid = {}
    matches = set()
    for version in STRATEGIES:
        strategy = records[version]
        rows = strategy["evaluations"]
        if (tuple(strategy[key] for key in keys) != identity or strategy["version"] != version
            or strategy["schema"] != "us_offline_screening_v1" or strategy["error"] is not None
            or sorted(row["symbol"] for row in rows) != list(listed)
            or any(type(row["matched"]) is not bool for row in rows)):
            raise ValueError(f"PAPER_SCREENING_IDENTITY_MISMATCH {version}")
        matched = {row["symbol"] for row in rows if row["matched"]}
        if len(matched) != run["strategies"][version]["matches"]:
            raise ValueError(f"PAPER_SCREENING_COUNT_MISMATCH {version}")
        grid[version] = {row["symbol"]: row["reason"] for row in rows}
        matches.update((version, symbol) for symbol in matched)
    candidates = {(row["strategy_version"], row["symbol"]): row for row in research["candidates"]}
    if candidates.keys() != matches or len(candidates) != len(research["candidates"]):
        raise ValueError("PAPER_RESEARCH_MATCH_SET_MISMATCH")
    for (version, symbol), row in candidates.items():
        grid[version][symbol] = row["structure"]["stage"]
    return [_candidate(row) for _, row in sorted(candidates.items())], grid


def load_day(directory: Path, target: date, tracking_symbols: set[str]) -> dict:
    run = verify_completed(directory, target)
    records = read_report_records(read_artifact(directory / "report.html"), run["report_sha256"])
    pool = read_holdings(directory / "holdings.zip").snapshot
    symbols = tuple(sorted(member.symbol for member in pool.members if member.active))
    history, observed, calendar, diagnostics = read_yahoo(
        read_artifact(directory / "yahoo.zip"), run["yahoo_zip_sha256"], target, symbols, pool.provenance,
        official_iwb=True, require_target_close=run.get("require_yahoo_close", False),
    )
    if ((observed.isoformat(), calendar, history[-1].session.closes_at.isoformat(), len(history)) !=
        (run["observed_at"], run["calendar"], run["session_close_utc"], run["history_sessions"])):
        raise ValueError("PAPER_CAPTURE_RECEIPT_MISMATCH")
    if eligible_symbols(pool, history[-1].session, observed) != symbols:
        raise ValueError("PAPER_HOLDINGS_SCOPE_MISMATCH")
    history = regular_history(history, target, symbols, observed, None)
    target_symbols = {bar.symbol for bar in history[-1].bars}
    if (len(symbols), len(target_symbols), sorted(set(symbols) - target_symbols)) != (
        run["listed_equities"], run["target_bars"], run["missing_target_bars"],
    ):
        raise ValueError("PAPER_TARGET_COVERAGE_MISMATCH")
    candidates, grid = _screening(run, records, symbols)

    previous, current = map(quote_prices, history[-2:])
    gaps = dict(diagnostics)
    requested = tracking_symbols | {plan["symbol"] for plan in candidates}
    source = {key: run[key] for key in (
        "report_id", "code_sha", "observed_at", "input_sha256", "report_sha256", "holdings_date",
        "holdings_csv_sha256", "holdings_zip_sha256", "yahoo_zip_sha256", "calendar",
        "listed_equities", "target_bars", "missing_target_bars",
    )}
    source.update(price_basis=BASIS, research_version=records["record-research"]["version"],
                  reference_commit=records["record-research"]["reference_commit"])
    return {
        "trade_date": target.isoformat(), "opens_at": history[-1].session.opens_at.isoformat(),
        "next_session": next_session(target).isoformat(), "source": source, "candidates": candidates,
        "quotes": {
            symbol: {
                "current": current.get(symbol), "previous": previous.get(symbol),
                "diagnostic": gaps.get(symbol, "" if symbol in symbols else "SYMBOL_OUTSIDE_CURRENT_IWB_SCOPE"),
                "structures": {version: rows[symbol] for version, rows in grid.items() if symbol in rows},
            }
            for symbol in sorted(requested)
        },
    }
