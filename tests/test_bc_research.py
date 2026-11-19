import json
import re
import unittest
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from us_watchlist.app.bc_offline import evaluate_joint, observe_joint
from us_watchlist.app.replay import prepare_replay
from us_watchlist.domain.models import SessionBar
from us_watchlist.domain.replay_research import TRANSITION, UNCONFIRMED, CandidateResearch, PlanObservation
from us_watchlist.reporting.replay_html import render_joint_replay
from us_watchlist.research.pullback import b_structure, compare_b_volume, pullback_volume
from us_watchlist.research.reference_plan import b_reference_plan, c_reference_plan
from us_watchlist.research.replay_observations import observe_candidate

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "b_demo" / "replay.toml"


def dates(n):
    return tuple(date(2026, 1, 5) + timedelta(days=i) for i in range(n))


def bar(close, volume=100, *, low=None, high=None):
    price = Decimal(str(close))
    return SessionBar("DEMOA", price, Decimal(str(high)) if high is not None else price,
                      Decimal(str(low)) if low is not None else price, price, volume)


class PullbackResearchTests(unittest.TestCase):
    def test_b_structure_uses_first_equal_high_and_exact_recovery_boundaries(self):
        prefix = (bar(90, low=80),) * 60 + (bar(108, high=110), bar(104, high=110), bar(100, low=98))
        days = dates(len(prefix) + 1)
        for close, state, ratio in (
            (103, "EARLY_PULLBACK", Decimal(5) / 12),
            (104, TRANSITION, Decimal("0.5")),
            (110, TRANSITION, Decimal(1)),
            (111, "POST_H1_CONTINUATION_PROXY", Decimal(13) / 12),
        ):
            with self.subTest(close=close):
                result = b_structure((*prefix, bar(close, high=160)), days, 60)
                self.assertEqual(result.stage, state)
                self.assertEqual(result.recovery_ratio, ratio)
                self.assertEqual(result.points, (
                    ("L0", days[0], Decimal(80)), ("H1", days[60], Decimal(110)), ("L2", days[62], Decimal(98)),
                ))
        late_high = (*prefix[:-1], bar(100, high=115), bar(105))
        self.assertEqual(b_structure(late_high, days, 60).reason, "NO_COMPLETE_POST_H1_PULLBACK_DAY")
        invalid = b_structure((*prefix[:-1], bar(85, low=79), bar(105)), days, 60)
        self.assertEqual(invalid.stage, UNCONFIRMED)
        self.assertEqual(invalid.reason, "INVALID_L0_L2_H1_ORDER_OR_DENOMINATOR")
        self.assertIsNone(invalid.recovery_ratio)

    def test_frozen_volume_denominators_and_odd_window_exclude_both_endpoints(self):
        bars = tuple(bar(close, volume) for close, volume in zip(
            (100, 99, 100, 100, 98, 99, 90), (999, 20, 60, 30, 40, 10, 1_000_000),
        ))
        days = dates(len(bars))
        result = pullback_volume(bars, days, 0)
        self.assertEqual((result.anchor_day, result.window_start, result.window_end), (days[0], days[1], days[-2]))
        self.assertEqual((result.window_days, result.up_days, result.down_days, result.flat_days), (5, 2, 2, 1))
        self.assertEqual(tuple(item.value for item in result.measures), (
            Decimal("0.375"), Decimal(7) / 6, Decimal(2) / 3,
        ))
        changed_t = (*bars[:-1], bar(210, 0))
        self.assertEqual(result, pullback_volume(changed_t, days, 0))

    def test_missing_volume_is_distinct_from_a_valid_zero(self):
        days = dates(6)
        bars = (bar(100), bar(101, 0), bar(100, 0), bar(101, 200), bar(102, 200), bar(103))
        result = pullback_volume(bars, days, 0)
        self.assertEqual(result.measures[0].value, 0)
        self.assertEqual(result.measures[1].missing_reason, "INVALID_UP_OR_DOWN_VOLUME")
        self.assertEqual(result.measures[2].missing_reason, "INVALID_PULLBACK_HALF_VOLUME")
        no_days = pullback_volume(bars, days, 4)
        self.assertEqual(no_days.window_days, 0)
        self.assertEqual({item.missing_reason for item in no_days.measures}, {"NO_PULLBACK_WINDOW"})
        one_day = pullback_volume(bars, days, 3)
        self.assertEqual(one_day.measures[1].missing_reason, "NO_UP_OR_DOWN_DAY")
        self.assertEqual(one_day.measures[2].missing_reason, "PULLBACK_WINDOW_LT_4")
        zero_window = pullback_volume(tuple(replace(row, volume=0) for row in bars), days, 0)
        self.assertEqual(zero_window.measures[0].missing_reason, "INVALID_PULLBACK_VOLUME_SUM")

    def test_three_valid_same_stage_numeric_qualifiers_required_per_measure(self):
        days = dates(64)
        bars = (bar(80),) * 60 + (bar(101, high=110), bar(99), bar(100), bar(106))
        volume = pullback_volume(bars, days, 60)
        template = CandidateResearch(
            "B", "DEMOA", 120, "", b_structure(bars, days, 60), volume, PlanObservation("B_NUMERIC_QUALIFIED"),
        )

        def row(symbol, value, *, last=True):
            measures = tuple(
                replace(item, value=Decimal(value) if i < 2 or last else None)
                for i, item in enumerate(template.volume.measures)
            )
            return replace(template, symbol=symbol, volume=replace(volume, measures=measures))

        a, b, c = row("A", "0.2"), row("B", "0.2"), row("C", "0.8", last=False)
        rejected = replace(row("D", "0.1"), trade=PlanObservation("B_NUMERIC_REJECTED"))
        first, second, third, ignored = compare_b_volume((a, b, c, rejected))
        tied = first.volume.measures[0].coordinate
        self.assertEqual((tied.percentile, tied.bucket, tied.sample_size), (Decimal("0.5"), "MID", 3))
        self.assertEqual(second.volume.measures[0].coordinate, tied)
        self.assertEqual(third.volume.measures[0].coordinate.judgment, "DEVIATION")
        self.assertEqual(third.volume.measures[1].coordinate.judgment, "PREFERRED")
        self.assertEqual(first.volume.measures[2].coordinate.status, "INSUFFICIENT_CROSS_SECTION")
        self.assertEqual(third.volume.measures[2].coordinate.status, "FEATURE_UNAVAILABLE")
        self.assertEqual(ignored.volume.measures[0].coordinate.status, "B_NUMERIC_QUALIFICATION_NOT_MET")


