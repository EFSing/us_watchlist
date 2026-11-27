import re
import unittest
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from us_watchlist.app.bc_offline import evaluate_joint, observe_joint, observe_workbench
from us_watchlist.app.replay import prepare_input
from us_watchlist.domain.company_catalog import COMPANIES, catalog_sector_style, company_name, issuer_key, sector_style
from us_watchlist.domain.models import (
    MarketSnapshot, PriceBasis, Provenance, SessionBar, SessionKind, SessionWindow, Signal, UniverseMember, UniverseSnapshot,
)
from us_watchlist.domain.replay_research import (
    TRANSITION, VOLUME_FIELDS, CandidateResearch, PlanObservation, PullbackVolume, ReferencePlan,
    ReplayResearch, StructureObservation, VolumeMeasure,
)
from us_watchlist.domain.screening import Evaluation, ScreeningResult
from us_watchlist.integrations.iwb_holdings import LATEST, parse_holdings, read_holdings
from us_watchlist.integrations.replay_input import read_replay
from us_watchlist.integrations.report_metadata import read_core_candidates
from us_watchlist.reporting.replay_html import render_joint_replay
from us_watchlist.reporting.workbench_html import chart_svg
from us_watchlist.strategies.b_breakout_retest import US_B_V2, BreakoutRetestShape
from us_watchlist.strategies.contracts import StrategyInput

ROOT = Path(__file__).resolve().parents[1]
B = BreakoutRetestShape.version
SECTORS = ("Utilities", "Information Technology", "Industrials", "")


