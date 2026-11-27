import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from us_watchlist.app.bc_offline import evaluate_joint, observe_joint
from us_watchlist.app.replay import prepare_replay
from us_watchlist.domain.models import SessionBar
from us_watchlist.domain.replay_research import REFERENCE_V2
from us_watchlist.research.reference_plan import b_reference_plan, b_us_reference_plan
from us_watchlist.strategies.b_breakout_retest import US_B_V2, BreakoutRetestShape

CONFIG = Path(__file__).resolve().parents[1] / "configs" / "b_demo" / "replay.toml"


def bar(value, *, wick="0.4", volume=100):
    close, spread = Decimal(value), Decimal(wick)
    return SessionBar("DEMOA", close, close + spread, close - spread, close, volume)


class BreakoutV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence, cls.inputs = prepare_replay(CONFIG)

    def _evaluate(self, bars):
        self.assertEqual(len(bars), 76)
        history = tuple(replace(snapshot, bars=(value,)) for snapshot, value in zip(self.inputs.history[-76:], bars))
        inputs = replace(self.inputs, eligible_symbols=("DEMOA",), history=history)
        return BreakoutRetestShape(US_B_V2).evaluate(inputs)[0]

    def test_demo_keeps_four_distinct_diagnostics_and_uses_v2_research(self):
        b, c = evaluate_joint(self.inputs)
        self.assertEqual({row.symbol: row.reason for row in b.evaluations}, {
            "DEMOA": "SHAPE_MATCH", "DEMOB": "NO_QUALIFYING_BREAKOUT", "DEMOC": "INCOMPLETE_HISTORY",
            "DEMOD": "FIRST_BREAKOUT_RETEST_FAILED",
        })
        self.assertEqual(observe_joint(self.evidence, self.inputs, b, c).version, REFERENCE_V2)

    def test_atr_threshold_floor_interior_and_cap(self):
        for wick, breakout, reason, threshold in (
            ("0.4", "102", "SHAPE_MATCH", "0.02"),
            ("2", "103", "SHAPE_MATCH", "0.03"),
            ("3", "103", "NO_QUALIFYING_BREAKOUT", None),
            ("3", "104.1", "SHAPE_MATCH", "0.04"),
        ):
            with self.subTest(wick=wick, breakout=breakout):
                bars = [bar(100, wick=wick)] * 72 + [bar(breakout, volume=150), bar(100), bar(101), bar(102)]
                row = self._evaluate(bars)
                self.assertEqual(row.reason, reason)
                if threshold is not None:
                    self.assertEqual(dict(row.structure)["Breakout min change"], Decimal(threshold))

    def test_retest_volume_cap_is_strict_and_first_breakout_remains_the_anchor(self):
        before = [bar(100)] * 72
        row = self._evaluate(before + [bar(102, volume=200)] + [bar(101, volume=150)] * 3)
        self.assertEqual(row.reason, "FIRST_BREAKOUT_RETEST_FAILED")
        self.assertFalse(dict(row.volume)["Retest contracted"])
        recovery = self._evaluate(before + [bar(102, volume=150), bar(105, volume=200), bar(101), bar(101)])
        self.assertEqual(recovery.reason, "FIRST_BREAKOUT_RETEST_FAILED")
        self.assertEqual(dict(recovery.structure)["Breakout date"],
                         self.inputs.history[-4].session.trading_date.isoformat())

    def test_ma50_requires_both_close_above_and_sufficient_slope(self):
        losing_ma50 = self._evaluate([bar(100)] * 72 + [bar(102, volume=150)] + [bar(99)] * 3)
        falling_ma50 = self._evaluate(
            [bar(93)] * 21 + [bar(103)] * 5 + [bar(93)] * 35 + [bar(105, volume=150)]
            + [bar("94.6")] * 13 + [bar(100)]
        )
        for row in (losing_ma50, falling_ma50):
            structure = dict(row.structure)
            self.assertEqual(row.reason, "FIRST_BREAKOUT_RETEST_FAILED")
            self.assertFalse(structure["Trend MA50"])
            self.assertTrue(structure["Near platform"] and structure["Controlled pullback"] and structure["Turn strength"])

    def test_peak_guard_uses_closes_and_all_post_breakout_sessions(self):
        before = [bar(100)] * 71 + [bar(102, volume=150)]
        for low, controlled in (("99", True), ("98.99", False)):
            with self.subTest(low=low):
                row = self._evaluate(before + [bar(110, wick="5"), bar(low), bar(101), bar(102)])
                self.assertIs(dict(row.structure)["Controlled pullback"], controlled)
                self.assertEqual(row.reason, "SHAPE_MATCH" if controlled else "FIRST_BREAKOUT_RETEST_FAILED")

    def test_first_turn_resets_after_weakness_and_includes_day_after_breakout(self):
        before = [bar(100)] * 72 + [bar(102, volume=150)]
        for bars, fresh in (
            (before + [bar(103), bar(100), bar(101)], True),
            (before + [bar(100), bar(101), bar(102)], False),
            ([bar(100)] * 74 + [bar(102, volume=150), bar(102)], True),
        ):
            row = self._evaluate(bars)
            self.assertEqual(row.reason, "SHAPE_MATCH")
            self.assertIs(dict(row.structure)["Fresh turn"], fresh)


