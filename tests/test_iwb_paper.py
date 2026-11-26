import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from us_watchlist.app.iwb_paper import run_study
from us_watchlist.app.paper_inputs import _screening, _structure_origin, load_day
from us_watchlist.domain.paper import (
    BASIS, B_VERSION, POSITION_PROTOCOL, PROTOCOL, RETIRED_STRATEGIES, STRATEGIES, Mode, Status, check_policy,
)
from us_watchlist.domain.replay_research import VOLUME_FIELDS
from us_watchlist.integrations.paper_archive import read_report_records
from us_watchlist.integrations.xnys import next_session, regular_windows
from us_watchlist.reporting.paper_html import render_paper
from us_watchlist.tracking.paper import summarize
from us_watchlist.tracking.paper_position import PositionIndicators

START = date(2026, 1, 5)
T1 = date(2026, 1, 6)
T2 = date(2026, 1, 7)
T3 = date(2026, 1, 8)
_, BALANCED = STRATEGIES
CONSERVATIVE, = RETIRED_STRATEGIES
RULE = {"min_actual_rr": "2", "min_target_upside": "0.05", "max_open_premium": "0.08", "exit_model": "FIXED_STOP"}
POLICY = {
    B_VERSION: {"B_NUMERIC_QUALIFIED:UNKNOWN": RULE},
    BALANCED: {"C_PRICE_RESEARCH:CLEAR": RULE},
}
SIGNAL_BAR = ("100", "104", "96", "101")


def candidate(symbol, strategy=B_VERSION, *, rejected=False, warning="UNKNOWN"):
    qualification = "C_PRICE_RESEARCH" if strategy != B_VERSION else (
        "B_NUMERIC_REJECTED" if rejected else "B_NUMERIC_QUALIFIED"
    )
    return {
        "symbol": symbol, "strategy_version": strategy, "matched": True, "qualification": qualification,
        "qualification_reason": None, "risk_warning": warning, "structure": {"stage": "W2_TO_W3_TRANSITION_PROXY"},
        "volume": [{"field": field, "value": "1"} for field in VOLUME_FIELDS],
        "levels": {"trigger": "100", "stop": "95", "target": "120", "entry": "100", "rr": "4", "target_rule": "TEST"},
        "reference_missing_reason": None,
    }


def evidence(day, candidates=(), *, bars=None, prior=None):
    bars = bars or {}
    prior = prior or {}
    symbols = set(bars) | set(prior) | {plan["symbol"] for plan in candidates}
    return {
        "trade_date": str(day), "opens_at": f"{day}T14:30:00+00:00", "next_session": str(next_session(day)),
        "source": {
            "observed_at": f"{day}T22:00:00+00:00", "report_id": f"synthetic-{day}", "report_sha256": "a" * 64,
            "input_sha256": sha256(str(day).encode()).hexdigest(), "research_version": "synthetic-research",
        },
        "candidates": list(candidates),
        "quotes": {
            symbol: {
                "current": list(bars.get(symbol, SIGNAL_BAR)) if bars.get(symbol, True) is not None else None,
                "previous": list(prior.get(symbol, SIGNAL_BAR)) if prior.get(symbol, True) is not None else None,
                "diagnostic": "YAHOO_SPLIT_BASIS_UNVERIFIED" if bars.get(symbol, True) is None else "",
                "structures": {B_VERSION: "W2_TO_W3_TRANSITION_PROXY", BALANCED: "C_CLOSE_REBOUND_CONFIRMED"},
            }
            for symbol in sorted(symbols)
        },
    }


def demo_days():
    narrow_target = candidate("INDI", BALANCED, warning="CLEAR")
    narrow_target["levels"].update(target="108", rr="1.6")
    first = evidence(START, (
        candidate("ALFA"), candidate("BRAV", BALANCED, warning="CLEAR"),
        candidate("CHAR", BALANCED, warning="WARNING"), candidate("DELT", rejected=True),
        candidate("ECHO"), candidate("FOXT"), candidate("GOLF"), candidate("HOTL"),
        narrow_target, candidate("JULI"),
    ))
    second = evidence(T1, bars={
        "ALFA": ("100", "114", "98", "105"), "BRAV": ("101", "113", "98", "107"),
        "CHAR": SIGNAL_BAR, "DELT": SIGNAL_BAR, "ECHO": ("97", "125", "96", "108"),
        "FOXT": ("95", "101", "92", "96"), "GOLF": ("120", "124", "119", "122"),
        "HOTL": ("108", "110", "101", "103"), "INDI": ("104", "108", "100", "105"),
        "JULI": ("109", "111", "99", "107"),
    })
    third = evidence(T2, bars={
        "ALFA": ("102", "130", "93", "122"), "BRAV": ("110", "122", "109", "121"),
    }, prior={symbol: second["quotes"][symbol]["current"] for symbol in ("ALFA", "BRAV")})
    fourth = evidence(T3, bars={"BRAV": ("90", "120", "85", "111")}, prior={"BRAV": third["quotes"]["BRAV"]["current"]})
    return first, second, third, fourth


