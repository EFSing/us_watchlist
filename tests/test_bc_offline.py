import json
import re
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from us_watchlist.app.bc_offline import evaluate_joint, run_bc_offline
from us_watchlist.app.replay import prepare_replay
from us_watchlist.domain.paper import RETIRED_STRATEGIES
from us_watchlist.reporting.replay_html import render_joint_replay
from us_watchlist.strategies.b_breakout_retest import BreakoutRetestShape
from us_watchlist.strategies.c_trend_pullback import BALANCED_A, TrendPullback

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "b_demo" / "replay.toml"


def embedded_records(html: str) -> dict:
    return {name: json.loads(raw) for name, raw in re.findall(
        r'<script type="application/json" data-strategy="([^"]+)">(.*?)</script>', html,
    )}


class JointOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence, cls.inputs = prepare_replay(CONFIG)
        cls.temp = ROOT / ".runtime" / "tmp"
        cls.temp.mkdir(parents=True, exist_ok=True)

    def test_each_rule_evaluates_the_shared_universe_and_records_its_own_candidate(self):
        with TemporaryDirectory(dir=self.temp) as directory:
            artifacts = Path(directory)
            path = run_bc_offline(CONFIG, artifacts)
            self.assertEqual(run_bc_offline(CONFIG, artifacts), path)
            html = path.read_text(encoding="utf-8")
            results = embedded_records(html)
            expected = {
                BreakoutRetestShape.version.version: "DEMOA",
                TrendPullback(BALANCED_A).version.version: "DEMOB",
            }
            b, c = evaluate_joint(self.inputs)
            self.assertEqual([result.strategy.version for result in (b, *c)], list(expected))
            self.assertEqual(results.keys(), expected.keys())
            for version, expected_signal in expected.items():
                with self.subTest(version=version):
                    self.assertIn(f'href="#{version}"', html)
                    rows = results[version]["evaluations"]
                    self.assertEqual([row["symbol"] for row in rows], ["DEMOA", "DEMOB", "DEMOC", "DEMOD"])
                    self.assertEqual([row["symbol"] for row in rows if row["matched"]], [expected_signal])
                    self.assertIn("missing session", rows[2]["data_gap"])
            self.assertIn("C 均衡规则匹配 1 只。", html)
            self.assertIn("<summary>C · 均衡规则 · 1 只匹配</summary>", html)
            self.assertNotIn("C · 保守规则", html)

    def test_historical_result_keeps_its_rule_label_and_deduplicated_count(self):
        b, (balanced,) = evaluate_joint(self.inputs)
        retired = replace(balanced, strategy=replace(balanced.strategy, version=next(iter(RETIRED_STRATEGIES))))
        html = render_joint_replay(self.evidence, b, (balanced, retired))
        self.assertIn("C · 保守规则", html)
        self.assertIn("C 2 套规则合计 1 只（按代码去重）。", html)

    def test_failed_strategy_remains_visible_and_other_strategy_still_reports_matches(self):
        for failing, valid in ((BreakoutRetestShape, TrendPullback(BALANCED_A)),
                               (TrendPullback, BreakoutRetestShape())):
            with self.subTest(failing=failing), TemporaryDirectory(dir=self.temp) as directory:
                with patch.object(failing, "evaluate", side_effect=RuntimeError("injected </script> fault")):
                    path = run_bc_offline(CONFIG, Path(directory))
                html = path.read_text(encoding="utf-8")
                results = embedded_records(html)
                errors = [item for item in results.values() if item["status"] == "FAILED"]
                self.assertTrue(errors)
                self.assertEqual(errors[0]["error"], "RuntimeError: injected </script> fault")
                main, audit = html.split('<details id="audit"', 1)
                self.assertIn("该规则执行失败", main)
                self.assertNotIn("injected", main)
                self.assertIn("injected &lt;/script&gt; fault", audit)
                self.assertTrue(any(row["matched"] for row in results[valid.version.version]["evaluations"]))

    def test_c_support_uses_pret_pivots_and_volume_never_gates_structure(self):
        inputs = replace(self.inputs, eligible_symbols=("DEMOB",))
        first = TrendPullback(BALANCED_A).evaluate(inputs)[0]
        latest = inputs.history[-1]
        bar = next(item for item in latest.bars if item.symbol == "DEMOB")
        wicks = replace(latest, bars=(replace(bar, low=Decimal("122"), volume=0),))
        after = replace(inputs, history=(*inputs.history[:-1], wicks))
        recovered = TrendPullback(BALANCED_A).evaluate(after)[0]
        self.assertIsNotNone(first.signal)
        self.assertIsNotNone(recovered.signal)
        self.assertEqual(dict(recovered.structure)["Support floor"], dict(first.structure)["Support floor"])
        self.assertEqual(dict(recovered.structure)["Peak date"], dict(first.structure)["Peak date"])
        self.assertEqual(dict(recovered.structure)["Support status"], "T_INTRADAY_PUNCTURE_RECOVERED")
        self.assertAlmostEqual(dict(first.volume)["RV_T"], 1.368421052631579)
        self.assertAlmostEqual(dict(first.volume)["Pullback / baseline median volume"], 0.775)
        self.assertEqual(dict(recovered.volume)["RV_T"], 0)
        broken = replace(latest, bars=(
            replace(bar, open=Decimal("123"), close=Decimal("122"), low=Decimal("121")),
        ))
        failed = TrendPullback(BALANCED_A).evaluate(replace(inputs, history=(*inputs.history[:-1], broken)))[0]
        self.assertIsNone(failed.signal)
        self.assertEqual(dict(failed.structure)["Support status"], "T_CLOSE_BREAK")

    def test_short_and_long_c_rules_keep_distinct_history_eligibility(self):
        inputs = replace(self.inputs, eligible_symbols=("DEMOB",), history=self.inputs.history[-76:])
        self.assertIsNotNone(TrendPullback(BALANCED_A).evaluate(inputs)[0].signal)
        long_window = replace(BALANCED_A, name="TEST_LONG_WINDOW", trend_window=90)
        row = TrendPullback(long_window).evaluate(inputs)[0]
        self.assertEqual(row.reason, "INCOMPLETE_HISTORY")
        self.assertEqual(row.sessions_available, 76)
        self.assertIn("Only 76 of 90", row.data_gap)