class CatalogTests(unittest.TestCase):
    def test_frozen_holdings_have_chinese_names_and_exact_official_sectors(self):
        root = ROOT / ".runtime" / "data"
        archives = (*root.glob("iwb/IWB_*.zip"), *root.glob("iwb-validation/**/holdings.zip"))
        if not archives:
            self.skipTest("Local IWB archives unavailable")
        for archive in archives:
            with self.subTest(archive=archive):
                for member in read_holdings(archive).snapshot.members:
                    self.assertIn(member.symbol, COMPANIES)
                    self.assertRegex(company_name(member.symbol), r"[\u4e00-\u9fff]")
                    self.assertEqual(catalog_sector_style(member.symbol), sector_style(member.sector))
        self.assertEqual(company_name("JAN"), "杰纳斯养老地产")
        self.assertEqual(company_name("PPLI"), "人物传媒")
        self.assertEqual(company_name("UI"), "优倍快网络")

    def test_unknown_name_sector_and_share_classes(self):
        self.assertEqual(company_name("DEMOA", " Example   Tech, Inc. Class K  "), "Example Tech")
        self.assertEqual(company_name("ALFA"), "ALFA")
        self.assertEqual(company_name("ABC0", " "), "ABC0")
        self.assertEqual(sector_style(""), ("未标注板块", "未分类"))
        self.assertEqual(sector_style("Communication"), ("通信服务", "成长"))
        for a, b in (("GOOG", "GOOGL"), ("LLYVA", "LLYVK"), ("FWONA", "FWONK"), ("FOX", "FOXA"),
                     ("NWS", "NWSA"), ("BF-A", "BF-B"), ("LEN", "LEN-B"), ("UHAL", "UHAL-B"),
                     ("HEI", "HEI-A"), ("Z", "ZG")):
            self.assertEqual(issuer_key(a), issuer_key(b))
        self.assertEqual(issuer_key("ALFA", "Test Corp Class A"), issuer_key("ABC0", "TEST CLASS B"))
        self.assertNotEqual(issuer_key("LLYVA"), issuer_key("FWONA"))
        self.assertNotEqual(issuer_key("DEMOA"), issuer_key("ABC0"))

    def test_optional_iwb_columns_and_invalid_weights(self):
        raw = (
            'iShares Russell 1000 ETF\nFund Holdings as of,"Nov 26, 2025"\n'
            "Ticker,Asset Class,Exchange,Market Currency,Name,Sector,Market Weight\n"
        )
        rows = (
            'ABC0,Equity,NASDAQ,USD, Acme  Company ,Utilities," 1,234.50 "\n'
            'ABC1,Equity,NASDAQ,USD, ,,-\n'
            + "".join(f"ABC{i},Equity,NASDAQ,USD,,,\n" for i in range(2, 900))
        )
        provenance = Provenance(LATEST, "test", datetime(2025, 11, 28, tzinfo=UTC))
        version = parse_holdings((raw + rows).encode(), provenance)
        members = {member.symbol: member for member in version.snapshot.members}
        self.assertEqual(members["ABC0"], UniverseMember("ABC0", True, "Acme Company", "Utilities", Decimal("1234.50")))
        self.assertEqual(members["ABC1"], UniverseMember("ABC1", True))
        self.assertEqual(members["ABC2"], UniverseMember("ABC2", True))
        for invalid in ("-1", "NaN", "Infinity", "bogus"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_holdings((raw + rows.replace('" 1,234.50 "', invalid)).encode(), provenance)


def _inputs(symbols, missing=None):
    start = date(2026, 1, 1)
    history = []
    for i in range(120):
        day = start + timedelta(days=i)
        window = SessionWindow(day, SessionKind.REGULAR, datetime.combine(day, time(14), UTC),
                               datetime.combine(day, time(21), UTC))
        provenance = Provenance("test", str(day), window.closes_at)
        bars = []
        for j, symbol in enumerate(symbols):
            if missing == (symbol, i):
                continue
            close = Decimal(100 + (0, 10, -10)[j % 3] * (i == 119))
            bars.append(SessionBar(symbol, close, close + 1, close - 1, close, 100))
        history.append(MarketSnapshot(window, provenance, PriceBasis.YAHOO_CHART_QUOTE, tuple(bars)))
    members = tuple(UniverseMember(symbol, True, sector=SECTORS[i % 4]) for i, symbol in enumerate(symbols))
    pool = UniverseSnapshot(start, history[0].provenance, members)
    return pool, StrategyInput(provenance.available_at, tuple(symbols), tuple(history))


def _evaluation(inputs, symbol, *, match=True, near=True, contracted=True, turn=None, distance="0.01", ratio=.4):
    if turn is None:
        turn = match
    latest = inputs.history[-1].session
    close = next(bar.close for bar in inputs.history[-1].bars if bar.symbol == symbol)
    platform = close * (1 - Decimal(distance))
    structure = (("Platform", platform), ("Close / platform", close / platform),
                 ("Near platform", near), ("Turn strength", turn))
    volume = (("Retest mean volume / breakout", ratio), ("Retest contracted", contracted))
    if match:
        return Evaluation(symbol, "SHAPE_MATCH", 76, Signal(symbol, B, latest, inputs.cutoff), structure, volume)
    return Evaluation(symbol, "FIRST_BREAKOUT_RETEST_FAILED", 76, structure=structure, volume=volume)


def _study(symbol, *, passed=True, transition=True, risk="0.03", rr="2", recovery="0.55"):
    measure = tuple(VolumeMeasure(field, Decimal(".45")) for field in VOLUME_FIELDS)
    volume = PullbackVolume(None, None, None, 6, 3, 3, 0, measure)
    structure = StructureObservation(TRANSITION if transition else "EARLY_PULLBACK", recovery_ratio=Decimal(recovery))
    levels = ReferencePlan(Decimal(100), Decimal(95), Decimal(110), Decimal(100), Decimal(rr), "B_PRESSURE")
    trade = PlanObservation("B_NUMERIC_QUALIFIED" if passed else "B_NUMERIC_REJECTED",
                            None if passed else "B_RR_BELOW_TWO_AT_CLOSE", levels,
                            inputs=(("risk_to_close", Decimal(risk)),))
    return CandidateResearch(B.version, symbol, 120, "", structure, volume, trade)


class WorkbenchTests(unittest.TestCase):
    def test_market_breadth_uses_only_unbroken_price_windows(self):
        pool, inputs = _inputs(("AAPL", "MSFT", "CAT", "ALFA"), missing=("ALFA", 118))
        b = ScreeningResult(B, (_evaluation(inputs, "MSFT"),))
        view = observe_workbench(pool, inputs, b, (), ReplayResearch("test", "test", (_study("MSFT"),)))
        pulse = view.pulse
        self.assertEqual((pulse.observed, pulse.up, pulse.down, pulse.flat), (4, 1, 1, 1))
        self.assertEqual((pulse.above_ma20.count, pulse.above_ma20.sample), (1, 3))
        self.assertEqual((pulse.above_ma60.count, pulse.above_ma60.sample), (1, 3))
        self.assertEqual((pulse.near_high60.count, pulse.near_high60.sample), (2, 3))
        self.assertEqual(pulse.environment, "普跌防守")
        growth = pulse.styles[1]
        self.assertEqual((growth.sample, growth.daily_median, growth.change_20_median, growth.b_matches),
                         (1, Decimal(".1"), Decimal(".1"), 1))
        self.assertEqual(pulse.sectors[0].name, "信息技术")
        unknown = next(group for group in pulse.sectors if group.style == "未分类")
        self.assertEqual((unknown.sample, unknown.daily_median, unknown.above_ma20.sample), (1, None, 0))

    def test_core_ranking_caps_six_and_reserves_one_class_per_issuer(self):
        symbols = ("LLYVA", "LLYVK", "UI", "AAPL", "MSFT", "OGE", "JAN", "WST")
        pool, inputs = _inputs(symbols)
        b = ScreeningResult(B, tuple(_evaluation(inputs, symbol) for symbol in symbols))
        studies = (
            _study("LLYVA", rr="2.5"), _study("LLYVK", rr="3"), _study("UI", risk=".02"),
            _study("AAPL", transition=False, recovery=".49"), _study("MSFT", transition=False, recovery=".48"),
            _study("OGE", transition=False, recovery=".47"), _study("JAN", transition=False, recovery=".46"),
            _study("WST", transition=False, recovery=".45"),
        )
        view = observe_workbench(pool, inputs, b, (), ReplayResearch("test", "test", studies))
        self.assertEqual([row.quote.symbol for row in view.core], ["LLYVA", "UI", "MSFT", "AAPL", "JAN", "OGE"])
        self.assertEqual([(row.quote.symbol, row.same_issuer) for row in view.other], [("LLYVK", True), ("WST", False)])
        self.assertFalse(any(row.supplemental for row in view.core))

    def test_supplemental_selection_and_prep_pool_have_independent_filters(self):
        matches = ("LLYVA", "LLYVK", "DLTR", "VIK", "SIRI", "UI")
        watch = tuple(f"PREP{i}" for i in range(14))
        pool, inputs = _inputs((*matches, *watch))
        b_rows = [_evaluation(inputs, symbol, ratio=.55 if symbol == "VIK" else .4) for symbol in matches]
        b_rows.extend(_evaluation(inputs, symbol, match=False, near=i != 11, contracted=i != 12, turn=i == 13,
                                  distance=".01" if i < 2 else ".02", ratio=.3 if i == 1 else .4)
                      for i, symbol in enumerate(watch))
        studies = (
            _study("LLYVA"), _study("LLYVK", passed=False, risk=".01"),
            _study("DLTR", passed=False, transition=False, risk=".01"),
            _study("VIK", passed=False, risk=".06"), _study("SIRI", passed=False, risk=".0601"),
            _study("UI", passed=False, risk=".06"),
        )
        b = ScreeningResult(B, tuple(b_rows))
        view = observe_workbench(pool, inputs, b, (), ReplayResearch("test", "test", studies))
        self.assertEqual([(row.quote.symbol, row.supplemental) for row in view.core],
                         [("LLYVA", False), ("UI", True), ("VIK", True)])
        self.assertEqual(len(view.watch), 10)
        self.assertEqual([row.quote.symbol for row in view.watch[:2]], ["PREP1", "PREP0"])
        self.assertTrue(set(watch[11:]).isdisjoint(row.quote.symbol for row in view.watch))
        self.assertEqual(len(view.core[0].chart), 60)
        self.assertEqual(view.core[0].chart[0].ma20, Decimal(100))
        svg = chart_svg(view.core[0])
        for label in ("<svg", "price-band", "price-close", "price-ma20", "volumes", "guide platform", "guide trigger", "guide stop"):
            self.assertIn(label, svg)

    def test_v2_core_prioritizes_freshness_then_stage_and_favored_style(self):
        symbols = ("OGE", "MSFT", "CAT", "WST", "AEE", "AAPL")
        pool, inputs = _inputs(symbols)
        version = US_B_V2.version
        evaluations = []
        for symbol in symbols:
            row = _evaluation(inputs, symbol)
            evaluations.append(replace(row, signal=replace(row.signal, strategy=version),
                                       structure=(*row.structure, ("Fresh turn", symbol != "AEE"))))
        studies = tuple(replace(_study(symbol, transition=symbol != "AAPL", risk=risk),
                                strategy_version=version.version)
                        for symbol, risk in zip(symbols, (".04", ".03", ".01", ".02", ".01", ".05")))
        view = observe_workbench(pool, inputs, ScreeningResult(version, tuple(evaluations)), (),
                                 ReplayResearch("test", "test", studies))
        self.assertEqual(view.pulse.environment, "普跌防守")
        self.assertEqual([row.quote.symbol for row in view.core], ["OGE", "CAT", "WST", "MSFT", "AAPL", "AEE"])
        self.assertEqual({row.quote.symbol for row in view.core if row.regime_aligned}, {"OGE", "AEE"})
        self.assertFalse(view.core[-1].fresh_turn)

    def test_v2_prep_pool_requires_both_guardrails(self):
        symbols = ("PASS", "TREND", "PULLBACK", "TURN")
        pool, inputs = _inputs(symbols)
        rows = []
        for symbol in symbols:
            row = _evaluation(inputs, symbol, match=False, turn=symbol == "TURN")
            rows.append(replace(row, structure=(
                *row.structure, ("Trend MA50", symbol != "TREND"), ("Controlled pullback", symbol != "PULLBACK"),
            )))
        b = ScreeningResult(US_B_V2.version, tuple(rows))
        view = observe_workbench(pool, inputs, b, (), ReplayResearch("test", "test", ()))
        self.assertEqual([row.quote.symbol for row in view.watch], ["PASS"])

    def test_workbench_html_preserves_all_machine_record_bytes(self):
        data = read_replay(ROOT / "configs" / "b_demo" / "replay.toml")
        evidence, inputs = prepare_input(data)
        b, c = evaluate_joint(inputs)
        research = observe_joint(evidence, inputs, b, c)
        view = observe_workbench(data.candidates.snapshot, inputs, b, c, research)
        view = replace(view, core=view.other, other=())
        old = render_joint_replay(evidence, b, c, research=research)
        new = render_joint_replay(evidence, b, c, research=research, workbench=view)
        records = r'<script type="application/json" .*?</script>'
        self.assertEqual(re.findall(records, new, re.S), re.findall(records, old, re.S))
        self.assertNotRegex(new, r"<(?:script|link|iframe|img)\b[^>]*\b(?:src|href)=")
        self.assertNotRegex(new, r"<details[^>]*\bopen\b")
        ids = re.findall(r'(?<![\w-])id="([^"]+)"', new)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(re.findall(r'href="#([^"]+)"', new)).issubset(ids))
        anchors = ('</head>', '<a href="#overview">今日总览</a>', '<section id="candidates" class="panel">')
        self.assertEqual([new.count(anchor) for anchor in anchors], [1, 1, 1])
        self.assertEqual([new.index(anchor) for anchor in anchors], sorted(new.index(anchor) for anchor in anchors))
        self.assertEqual(read_core_candidates(new.encode("utf-8")), (("DEMOA", "DEMOA", "未标注板块"),))
        self.assertIn(f'id="{US_B_V2.version.version}-DEMOA"', new)
        self.assertIn('class="pill signal-fresh">今日新转强', new)
        self.assertNotIn("其他指标（见原始记录）", new)
        self.assertEqual(read_core_candidates(old.encode("utf-8")), ())
