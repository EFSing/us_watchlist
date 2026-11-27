"""Project validated regular-session bars and existing B/C results for display."""

from collections import Counter
from dataclasses import dataclass, replace
from decimal import Decimal
from statistics import median

from us_watchlist.domain.company_catalog import SECTORS, STYLES, company_name, issuer_key, sector_style
from us_watchlist.domain.models import MarketSnapshot, SessionBar, UniverseMember, UniverseSnapshot
from us_watchlist.domain.replay_research import TRANSITION, ReplayResearch
from us_watchlist.domain.screening import B_US_V2, ScreeningResult
from us_watchlist.domain.workbench import BCandidate, Breadth, BWatch, ChartDay, MarketGroup, MarketPulse, QuoteSummary, Workbench

_LAST = Decimal("Infinity")


@dataclass(frozen=True)
class _MarketRow:
    quote: QuoteSummary
    change_20: Decimal | None
    above_ma20: bool | None
    above_ma60: bool | None
    near_high60: bool | None
    b_match: bool


def _mean_close(bars: tuple[SessionBar, ...], sessions: int) -> Decimal:
    return sum(bar.close for bar in bars[-sessions:]) / Decimal(sessions)


def _breadth(values) -> Breadth:
    available = [value for value in values if value is not None]
    return Breadth(sum(available), len(available))


def _median(values) -> Decimal | None:
    available = [value for value in values if value is not None]
    return median(available) if available else None


def _group(name: str, style: str, rows: list[_MarketRow]) -> MarketGroup:
    return MarketGroup(
        name, style, len(rows), _median(row.quote.daily_change for row in rows),
        _median(row.change_20 for row in rows), _breadth(row.above_ma20 for row in rows),
        sum(row.b_match for row in rows),
    )


def _environment(short: Breadth, long: Breadth) -> str:
    a, b = short.ratio, long.ratio
    if a is None or b is None:
        return "宽度资料不足"
    if min(a, b) >= Decimal("0.60"):
        return "多头趋势扩张"
    if max(a, b) <= Decimal("0.40"):
        return "普跌防守"
    if abs(a - b) >= Decimal("0.15") or (a - Decimal("0.50")) * (b - Decimal("0.50")) < 0:
        return "结构分化轮动"
    return "震荡整理"


def _pulse(eligible: int, rows: list[_MarketRow]) -> MarketPulse:
    changes = [row.quote.daily_change for row in rows if row.quote.daily_change is not None]
    ma20 = _breadth(row.above_ma20 for row in rows)
    ma60 = _breadth(row.above_ma60 for row in rows)
    styles = tuple(_group(style, style, [row for row in rows if row.quote.style == style]) for style in STYLES)
    sectors = [_group(name, style, [row for row in rows if row.quote.sector == name])
               for name, style in SECTORS.values()]
    unknown = [row for row in rows if row.quote.style == "未分类"]
    if unknown:
        sectors.append(_group("未标注板块", "未分类", unknown))
    sectors.sort(key=lambda group: (-group.daily_median if group.daily_median is not None else _LAST, group.name))
    return MarketPulse(
        eligible, len(rows), sum(change > 0 for change in changes), sum(change < 0 for change in changes),
        changes.count(0), ma20, ma60, _breadth(row.near_high60 for row in rows), _environment(ma20, ma60),
        styles, tuple(sectors),
    )


def _ranking_risk(row: BCandidate) -> Decimal:
    if row.research.strategy_version == B_US_V2:
        risk_to_entry = dict(row.research.trade.inputs).get("risk_to_entry")
        if risk_to_entry is not None:
            return risk_to_entry
    return row.risk_to_close if row.risk_to_close is not None else _LAST


def _core_order(row: BCandidate) -> tuple:
    plan = row.research.trade.plan
    return (
        not row.fresh_turn, row.research.structure.stage != TRANSITION, not row.regime_aligned,
        _ranking_risk(row), -plan.rr if plan is not None else _LAST, row.quote.symbol,
    )


def _favored_styles(pulse: MarketPulse) -> set[str]:
    medians = {group.style: group.change_20_median for group in pulse.styles if group.change_20_median is not None}
    favored = set()
    if (pulse.environment in {"普跌防守", "震荡整理"}
            or ("防御" in medians and "成长" in medians and medians["防御"] > medians["成长"])):
        favored.add("防御")
    if medians:
        strongest = max(medians, key=medians.__getitem__)
        if pulse.environment == "多头趋势扩张" or medians[strongest] > 0:
            favored.add(strongest)
    return favored


def _fallback_order(row: BCandidate) -> tuple:
    return (
        row.research.structure.stage != TRANSITION, _ranking_risk(row),
        row.retest_ratio if row.retest_ratio is not None else _LAST, row.quote.symbol,
    )