def run_day(root, day, *, policy=POLICY, **options):
    def load(symbols):
        if symbols - day["quotes"].keys():
            raise AssertionError("Synthetic archive missing quote evidence")
        return day

    return run_study(
        root, Mode.SYNTHETIC, START, date.fromisoformat(day["trade_date"]), policy,
        evidence_loader=load, **options,
    )


def screening_archive(day, versions):
    fields = {"trade_date": str(day), "cutoff": f"{day}T22:00:00+00:00", "manifest_sha256": "test-sha",
              "mode": "iwb_yahoo_observation"}
    run = {"trade_date": str(day), "observed_at": fields["cutoff"], "input_sha256": fields["manifest_sha256"],
           "strategies": {version: {"matches": 0} for version in versions}}
    records = {version: {**fields, "schema": "us_offline_screening_v1", "version": version, "error": None,
                         "evaluations": [{"symbol": "ALFA", "matched": False, "reason": "NO_MATCH"}]}
               for version in versions}
    records["record-research"] = {**fields, "price_basis": BASIS, "candidates": []}
    return run, records


def position_policy(**model):
    return {
        B_VERSION: {"B_NUMERIC_QUALIFIED:UNKNOWN": {
            **RULE, "exit_model": {
                "reject_open_at_or_below_structure": False, "structure_exit": False, "pivot": None,
                "atr_trail": None, "profit_protection": None, **model,
            },
        }},
    }


def position_day(day, *, bar=SIGNAL_BAR, previous=SIGNAL_BAR, signal=False):
    plan = candidate("ALFA")
    plan["structure_origin"] = {
        "floor_anchor": "L2", "points": {"L2": ["2026-01-02", "97"]}, "known_on": str(START),
    }
    data = evidence(day, (plan,) if signal else (), bars={"ALFA": bar}, prior={"ALFA": previous})
    current, following = regular_windows(next_session(day), 2)
    data.update(opens_at=current.opens_at.isoformat(), closes_at=current.closes_at.isoformat(),
                next_opens_at=following.opens_at.isoformat(), seeds={})
    data["source"].update(price_basis=BASIS, observed_at=(current.closes_at + timedelta(hours=1)).isoformat())
    return data