class ReferencePlanTests(unittest.TestCase):
    base = (bar(100, low=96, high=102),) * 119 + (bar(101, low=100, high=102),)

    def assert_valid_rr(self, plan):
        self.assertLess(plan.stop, plan.entry)
        self.assertLess(plan.entry, plan.target)
        self.assertLess(plan.stop, plan.trigger)
        self.assertLess(plan.trigger, plan.target)
        self.assertEqual(plan.rr, (plan.target - plan.entry) / (plan.entry - plan.stop))

    def test_b_close_based_gate_and_rounded_display_rr_are_separate(self):
        observation = b_reference_plan(self.base, Decimal(100))
        self.assertEqual(observation.qualification, "B_NUMERIC_QUALIFIED")
        plan = observation.plan
        self.assertEqual((plan.trigger, plan.stop, plan.target, plan.entry), tuple(
            map(Decimal, ("100.20", "98.05", "108.38", "101.00")),
        ))
        self.assertEqual(plan.target_rule, "B_TREND_2_5R")
        self.assertEqual(dict(observation.inputs)["rr_to_unrounded_close"], Decimal("2.5"))
        self.assert_valid_rr(plan)

    def test_b_price_bins_pressure_and_overhang_keep_rejected_plan_as_reference(self):
        rows = list(self.base)
        rows[40] = bar("107.6", 100_000, low=105, high=108)
        observation = b_reference_plan(tuple(rows), Decimal(100))
        self.assertEqual(observation.qualification_reason, "B_OVERHANG_WITH_RR_BELOW_2_5")
        self.assertEqual(dict(observation.inputs)["strongest_above_threshold_bin"], Decimal("107.4"))
        self.assertEqual(observation.plan.target, Decimal("107.40"))
        self.assert_valid_rr(observation.plan)
        rows[40] = bar("104.2", 100_000, low=103, high=105)
        low_rr = b_reference_plan(tuple(rows), Decimal(100))
        self.assertEqual(low_rr.qualification_reason, "B_RR_BELOW_TWO_AT_CLOSE")
        self.assertEqual(low_rr.plan.target, Decimal("104.10"))
        self.assert_valid_rr(low_rr.plan)

    def test_b_short_history_and_stop_gate_do_not_make_levels(self):
        self.assertIsNone(b_reference_plan(self.base[1:], Decimal(100)).plan)
        low_history = (bar(85, low=80, high=86),) * 119 + (bar(100, low=99, high=101),)
        rejected = b_reference_plan(low_history, Decimal(85))
        self.assertEqual(rejected.missing_reason, "B_STOP_DISTANCE_OUTSIDE_RANGE")
        self.assertIsNone(rejected.plan)

    def test_c_uses_native_rebound_support_and_target_threshold(self):
        bars = (bar(106),) * 4 + (bar(111),)
        pressure = c_reference_plan(bars, Decimal(120), Decimal(100), Decimal(108)).plan
        trend = c_reference_plan(bars, Decimal("114.33"), Decimal(100), Decimal(108)).plan
        self.assertEqual(pressure.trigger, Decimal(108))
        self.assertEqual(pressure.stop, Decimal(98))
        self.assertEqual(pressure.target, Decimal(120))
        self.assertEqual(trend.target, Decimal("143.50"))
        self.assertEqual(pressure.entry, pressure.trigger)
        self.assert_valid_rr(pressure)
        self.assert_valid_rr(trend)
        bad = c_reference_plan(bars, Decimal(120), Decimal(110), Decimal(105))
        self.assertIsNone(bad.plan)
        self.assertEqual(bad.missing_reason, "REFERENCE_LEVEL_ORDER_INVALID")


class ResearchReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence, cls.inputs = prepare_replay(CONFIG)
        cls.b, cls.c = evaluate_joint(cls.inputs)

    def test_missing_split_sessions_cannot_be_bridged_by_a_plan_or_volume_window(self):
        row = next(row for row in self.b.evaluations if row.signal is not None)
        slot = row.signal.session.trading_date
        days = tuple(slot - timedelta(days=119-i) for i in range(120))
        anchored = replace(row, structure=(("Breakout date", days[-10].isoformat()), ("Platform", Decimal(100))))
        history = (bar(90, low=80),) * 110 + (bar(110, high=112),) + (bar(99),) * 8 + (bar(106),)
        split_diagnostic = f"YAHOO_SPLIT_BASIS_UNVERIFIED {days[18]}"
        for missing_index in (18, 113):
            series = (*history[:missing_index], None, *history[missing_index + 1:])
            observation = observe_candidate(anchored, days, series, is_b=True, source_gap=split_diagnostic)
            self.assertEqual(observation.continuous_sessions, 119 - missing_index)
            self.assertEqual(observation.source_gap, split_diagnostic)
            self.assertIsNone(observation.trade.plan)
            self.assertEqual(observation.trade.missing_reason, "B_HISTORY_LT_120")
            if missing_index < 110:
                self.assertIsNotNone(observation.volume.measures[0].value)
            else:
                self.assertEqual(observation.structure.stage, UNCONFIRMED)
                self.assertTrue(all(item.value is None for item in observation.volume.measures))

    def test_study_rejects_future_session_and_mismatched_signal_cutoff(self):
        next_day = timedelta(days=1)
        last = self.inputs.history[-1]
        future = replace(last, session=replace(last.session, trading_date=last.session.trading_date + next_day,
                                              opens_at=last.session.opens_at + next_day,
                                              closes_at=last.session.closes_at + next_day))
        with self.assertRaisesRegex(ValueError, "screening date and cutoff"):
            observe_joint(self.evidence, replace(self.inputs, history=(*self.inputs.history, future)), self.b, self.c)
        rows = tuple(replace(row, signal=replace(row.signal, known_at=row.signal.known_at + next_day))
                     if row.signal else row for row in self.b.evaluations)
        with self.assertRaisesRegex(ValueError, "completed screening session and cutoff"):
            observe_joint(self.evidence, self.inputs, replace(self.b, evaluations=rows), self.c)

    def test_new_records_are_separate_and_core_cards_are_outside_folds(self):
        research = observe_joint(self.evidence, self.inputs, self.b, self.c)
        legacy = render_joint_replay(self.evidence, self.b, self.c)
        html = render_joint_replay(self.evidence, self.b, self.c, research=research)
        self.assertEqual(html, render_joint_replay(self.evidence, self.b, self.c, research=research))
        pattern = r'<script type="application/json" data-strategy="([^"]+)">(.*?)</script>'
        self.assertEqual(re.findall(pattern, legacy), re.findall(pattern, html))
        cards = re.findall(r'<article class="watch-card".*?</article>', html, re.DOTALL)
        self.assertEqual(len(cards), len(research.candidates))
        for card in cards:
            visible, _ = card.split("<details>", 1)
            for label in ("结构阶段", "下跌日成交量占比", "上涨／下跌日均量比", "回踩后半／前半均量比",
                          "量能事实总结", "结构与量能综合判断", "参考计划（未验证）"):
                self.assertIn(label, visible)
        self.assertIn("grid-template-areas: \"label value\"", html)
        self.assertNotRegex(html, r'<(?:script|link)\b[^>]*\b(?:src|href)="')
        machine = json.loads(re.search(r'id="record-research">(.*?)</script>', html)[1])
        self.assertEqual(machine["manifest_sha256"], self.evidence.input_sha256)
        self.assertEqual(machine["research_effectiveness"], "UNVERIFIED")
        self.assertEqual(machine["formal_us_b_qualification"], "NOT_ESTABLISHED")
        self.assertEqual(len(machine["candidates"]), len(cards))
