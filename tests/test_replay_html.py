import json
import re
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from us_watchlist.app.bc_offline import evaluate_joint
from us_watchlist.app.replay import prepare_replay
from us_watchlist.domain.screening import IwbReportEvidence
from us_watchlist.reporting.replay_html import render_joint_replay
from test_bc_offline import embedded_records


CONFIG = Path(__file__).resolve().parents[1] / "configs" / "b_demo" / "replay.toml"


class ChineseReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        evidence, inputs = prepare_replay(CONFIG)
        cls.evidence = replace(evidence, mode="iwb_yahoo_observation", iwb=IwbReportEvidence(
            (("HOLX", "IWB_UNLISTED_OR_NO_MARKET"),), 6, 10, 4, "PARTIAL_COVERAGE",
        ))
        b, c = evaluate_joint(inputs)
        matched = next(row for row in b.evaluations if row.signal is not None)
        cls.decimal = Decimal("99.123456789123456789")
        cls.ratio = 2.123456789123
        detailed = replace(
            matched,
            structure=(("Platform", cls.decimal), ("Close / platform", Decimal("1.023456789")),
                       ("Near platform", True), ("Turn strength", False)),
            volume=(("Breakout volume / prior 20d mean", cls.ratio),
                    ("Retest mean volume / breakout", "Zero breakout volume")),
        )
        c_zero = replace(c[1], evaluations=tuple(
            replace(row, reason="REBOUND_NOT_CONFIRMED", signal=None) if row.signal else row
            for row in c[1].evaluations
        ))
        cls.b = replace(b, evaluations=tuple(detailed if row is matched else row for row in b.evaluations))
        cls.c = (c[0], c_zero)
        cls.html = render_joint_replay(cls.evidence, cls.b, cls.c)
        cls.main, cls.audit = cls.html.split('<details id="audit" class="panel fold">', 1)

    def test_chinese_labels_and_precision_keep_symbols_and_versions(self):
        for label in (
            'lang="zh-CN"', "美股收盘日报", "当日行情覆盖", "部分覆盖", "历史点时与拆股量能未验证",
            "研究效果未验证", "今日候选", "暂无经过审查的优选规则", "C · 均衡规则", "C · 保守规则",
            '0 只</strong><small>研究规则匹配', "本轮没有匹配的股票",
            "DEMOA", self.b.strategy.version, "$99.12", "102.35%", "2.12 倍",
            "回踩位置达标</dt><dd>是", "收盘转强条件达标</dt><dd>否", "突破日成交量为零",
            "缺少 1 个交易日的行情", "未匹配原因汇总", "搜索",
        ):
            with self.subTest(label=label):
                self.assertIn(label, self.main)
        for raw in (str(self.decimal), str(self.ratio), "INCOMPLETE_HISTORY", "PARTIAL_COVERAGE", "Platform",
                    "True", "Target-session OHLCV", "HOLX"):
            self.assertNotIn(raw, self.main)
        self.assertIn("HOLX（无有效上市市场）", self.audit)

    def test_folded_audit_keeps_every_original_field_and_is_deterministic(self):
        self.assertEqual(self.html, render_joint_replay(self.evidence, self.b, self.c))
        self.assertNotIn(self.evidence.input_sha256, self.main)
        self.assertIn(self.evidence.input_sha256, self.audit)
        self.assertIn('<details class="fold other-results">', self.main)
        self.assertNotRegex(self.html, r"<details[^>]*\bopen\b")
        records = embedded_records(self.audit)
        self.assertEqual(set(records), {rule.strategy.version for rule in (self.b, *self.c)})
        for rule in (self.b, *self.c):
            data = records[rule.strategy.version]
            self.assertEqual(data["schema"], "us_offline_screening_v1")
            self.assertEqual(data["status"], "PARTIAL_COVERAGE")
            self.assertEqual(data["strategy"], rule.strategy.name)
            self.assertEqual(data["manifest_sha256"], self.evidence.input_sha256)
            raw_rows = [{
                "symbol": row.symbol, "reason": row.reason, "matched": row.signal is not None,
                "sessions_available": row.sessions_available, "data_gap": row.data_gap,
                "structure": dict(row.structure), "volume": dict(row.volume),
            } for row in rule.evaluations]
            self.assertEqual(data["evaluations"], json.loads(json.dumps(raw_rows, default=str)))
        raw_input = re.search(r'id="record-input">(.*?)</script>', self.audit)
        inputs = json.loads(raw_input[1])
        self.assertEqual(inputs["history"]["snapshot_id"], self.evidence.history.snapshot_id)
        self.assertEqual(inputs["iwb"]["inactive"], [["HOLX", "IWB_UNLISTED_OR_NO_MARKET"]])
        self.assertEqual(inputs["input_sha256"], self.evidence.input_sha256)

    def test_mobile_layout_and_search_are_self_contained(self):
        self.assertIn('content="width=device-width, initial-scale=1"', self.html)
        self.assertIn('-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC"', self.html)
        self.assertIn("font-variant-numeric: tabular-nums", self.html)
        self.assertIn("position: sticky", self.html)
        self.assertIn("@media (max-width: 760px)", self.html)
        self.assertRegex(self.html, r"\.watch-columns, \.audit-grid \{ grid-template-columns: minmax\(0, 1fr\)")
        self.assertIn('type="search" placeholder="输入股票代码或原因"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('data-search="democ 所需历史行情不足', self.html)
        self.assertNotRegex(self.html, r"<(?:script|link|iframe|img)\b[^>]*\b(?:src|href)=")
        ids = re.findall(r'\bid="([^"]+)"', self.html)
        anchors = re.findall(r'href="#([^"]+)"', self.html)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(anchors).issubset(ids))