class UsReferencePlanTests(unittest.TestCase):
    @staticmethod
    def _bars(*, prior_high="98.4", post_high="104"):
        before = [bar(98)] * 112
        before[55] = replace(before[55], low=Decimal(75), high=Decimal(prior_high))
        breakout = replace(bar(102, volume=180), high=Decimal(post_high))
        return tuple(before + [breakout] + [bar(99)] * 6 + [bar(100)])

    @staticmethod
    def _below_platform_bars(*, platform=100, prior_high="95.4"):
        before = [bar(95)] * 108 + [bar(platform)]
        before[60] = replace(before[60], high=Decimal(prior_high))
        breakout = bar(platform + 2, volume=180)
        first_retest = bar("97.40", wick="0.46", volume=120)
        return tuple(before + [breakout, first_retest] + [bar("97.40")] * 8 + [bar("97.50")])

    def test_current_breakout_high_is_not_historical_pressure(self):
        bars = self._bars()
        old = b_reference_plan(bars, Decimal(98))
        new = b_us_reference_plan(bars, Decimal(98), 112)
        self.assertEqual(old.qualification_reason, "B_RR_BELOW_TWO_AT_CLOSE")
        self.assertEqual(old.plan.target, Decimal("104"))
        self.assertEqual(new.qualification, "B_NUMERIC_QUALIFIED")
        self.assertEqual(new.plan.target_rule, "B_TREND_2_5R")
        self.assertEqual(dict(new.inputs)["rr_to_unrounded_close"], Decimal("2.5"))
        self.assertEqual(new.plan.rr.quantize(Decimal("0.01")), Decimal("2.50"))
        self.assertEqual(dict(new.inputs)["post_breakout_high"], Decimal(104))

    def test_unbroken_old_high_can_still_reject_at_entry(self):
        bars = self._bars(prior_high="104.5", post_high="103.9")
        obs = b_us_reference_plan(bars, Decimal(98), 112)
        self.assertEqual(obs.qualification_reason, "B_RR_BELOW_TWO_AT_ENTRY")
        self.assertEqual(obs.plan.target_rule, "B_PRESSURE")
        self.assertEqual(obs.plan.target, Decimal("104.5"))
        crossed = b_us_reference_plan(self._bars(prior_high="104.5"), Decimal(98), 112)
        self.assertEqual(crossed.plan.target_rule, "B_TREND_2_5R")

    def test_below_platform_trend_target_and_gate_use_entry(self):
        obs = b_us_reference_plan(self._below_platform_bars(), Decimal(100), 109)
        self.assertEqual(obs.qualification, "B_NUMERIC_QUALIFIED")
        plan = obs.plan
        self.assertEqual(plan.target_rule, "B_TREND_2_5R")
        self.assertEqual((plan.trigger, plan.entry, plan.stop, plan.target, plan.rr),
                         tuple(map(Decimal, ("100.00", "100.00", "95.00", "112.50", "2.50"))))
        inputs = dict(obs.inputs)
        self.assertEqual(inputs["reference_entry"], plan.entry)
        self.assertEqual(inputs["risk_to_close"], Decimal("2.50") / Decimal("97.50"))
        self.assertEqual(inputs["risk_to_entry"], Decimal("0.05"))
        self.assertEqual(inputs["plan_rr"], Decimal("2.50"))
        self.assertEqual(inputs["rr_to_unrounded_close"], Decimal("6"))

    def test_below_platform_pressure_fails_entry_gate_and_retains_plan(self):
        bars = self._below_platform_bars(prior_high="104.00")
        obs = b_us_reference_plan(bars, Decimal(100), 109)
        self.assertEqual((obs.qualification, obs.qualification_reason),
                         ("B_NUMERIC_REJECTED", "B_RR_BELOW_TWO_AT_ENTRY"))
        plan = obs.plan
        self.assertEqual(plan.target_rule, "B_PRESSURE")
        self.assertEqual((plan.entry, plan.stop, plan.target, plan.rr),
                         tuple(map(Decimal, ("100.00", "95.00", "104.00", "0.80"))))
        inputs = dict(obs.inputs)
        self.assertEqual(inputs["rr_to_unrounded_close"], Decimal("2.60"))
        self.assertEqual(inputs["plan_rr"], Decimal("0.80"))

    def test_below_platform_entry_risk_can_exceed_limit_when_close_risk_passes(self):
        bars = self._below_platform_bars(platform=104)
        obs = b_us_reference_plan(bars, Decimal(104), 109)
        self.assertEqual((obs.qualification, obs.qualification_reason),
                         ("B_NUMERIC_REJECTED", "B_STOP_DISTANCE_OUTSIDE_RANGE"))
        self.assertIsNone(obs.plan)
        inputs = dict(obs.inputs)
        self.assertEqual(inputs["reference_entry"], Decimal("104.00"))
        self.assertTrue(0 < inputs["risk_to_close"] <= Decimal("0.08") < inputs["risk_to_entry"])

    def test_requires_history_and_valid_breakout_index_and_rejects_five_dollars(self):
        bars = self._bars()
        for sample, platform, index, reason in (
            (bars[1:], Decimal(98), 111, "B_HISTORY_LT_120"),
            (bars, None, 112, "B_PLATFORM_UNAVAILABLE"),
            (bars, Decimal(98), None, "B_BREAKOUT_UNAVAILABLE"),
            (bars, Decimal(98), 59, "B_BREAKOUT_UNAVAILABLE"),
            (bars, Decimal(98), 119, "B_BREAKOUT_UNAVAILABLE"),
        ):
            obs = b_us_reference_plan(sample, platform, index)
            self.assertEqual((obs.qualification, obs.qualification_reason), ("B_NUMERIC_UNAVAILABLE", reason))
        low = b_us_reference_plan(tuple([bar("4.9")] * 119 + [bar(5)]), Decimal("4.9"), 112)
        self.assertEqual(low.qualification_reason, "B_CLOSE_NOT_ABOVE_US_5")
        self.assertIsNone(low.plan)