def _funnel(matches: list[BCandidate]) -> tuple[tuple[BCandidate, ...], tuple[BCandidate, ...]]:
    qualified = sorted((row for row in matches if row.research.passed_b_numeric_gate), key=_core_order)
    fallback = sorted((
        row for row in matches if not row.research.passed_b_numeric_gate and row.research.trade.plan is not None
        and row.risk_to_close is not None and 0 < row.risk_to_close <= Decimal("0.06")
    ), key=_fallback_order)
    core, issuers = [], set()
    for row in qualified:
        if row.quote.issuer not in issuers:
            core.append(row)
            issuers.add(row.quote.issuer)
            if len(core) == 6:
                break
    for row in fallback:
        if len(core) >= 3:
            break
        if row.quote.issuer not in issuers:
            core.append(replace(row, supplemental=True))
            issuers.add(row.quote.issuer)
    selected = {row.quote.symbol for row in core}
    issuer_counts = Counter(row.quote.issuer for row in matches)
    other = tuple(replace(row, same_issuer=issuer_counts[row.quote.issuer] > 1) for row in matches
                  if row.quote.symbol not in selected)
    return tuple(core), other


def _chart(bars: tuple[SessionBar, ...], history: tuple[MarketSnapshot, ...]) -> tuple[ChartDay, ...]:
    start = max(0, len(bars) - 60)
    dates = tuple(snapshot.session.trading_date for snapshot in history[-len(bars):])
    return tuple(ChartDay(dates[i], bars[i], _mean_close(bars[i-19:i+1], 20) if i >= 19 else None)
                 for i in range(start, len(bars)))


def project_workbench(
    universe: UniverseSnapshot, eligible: tuple[str, ...], history: tuple[MarketSnapshot, ...],
    b: ScreeningResult, c: tuple[ScreeningResult, ...], research: ReplayResearch,
) -> Workbench:
    members = {member.symbol: member for member in universe.members}
    b_rows = {row.symbol: row for row in b.evaluations}
    matched = {row.symbol for row in b.evaluations if row.reason == "SHAPE_MATCH" and row.signal is not None}
    c_symbols = {row.symbol for rule in c for row in rule.evaluations if row.signal is not None}
    studies = {row.symbol: row for row in research.candidates if row.strategy_version == b.strategy.version}
    daily = [{bar.symbol: bar for bar in snapshot.bars} for snapshot in history[-120:]]
    market, candidates, watch, c_quotes = [], [], [], []
    for symbol in eligible:
        tail = []
        for session in reversed(daily):
            if symbol not in session:
                break
            tail.append(session[symbol])
        if not tail:
            continue
        bars = tuple(reversed(tail))
        member = members.get(symbol) or UniverseMember(symbol, True)
        sector, style = sector_style(member.sector)
        close = bars[-1].close
        quote = QuoteSummary(
            symbol, company_name(symbol, member.english_name), member.english_name, sector, style,
            member.market_weight, issuer_key(symbol, member.english_name), close,
            close / bars[-2].close - 1 if len(bars) >= 2 else None,
        )
        market.append(_MarketRow(
            quote, close / bars[-21].close - 1 if len(bars) >= 21 else None,
            close > _mean_close(bars, 20) if len(bars) >= 20 else None,
            close > _mean_close(bars, 60) if len(bars) >= 60 else None,
            close >= Decimal("0.95") * max(bar.high for bar in bars[-60:]) if len(bars) >= 60 else None,
            symbol in matched,
        ))
        if symbol in c_symbols:
            c_quotes.append(quote)
        evaluation = b_rows.get(symbol)
        if evaluation is None or (
            symbol not in matched and evaluation.reason != "FIRST_BREAKOUT_RETEST_FAILED"
        ):
            continue
        structure, volume = dict(evaluation.structure), dict(evaluation.volume)
        platform = structure["Platform"]
        value = volume["Retest mean volume / breakout"]
        ratio = Decimal(str(value)) if isinstance(value, (int, float, Decimal)) else None
        if symbol in matched:
            study = studies[symbol]
            risk = dict(study.trade.inputs).get("risk_to_close")
            if len(bars) == 120:
                low, high = min(bar.low for bar in bars), max(bar.high for bar in bars)
                position = (close - low) / (high - low) if high > low else Decimal("0.5")
            else:
                position = None
            candidates.append(BCandidate(
                evaluation, study, quote, platform, ratio, position, _chart(bars, history), risk,
                fresh_turn=structure.get("Fresh turn", True) is True,
            ))
        elif (structure["Near platform"] is True and volume["Retest contracted"] is True
              and structure.get("Trend MA50", True) is True and structure.get("Controlled pullback", True) is True
              and structure["Turn strength"] is False and ratio is not None):
            watch.append(BWatch(quote, platform, close / platform - 1, ratio))
    pulse = _pulse(len(eligible), market)
    favored = _favored_styles(pulse)
    core, other = _funnel([replace(row, regime_aligned=row.quote.style in favored) for row in candidates])
    watch.sort(key=lambda row: (abs(row.distance_to_platform), row.retest_ratio, row.quote.symbol))
    return Workbench(pulse, core, other, tuple(watch[:10]), tuple(c_quotes))