class PaperTests(unittest.TestCase):
    def setUp(self):
        root = Path(".runtime/tmp")
        root.mkdir(parents=True, exist_ok=True)
        temp = TemporaryDirectory(dir=root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    @staticmethod
    def by_symbol(view):
        return {row["plan"]["symbol"]: row for row in view["records"].values()}

    def position_session(self, day, policy, **options):
        return run_day(self.root, day, policy=policy, protocol=POSITION_PROTOCOL, **options)

    def test_combined_view_includes_open_positions_on_the_daily_page(self):
        first, second, _, _ = demo_days()
        daily = (
            '<!doctype html><html><head><title>IWB</title></head><body><main>'
            '<nav class="section-nav"><a href="#overview">今日总览</a></nav>'
            '<section id="overview">原始总览</section>'
            '<section id="candidates" class="panel">B/C 逐股候选</section></main></body></html>'
        ).encode("utf-8")
        for day in (first, second):
            day["source"]["report_sha256"] = sha256(daily).hexdigest()
        run_day(self.root, first, initialize=True, combined=True, archived_report=daily)
        output, _ = run_day(self.root, second, combined=True, archived_report=daily)
        report = (output / "report.html").read_text(encoding="utf-8")
        self.assertEqual(report.count("<main>"), 1)
        self.assertIn('href="#paper-research"', report)
        self.assertIn("B/C 逐股候选", report)
        self.assertIn("ALFA · B 突破回踩", report)
        self.assertIn("BRAV · C 均衡", report)
        self.assertIn("浮动 R", report)
        self.assertIn("当前模拟持仓<strong>2 只</strong>", report)
        self.assertLess(report.index('id="paper-research"'), report.index('id="candidates"'))

    def test_structure_trail_uses_confirmation_close_atr_and_restarts_with_scheduled_stop(self):
        policy = position_policy(
            structure_exit=True, pivot={"radius": 1, "min_separation": 2, "require_rebound": False},
            atr_trail={"period": 1, "multiple": "0.5"},
        )
        signal = position_day(START, signal=True)
        signal["seeds"] = {"ALFA": [[str(START), signal["quotes"]["ALFA"]["current"]]]}
        self.position_session(signal, policy, initialize=True)
        previous = SIGNAL_BAR
        for day, bar in (
            (T1, ("100", "112", "100", "106")), (T2, ("106", "107", "103", "105")),
            (T3, ("105", "106", "101", "104")),
        ):
            _, view = self.position_session(position_day(day, bar=bar, previous=previous), policy)
            state = self.by_symbol(view)["ALFA"]["position"]
            self.assertIsNone(state.get("protected_low"))
            self.assertEqual(state["stop"], "95")
            previous = bar

        day = next_session(T3)
        bar = ("104", "106", "102", "105")
        output, view = self.position_session(position_day(day, bar=bar, previous=previous), policy)
        state = self.by_symbol(view)["ALFA"]["position"]
        self.assertEqual((state["structural_floor"], state["structure_atr"], state["active_stop_at_open"], state["stop"]),
                         ("101", "4", "95", "99.0"))
        self.assertEqual(state["protected_low"]["pivot_date"], str(T3))
        self.assertEqual(state["protected_low"]["confirmed_on"], str(day))
        priced = (output / "paper-report.html").read_bytes()
        (output / "paper-report.html").unlink()
        restored = run_study(self.root, Mode.SYNTHETIC, START, day, policy, protocol=POSITION_PROTOCOL)[1]
        self.assertEqual(restored, view)
        self.assertEqual((output / "paper-report.html").read_bytes(), priced)

        following = next_session(day)
        wider_bar = ("105", "111", "100", "106")
        _, view = self.position_session(position_day(following, bar=wider_bar, previous=bar), policy)
        state = self.by_symbol(view)["ALFA"]["position"]
        self.assertEqual((state["structure_atr"], state["structure_stop_candidate"], state["stop"]),
                         ("11", "95.5", "99.0"))
        _, stopped = self.position_session(
            position_day(next_session(following), bar=("106", "125", "99", "110"), previous=wider_bar), policy,
        )
        position = self.by_symbol(stopped)["ALFA"]["position"]
        self.assertEqual((position["exit_reason"], position["exit_price"], position["active_stop_sources"]),
                         ("ACTIVE_STOP_TOUCHED", "99.0", ["STRUCTURE_STOP"]))
        self.assertEqual((position["mfe_r"], position["target_seen"]), ("2.4", False))

    def test_structure_has_priority_over_profit_and_new_gap_at_the_open(self):
        policy = position_policy(structure_exit=True, profit_protection={"trigger_r": "2", "giveback_r": "1"})
        self.position_session(position_day(START, signal=True), policy, initialize=True)
        broken = ("100", "110", "96", "96")
        output, pending = self.position_session(position_day(T1, bar=broken), policy)
        position = self.by_symbol(pending)["ALFA"]["position"]
        reasons = ["STRUCTURE_NEXT_OPEN", "PROFIT_PROTECTION_NEXT_OPEN"]
        self.assertEqual(position["pending_exit"]["reasons"], reasons)
        self.assertEqual((position["pending_exit"]["session"], position["stop"]), (str(T2), "95"))
        self.assertIn("待开盘退出 1 笔", (output / "paper-email.txt").read_text(encoding="utf-8"))
        restored = run_study(self.root, Mode.SYNTHETIC, START, T1, policy, protocol=POSITION_PROTOCOL)[1]
        self.assertEqual(restored, pending)

        gap = position_day(T2, bar=("93", "126", "92", "120"), previous=broken)
        gap["quotes"]["ALFA"]["structures"][B_VERSION] = "POST_EXIT_STRUCTURE"
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.position_session(gap, policy)[1], range(2)))
        self.assertEqual(results[0], results[1])
        closed = self.by_symbol(results[0])["ALFA"]["position"]
        self.assertEqual((closed["exit_reason"], closed["exit_reasons"], closed["exit_price"]),
                         ("STRUCTURE_NEXT_OPEN", [*reasons, "GAP_THROUGH_STOP"], "93"))
        self.assertEqual((closed["mfe_r"], closed["max_mfe_drawdown_r"], closed["target_seen"]), ("2", "3.4", False))
        self.assertNotEqual(closed["structure"], "POST_EXIT_STRUCTURE")

    def test_position_protocol_keeps_fixed_gap_equality_and_stop_day_high_unknown(self):
        policy = position_policy()
        alive = ("100", "106", "96", "101")
        options = {"policy": policy, "protocol": POSITION_PROTOCOL}
        for opening, low, price, reason, result in (
            ("94", "93", "94", "GAP_THROUGH_STOP", "-1.2"),
            ("95", "92", "95", "GAP_THROUGH_STOP", "-1"),
            ("101", "95", "95", "ACTIVE_STOP_TOUCHED", "-1"),
        ):
            with self.subTest(opening=opening):
                root = self.root / opening
                run_day(root, position_day(START, signal=True), initialize=True, **options)
                run_day(root, position_day(T1, bar=alive), **options)
                day = position_day(T2, bar=(opening, "125", low, "110"), previous=alive)
                output, view = run_day(root, day, **options)
                position = self.by_symbol(view)["ALFA"]["position"]
                self.assertEqual((position["exit_price"], position["exit_reason"], position["r"]), (price, reason, result))
                self.assertEqual((position["mfe_r"], position["target_seen"]), ("1.2", False))
                receipt = (output / "day.json").read_bytes()
                day["quotes"]["ALFA"]["current"][1] = "126"
                with self.assertRaisesRegex(ValueError, "identity already used"):
                    run_day(root, day, **options)
                self.assertEqual((output / "day.json").read_bytes(), receipt)

    def test_exact_profit_boundary_then_pending_open_does_not_add_target(self):
        policy = position_policy(profit_protection={"trigger_r": "2", "giveback_r": "1"})
        self.position_session(position_day(START, signal=True), policy, initialize=True)
        first = ("100", "110", "96", "105")
        _, view = self.position_session(position_day(T1, bar=first), policy)
        position = self.by_symbol(view)["ALFA"]["position"]
        self.assertEqual((position["active_stop_at_open"], position["stop"], position["initial_stop"]),
                         ("95", "105", "95"))
        second = ("109", "115", "106", "109")
        _, view = self.position_session(position_day(T2, bar=second, previous=first), policy)
        position = self.by_symbol(view)["ALFA"]["position"]
        self.assertEqual((position["protection_floor"], position["pending_exit"]["reasons"]),
                         ("110", ["PROFIT_PROTECTION_NEXT_OPEN"]))
        _, view = self.position_session(position_day(T3, bar=("120", "125", "90", "100"), previous=second), policy)
        position = self.by_symbol(view)["ALFA"]["position"]
        self.assertEqual((position["exit_price"], position["r"], position["mfe_r"], position["target_seen"]),
                         ("120", "4", "4", False))

    def test_structure_touch_holds_and_missing_appointment_session_suspends(self):
        policy = position_policy(structure_exit=True)
        self.position_session(position_day(START, signal=True), policy, initialize=True)
        touch = ("100", "103", "96", "97")
        _, view = self.position_session(position_day(T1, bar=touch), policy)
        self.assertIsNone(self.by_symbol(view)["ALFA"]["position"]["pending_exit"])
        broken = ("98", "100", "96", "96")
        self.position_session(position_day(T2, bar=broken, previous=touch), policy)
        _, missing = self.position_session(position_day(T3, bar=None, previous=broken), policy)
        following = next_session(T3)
        _, view = self.position_session(position_day(following, bar=("94", "100", "92", "98"), previous=broken), policy)
        missing_row = self.by_symbol(missing)["ALFA"]
        later = self.by_symbol(view)["ALFA"]
        self.assertEqual(later["position"], missing_row["position"])
        self.assertEqual(later["position"]["pending_exit"]["session"], str(T3))
        self.assertEqual(later["position"]["priced_on"], str(T2))
        self.assertEqual(later["history"][-1]["reason"], "UNRESOLVED_PRIOR_GAP")

    def test_position_protocol_rejects_late_management_and_bad_session_evidence(self):
        policy = position_policy(structure_exit=True)
        self.position_session(position_day(START, signal=True), policy, initialize=True)
        day = position_day(T1, bar=("100", "110", "96", "96"))
        too_early = deepcopy(day)
        too_early["source"]["observed_at"] = too_early["opens_at"]
        with self.assertRaisesRegex(ValueError, "PAPER_POSITION_EVIDENCE_MISMATCH"):
            self.position_session(too_early, policy)
        wrong_session = {**day, "next_session": str(T3)}
        with self.assertRaisesRegex(ValueError, "PAPER_POSITION_SESSION_MISMATCH"):
            self.position_session(wrong_session, policy)
        day["source"]["observed_at"] = day["next_opens_at"]
        _, view = self.position_session(day, policy)
        row = self.by_symbol(view)["ALFA"]
        self.assertEqual((row["history"][-1]["reason"], row["suspended_at"]), ("LATE_CLOSE_EVIDENCE", str(T1)))
        self.assertIsNone(row["position"]["pending_exit"])

    def test_rebound_requires_its_right_window_and_atr_warms_up_from_contiguous_seed(self):
        indicators = PositionIndicators(
            {"pivot": {"radius": 1, "min_separation": 2, "require_rebound": True},
             "atr_trail": {"period": 3}}, [], str(T1),
        )
        for day, bar in (
            (T1, ("102", "105", "101", "103")), (T2, ("103", "104", "100", "102")),
            (T3, ("102", "108", "102", "106")),
        ):
            self.assertIsNone(indicators.observe(str(day), tuple(map(Decimal, bar)), Decimal(97)))
            self.assertIsNone(indicators.atr)
        day = next_session(T3)
        low = indicators.observe(str(day), tuple(map(Decimal, ("106", "107", "103", "104"))), Decimal(97))
        self.assertEqual(low, {"pivot_date": str(T2), "confirmed_on": str(day), "price": "100", "rebound_date": str(T3)})
        self.assertEqual(indicators.atr, Decimal(14) / 3)

    def test_structure_origin_uses_each_rules_frozen_lows(self):
        b = {"strategy_version": B_VERSION, "structure": {"stage": "EARLY_PULLBACK", "points": [
            ["L0", "2025-12-29", "90"], ["H1", "2025-12-30", "110"], ["L2", "2026-01-02", "97"],
        ]}}
        self.assertEqual(_structure_origin(b, {}, str(START))["floor_anchor"], "L2")
        for version in (BALANCED, CONSERVATIVE):
            c = {"strategy_version": version, "structure": {"stage": "C_CLOSE_REBOUND_CONFIRMED", "points": [
                ["C_PRIOR_HIGH", "2025-12-29", "110"], ["C_SUPPORT_FLOOR", "2025-12-30", "93"],
                ["C_REBOUND_HIGH", "2026-01-02", "101"],
            ]}}
            evaluation = {"structure": {"Second low date": "2025-12-31", "Support ceiling": 97}}
            origin = _structure_origin(c, evaluation, str(START))
            self.assertEqual(origin["floor_anchor"], "C_SUPPORT_FLOOR")
            self.assertEqual(origin["points"]["C_SECOND_LOW"], ["2025-12-31", "97"])

    def test_full_lifecycle_and_all_open_checks(self):
        first, second, third, fourth = demo_days()
        output, t = run_day(self.root, first, initialize=True)
        self.assertEqual({row["status"] for row in t["records"].values()}, {Status.PENDING})
        self.assertIn("当前模拟持仓 0 只", (output / "paper-report.html").read_text(encoding="utf-8"))
        self.assertIn("当前模拟持仓 0 只", (output / "paper-email.txt").read_text(encoding="utf-8"))

        output, t1 = run_day(self.root, second, expect_previous=t["ledger_sha256"])
        rows = self.by_symbol(t1)
        for symbol, reason in {
            "CHAR": "COHORT_NOT_ENABLED", "DELT": "COHORT_NOT_ENABLED", "ECHO": "OPEN_BELOW_TRIGGER",
            "FOXT": "OPEN_AT_OR_BELOW_STOP", "GOLF": "OPEN_AT_OR_ABOVE_TARGET",
            "HOTL": "RR_BELOW_CONFIGURED_MINIMUM", "INDI": "TARGET_UPSIDE_BELOW_CONFIGURED_MINIMUM",
            "JULI": "OPEN_ABOVE_CONFIGURED_PREMIUM",
        }.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(rows[symbol]["status"], Status.NOT_FILLED)
                self.assertEqual(rows[symbol]["history"][-1]["reason"], reason)
                self.assertIsNone(rows[symbol]["position"])
        self.assertEqual(rows["ALFA"]["position"]["r"], "1")
        self.assertEqual(rows["ALFA"]["position"]["mfe_r"], "2.8")
        self.assertEqual(rows["ALFA"]["position"]["mae_r"], "-0.4")
        self.assertEqual(rows["ALFA"]["position"]["initial_rr"], "4")
        self.assertEqual(rows["ALFA"]["position"]["units"], 1)
        self.assertIn("当前模拟持仓 2 只", (output / "paper-report.html").read_text(encoding="utf-8"))
        self.assertTrue(all(stat["win_rate"] is None for stat in t1["performance"]))

        output, t2 = run_day(self.root, third)
        rows = self.by_symbol(t2)
        self.assertEqual(rows["ALFA"]["status"], Status.CLOSED)
        self.assertEqual(rows["ALFA"]["position"]["exit_price"], "95")
        self.assertEqual(rows["ALFA"]["position"]["r"], "-1")
        self.assertEqual(rows["ALFA"]["position"]["mfe_r"], "2.8")
        self.assertEqual(rows["ALFA"]["position"]["mae_r"], "-1")
        self.assertFalse(rows["ALFA"]["position"]["target_seen"])
        self.assertEqual(rows["BRAV"]["position"]["priced_on"], str(T2))
        self.assertTrue(rows["BRAV"]["position"]["target_seen"])
        self.assertEqual(rows["BRAV"]["status"], Status.OPEN)
        self.assertIn("当前模拟持仓 1 只", (output / "paper-report.html").read_text(encoding="utf-8"))
        b_stat, c_stat, *_ = t2["performance"]
        self.assertNotIn(CONSERVATIVE, {row["group"] for row in t2["performance"]})
        self.assertEqual((b_stat["win_rate"], b_stat[Status.CLOSED], b_stat["mean_r"]), (0, 1, -1))
        self.assertEqual((c_stat[Status.OPEN], c_stat["total_r"]), (1, 0))
        _, t3 = run_day(self.root, fourth)
        state = self.by_symbol(t3)["BRAV"]["position"]
        self.assertEqual((state["exit_reason"], state["exit_price"], state["r"][:7]),
                         ("GAP_THROUGH_STOP", "90", "-1.8333"))

    def test_entry_day_stop_is_sequenced_after_open(self):
        day = evidence(START, (candidate("ALFA"), candidate("ALFA", BALANCED, warning="CLEAR")))
        run_day(self.root, day, initialize=True)
        _, view = run_day(self.root, evidence(T1, bars={"ALFA": ("100", "125", "90", "120")}))
        self.assertEqual(len(view["records"]), 2)
        for row in view["records"].values():
            self.assertEqual([event["status"] for event in row["history"]], [Status.PENDING, Status.OPEN, Status.CLOSED])
            self.assertEqual((row["position"]["mfe_r"], row["position"]["mae_r"]), ("0", "-1"))
        self.assertEqual({row["plan"]["risk_warning"] for row in view["records"].values()}, {"CLEAR", "UNKNOWN"})

    def test_legacy_r_protection_is_causal_and_only_realizes_on_exit(self):
        rule = {**RULE, "exit_model": "LEGACY_R_PROTECTION"}
        policy = {B_VERSION: {"B_NUMERIC_QUALIFIED:UNKNOWN": rule}}
        run_day(self.root, evidence(START, (candidate("ALFA"),)), initialize=True, policy=policy)
        day = ("100", "111", "98", "108")
        _, raised = run_day(self.root, evidence(T1, bars={"ALFA": day}), policy=policy)
        row = self.by_symbol(raised)["ALFA"]
        self.assertEqual((row["position"]["stop"], row["history"][-1]["reason"]),
                         ("106.0", "STOP_RAISED_FOR_NEXT_SESSION"))
        self.assertIsNone(raised["performance"][0]["win_rate"])
        second = ("109", "115", "108", "109")
        _, pending = run_day(self.root, evidence(T2, bars={"ALFA": second}, prior={"ALFA": day}), policy=policy)
        row = self.by_symbol(pending)["ALFA"]
        self.assertTrue(row["position"]["exit_next_open"])
        self.assertEqual(row["history"][-1]["reason"], "PROFIT_PROTECTION_ARMED")
        _, ended = run_day(self.root, evidence(T3, bars={"ALFA": ("108", "125", "90", "110")},
                                              prior={"ALFA": second}), policy=policy)
        final = self.by_symbol(ended)["ALFA"]["position"]
        self.assertEqual((final["exit_reason"], final["exit_price"], final["mfe_r"]),
                         ("PROFIT_PROTECTION_NEXT_OPEN", "108", "3"))
        self.assertEqual(ended["performance"][0]["win_rate"], 1)
        self.assertEqual(str(ended["performance"][0]["total_r"]), "1.6")

    def test_missing_next_bar_delayed_signal_and_price_basis_conflict(self):
        first = evidence(START, (candidate("ALFA"), candidate("BRAV"), candidate("CHAR")))
        first["source"]["observed_at"] = str(T1) + "T14:30:00+00:00"
        run_day(self.root, first, initialize=True)
        _, view = run_day(self.root, evidence(T1, bars={symbol: SIGNAL_BAR for symbol in ("ALFA", "BRAV", "CHAR")}))
        self.assertTrue(all(row["history"][-1]["reason"] == "SIGNAL_NOT_KNOWN_BEFORE_T1_OPEN"
                            for row in view["records"].values()))

        first = evidence(START, (candidate("ALFA"), candidate("BRAV"), candidate("CHAR")))
        root = self.root / "timely"
        run_day(root, first, initialize=True)
        _, view = run_day(root, evidence(T1, bars={"ALFA": None, "CHAR": SIGNAL_BAR},
                                       prior={"BRAV": ("90", "91", "89", "90"), "CHAR": None}))
        rows = self.by_symbol(view)
        self.assertEqual(rows["ALFA"]["history"][-1]["reason"], "MISSING_OR_SPLIT_UNVERIFIED_YAHOO_BAR")
        self.assertEqual(rows["ALFA"]["history"][-1]["diagnostic"], "YAHOO_SPLIT_BASIS_UNVERIFIED")
        self.assertEqual(rows["BRAV"]["history"][-1]["reason"], "PRIOR_PRICE_BASIS_CHANGED")
        self.assertEqual(rows["CHAR"]["status"], Status.UNAVAILABLE)
        _, later = run_day(root, evidence(T2))
        self.assertEqual(view["records"], later["records"])

    def test_open_gap_retains_price_and_freezes_until_chain_recovery(self):
        run_day(self.root, evidence(START, (candidate("ALFA"),)), initialize=True)
        _, first = run_day(self.root, evidence(T1, bars={"ALFA": SIGNAL_BAR}))
        _, missing = run_day(self.root, evidence(T2, bars={"ALFA": None}))
        _, later = run_day(self.root, evidence(T3, bars={"ALFA": ("80", "84", "70", "73")}))
        last = self.by_symbol(later)["ALFA"]
        self.assertEqual(last["position"], self.by_symbol(first)["ALFA"]["position"])
        self.assertEqual(last["status"], Status.OPEN)
        self.assertEqual(last["suspended_at"], str(T2))
        self.assertEqual(self.by_symbol(missing)["ALFA"]["history"][-1]["observation"], Status.UNAVAILABLE)
        self.assertEqual(last["history"][-1]["reason"], "UNRESOLVED_PRIOR_GAP")

    def test_idempotence_state_conflict_and_missing_day_fail_closed(self):
        first, second, third, _ = demo_days()
        first_path, view = run_day(self.root, first, initialize=True)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: run_day(self.root, second), range(2)))
        output, t1 = results[0]
        self.assertEqual(t1, results[1][1])
        original = (output / "day.json").read_bytes()
        (output / "paper-report.html").unlink()
        self.assertEqual(run_study(self.root, Mode.SYNTHETIC, START, T1, POLICY)[1], t1)
        changed = deepcopy(second)
        changed["source"]["report_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "identity already used"):
            run_day(self.root, changed)
        self.assertEqual((output / "day.json").read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "PAPER_EXPECTED_PREDECESSOR_MISMATCH"):
            run_day(self.root, second, expect_previous="0" * 64)
        with self.assertRaisesRegex(ValueError, "PAPER_PROSPECTIVE_DISABLED"):
            run_study(self.root, Mode.PROSPECTIVE, START, T1, POLICY)
        with self.assertRaises(OSError):
            run_study(self.root, Mode.HISTORICAL_REPLAY, START, T1, POLICY)
        (first_path / "day.json").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "PAPER_LEDGER_DAY_MISSING"):
            run_day(self.root, third)
        self.assertEqual(run_day(self.root, first, initialize=True)[1], view)
        (output / "day.json").write_bytes(original.replace(b"synthetic-2026", b"corrupted-2026"))
        with self.assertRaisesRegex(ValueError, "PAPER_LEDGER_INTEGRITY_CONFLICT"):
            run_day(self.root, third)

    def test_evidence_only_no_t1_fill_and_no_cross_mode_restore(self):
        _, view = run_day(self.root, evidence(START, (candidate("ALFA"),)), initialize=True, policy={})
        _, t1 = run_day(self.root, evidence(T1, bars={"ALFA": SIGNAL_BAR}), policy={})
        plan = self.by_symbol(view)["ALFA"]["plan"]
        row = self.by_symbol(t1)["ALFA"]
        self.assertEqual(plan["simulation_eligibility"], "POLICY_UNSET")
        self.assertEqual((row["status"], row["history"][-1]["actual_rr"]), (Status.UNAVAILABLE, "4"))
        self.assertEqual(next_session(date(2025, 11, 26)), date(2025, 11, 28))
        with self.assertRaisesRegex(ValueError, "PAPER_UNKNOWN_POLICY_COHORT"):
            check_policy({B_VERSION: {"C_PRICE_RESEARCH:CLEAR": RULE}})

    def test_new_policy_rejects_retired_c_rule(self):
        position_rule = position_policy()[B_VERSION]["B_NUMERIC_QUALIFIED:UNKNOWN"]
        for protocol, rule in ((PROTOCOL, RULE), (POSITION_PROTOCOL, position_rule)):
            with self.subTest(protocol=protocol):
                check_policy({BALANCED: {"C_PRICE_RESEARCH:CLEAR": rule}}, protocol)
                with self.assertRaisesRegex(ValueError, "PAPER_UNKNOWN_POLICY_STRATEGY"):
                    check_policy({CONSERVATIVE: {"C_PRICE_RESEARCH:CLEAR": rule}}, protocol)

    def test_ledger_advances_from_three_rule_archive_to_two_rule_archive(self):
        def from_archive(day, versions, matched=None):
            run, records = screening_archive(day, versions)
            if matched:
                run["strategies"][matched]["matches"] = 1
                records[matched]["evaluations"][0]["matched"] = True
                archived = candidate("ALFA", matched, warning="CLEAR")
                records["record-research"]["candidates"].append({
                    **archived, "trade": {"qualification": archived["qualification"], "plan": archived["levels"],
                                          "qualification_reason": None, "missing_reason": None,
                                          "inputs": [("stop_risk_warning", False)]},
                    "volume": {"measures": archived["volume"]},
                })
            scripts = []
            for key, value in records.items():
                attribute = "id" if key == "record-research" else "data-strategy"
                scripts.append(f'<script type="application/json" {attribute}="{key}">{json.dumps(value)}</script>')
            body = "".join(scripts).encode()
            plans, grid = _screening(run, read_report_records(body, sha256(body).hexdigest()), ("ALFA",))
            data = evidence(day, plans, bars={"ALFA": SIGNAL_BAR})
            data["quotes"]["ALFA"]["structures"] = {version: rows["ALFA"] for version, rows in grid.items()}
            return data

        first = from_archive(START, (*STRATEGIES, CONSERVATIVE), CONSERVATIVE)
        second = from_archive(T1, STRATEGIES, BALANCED)
        self.assertEqual(set(first["quotes"]["ALFA"]["structures"]), {*STRATEGIES, CONSERVATIVE})
        self.assertEqual(second["quotes"]["ALFA"]["structures"].keys(), STRATEGIES.keys())
        _, initial = run_day(self.root, first, initialize=True, policy={})
        output, advanced = run_day(self.root, second, policy={}, expect_previous=initial["ledger_sha256"])
        _, restored = run_study(self.root, Mode.SYNTHETIC, START, T1, {})
        self.assertEqual(restored, advanced)
        self.assertEqual({row["plan"]["strategy_version"]: row["status"] for row in advanced["records"].values()},
                         {CONSERVATIVE: Status.UNAVAILABLE, BALANCED: Status.PENDING})
        retired_stat = next(row for row in advanced["performance"] if row["group"] == CONSERVATIVE)
        self.assertEqual(retired_stat[Status.UNAVAILABLE], 1)
        self.assertIn("<th scope='row'>C 保守</th>", (output / "paper-report.html").read_text(encoding="utf-8"))

    def test_restore_reuses_byte_identical_legacy_view_with_empty_retired_row(self):
        output, view = run_day(self.root, evidence(START), initialize=True, policy={})
        legacy = {**view, "performance": summarize(view["records"], include_empty_retired=True)}
        old_bytes = render_paper(legacy, company_labels=False).encode("utf-8")
        path = output / "paper-report.html"
        self.assertNotIn("C 保守", path.read_text(encoding="utf-8"))
        path.write_bytes(old_bytes)
        self.assertEqual(run_study(self.root, Mode.SYNTHETIC, START, START, {})[1], view)
        self.assertEqual(path.read_bytes(), old_bytes)

    def test_archive_hash_and_duplicate_records_are_rejected(self):
        html = f'<script type="application/json" data-strategy="{B_VERSION}">{{}}</script>'.encode()
        with self.assertRaisesRegex(ValueError, "PAPER_REPORT_SHA_MISMATCH"):
            read_report_records(html, "0" * 64)
        with self.assertRaisesRegex(ValueError, "PAPER_DUPLICATE_REPORT_RECORD"):
            read_report_records(html * 2, sha256(html * 2).hexdigest())
        with patch("us_watchlist.app.paper_inputs.verify_completed", side_effect=ValueError("archive conflict")):
            with self.assertRaisesRegex(ValueError, "archive conflict"):
                load_day(self.root, START, set())
        self.assertFalse(list(self.root.iterdir()))

    def test_screening_and_reference_records_must_agree(self):
        run, records = screening_archive(START, STRATEGIES)
        self.assertEqual(_screening(run, records, ("ALFA",))[0], [])
        records[B_VERSION]["evaluations"][0]["matched"] = True
        with self.assertRaisesRegex(ValueError, "PAPER_SCREENING_COUNT_MISMATCH"):
            _screening(run, records, ("ALFA",))
        run["strategies"][B_VERSION]["matches"] = 1
        with self.assertRaisesRegex(ValueError, "PAPER_RESEARCH_MATCH_SET_MISMATCH"):
            _screening(run, records, ("ALFA",))

    def test_screening_rejects_missing_active_unknown_and_disagreeing_strategy_sets(self):
        for receipt_versions, embedded_versions in (
            ((B_VERSION,), (B_VERSION,)),
            ((*STRATEGIES, "unknown"), (*STRATEGIES, "unknown")),
            ((*STRATEGIES, CONSERVATIVE), tuple(STRATEGIES)),
            (tuple(STRATEGIES), (*STRATEGIES, CONSERVATIVE)),
        ):
            with self.subTest(receipt=receipt_versions, embedded=embedded_versions):
                run, _ = screening_archive(START, receipt_versions)
                _, records = screening_archive(START, embedded_versions)
                with self.assertRaisesRegex(ValueError, "PAPER_SCREENING_STRATEGY_SET_MISMATCH"):
                    _screening(run, records, ("ALFA",))
