import json
import unittest
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from us_watchlist.app.b_offline import run_b_offline
from us_watchlist.domain.models import PriceBasis, SessionKind
from us_watchlist.integrations.pipeline_iwb import read_pipeline_candidates
from us_watchlist.integrations.replay_input import read_replay
from us_watchlist.market_data.quality import regular_history
from us_watchlist.strategies.b_breakout_retest import BreakoutRetestShape
from us_watchlist.strategies.contracts import StrategyInput
from us_watchlist.universe.eligibility import eligible_symbols

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "configs" / "b_demo"
CONFIG = DEMO / "replay.toml"


class BReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.run_input = read_replay(CONFIG)
        cls.temp = ROOT / ".runtime" / "tmp"
        cls.temp.mkdir(parents=True, exist_ok=True)

    def test_offline_report_matches_expected_states_and_replays(self):
        with TemporaryDirectory(dir=self.temp) as directory:
            output = Path(directory)
            path = run_b_offline(CONFIG, output)
            html = path.read_text(encoding="utf-8")
            self.assertIn(">DEMOA</h3>", html)
            self.assertIn("突破回踩形态匹配</span>", html)
            for symbol, status, available in (
                ("DEMOB", "未找到符合条件的放量突破", 76),
                ("DEMOC", "所需历史行情不足", 75),
                ("DEMOD", "首次合格突破后的回踩未达条件", 76),
            ):
                with self.subTest(symbol=symbol):
                    self.assertRegex(html, rf'<th scope="row">{symbol}</th><td>{status}.*?</td><td>{available}</td>')
            self.assertNotIn("DEMOE-WI", html)
            self.assertNotIn("DEMOF", html)
            self.assertIn("<strong>1 只</strong><small>形态匹配", html)
            self.assertIn("常规交易时段", html)
            self.assertIn("合成样本", html)
            self.assertEqual(path, run_b_offline(CONFIG, output))
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_pipeline_receipt_publication_sets_cutoff_even_for_older_holdings(self):
        data = self.run_input
        seed = data.candidates.snapshot
        with self.assertRaisesRegex(ValueError, "Universe snapshot was unavailable"):
            eligible_symbols(
                seed, data.history[-1].session,
                seed.provenance.available_at - timedelta(seconds=1),
            )
        self.assertIn(
            "DEMOA",
            eligible_symbols(seed, data.history[-1].session, seed.provenance.available_at),
        )

    def test_stale_seed_and_modified_ohlcv_fail_before_publication(self):
        with TemporaryDirectory(dir=self.temp) as directory:
            root = Path(directory)
            fixture = copytree(DEMO, root / "demo")
            config = fixture / "replay.toml"
            original = config.read_bytes()
            config.write_bytes(original.replace(b"max_seed_age_days = 7", b"max_seed_age_days = 0"))
            with self.assertRaisesRegex(ValueError, "exceeds max_seed_age_days"):
                run_b_offline(config, root / "reports")
            config.write_bytes(original)
            ohlcv = fixture / "ohlcv.csv"
            ohlcv.write_bytes(ohlcv.read_bytes().replace(b",100\n", b",101\n", 1))
            with self.assertRaisesRegex(ValueError, "Calendar or OHLCV SHA-256"):
                run_b_offline(config, root / "reports")
            self.assertFalse((root / "reports").exists())

    def test_invalid_history_cannot_produce_candidate(self):
        d = self.run_input
        first = d.history[0]
        for label, history, cutoff, adjustments, error in (
            ("reordered", (d.history[1], first, *d.history[2:]), d.cutoff, d.adjustments_known_at,
             "ordered, unique"),
            ("duplicate", (first, first, *d.history[2:]), d.cutoff, d.adjustments_known_at,
             "ordered, unique"),
            ("premarket", (replace(first, session=replace(first.session, kind=SessionKind.PRE_MARKET)),
                           *d.history[1:]), d.cutoff, d.adjustments_known_at, "only regular"),
            ("mixed", (replace(first, price_basis=PriceBasis.RAW), *d.history[1:]), d.cutoff,
             d.adjustments_known_at, "requires split_adjusted"),
            ("too late", d.history, d.cutoff + timedelta(days=1), d.adjustments_known_at,
             "target UTC date"),
            ("too early", d.history, d.history[-1].session.closes_at, d.history[-1].session.closes_at,
             "market snapshot was unavailable"),
            ("future adjustment", d.history, d.cutoff, d.cutoff + timedelta(seconds=1),
             "Split adjustments were unavailable"),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, error):
                regular_history(history, d.target_date, ("DEMOA",), cutoff, adjustments)

    def test_first_breakout_cannot_be_replaced_with_a_later_match(self):
        d = self.run_input
        history = regular_history(d.history, d.target_date, ("DEMOA",), d.cutoff, d.adjustments_known_at)
        changed = list(history[-76:])
        for i, close, volume in ((61, "52", 180), (74, "54", 250), (75, "54", 100)):
            snapshot = changed[i]
            changed[i] = replace(
                snapshot, bars=(replace(snapshot.bars[0], close=Decimal(close), volume=volume),)
            )
        strategy = BreakoutRetestShape()
        failed, = strategy.evaluate(StrategyInput(d.cutoff, ("DEMOA",), tuple(changed)))
        self.assertEqual(failed.reason, "FIRST_BREAKOUT_RETEST_FAILED")
        self.assertIsNone(failed.signal)
        snapshot = changed[61]
        changed[61] = replace(snapshot, bars=(replace(snapshot.bars[0], volume=100),))
        matched, = strategy.evaluate(StrategyInput(d.cutoff, ("DEMOA",), tuple(changed)))
        self.assertEqual(matched.reason, "SHAPE_MATCH")
        self.assertEqual(matched.signal.known_at, d.cutoff)


class IwbAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.uploaded = read_replay(CONFIG).candidates.snapshot.provenance.available_at

    def read(self, payload, **kwargs):
        options = dict(
            artifact="synthetic:demo",
            artifact_sha256=sha256(payload).hexdigest(),
            uploaded_at=self.uploaded,
            synthetic=True,
        )
        return read_pipeline_candidates(payload, **(options | kwargs))

    def test_zip_path_reads_only_the_complete_us_audit(self):
        archive = BytesIO()
        with ZipFile(archive, "w") as zipper:
            zipper.writestr("daily-report.json", (DEMO / "candidate_audit.json").read_bytes())
        seed = self.read(
            archive.getvalue(),
            synthetic=False,
            artifact="https://github.com/EFSing/stock-data-pipeline/actions/runs/123/artifacts/456",
        )
        self.assertEqual(seed.seed_count, 6)
        self.assertEqual(seed.active_count, 5)
        self.assertEqual(tuple(member.symbol for member in seed.snapshot.members),
                         ("DEMOA", "DEMOB", "DEMOC", "DEMOD"))

    def test_rejects_wrong_checksum_and_undated_or_incomplete_seed(self):
        payload = (DEMO / "candidate_audit.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            self.read(payload, artifact_sha256="0" * 64)
        for key, value in (("seed_count", 7), ("seed_source_as_of", "2026-04-18")):
            with self.subTest(key=key):
                report = json.loads(payload)
                report["candidate_markets"]["US"][key] = value
                with self.assertRaisesRegex(ValueError, "complete dated IWB audit"):
                    self.read(json.dumps(report).encode())

    def test_candidate_contract_distinguishes_selection_from_incomplete_provider(self):
        fixture = (DEMO / "candidate_audit.json").read_bytes()
        for key, value, error in (
            ("candidate_included_count", 5, "audit flags disagree"),
            ("candidate_included_symbols", ["DEMOA", "DEMOB", "DEMOC", "DEMOF"], "audit flags disagree"),
            ("candidate_selection_outcome", "DISCOVERY_FAILED", "did not publish"),
        ):
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, error):
                report = json.loads(fixture)
                report["candidate_markets"]["US"][key] = value
                self.read(json.dumps(report).encode())

    def test_rejects_duplicates_foreign_rows_and_early_archive_timestamp(self):
        payload = (DEMO / "candidate_audit.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "upload must follow"):
            self.read(payload, uploaded_at=self.uploaded - timedelta(minutes=10))
        for key, value, error in (
            ("symbol", "DEMOA", "duplicate canonical symbols"),
            ("market", "CN", "inconsistent market"),
            ("source", "other_vendor", "inconsistent market"),
        ):
            with self.subTest(key=key):
                report = json.loads(payload)
                report["candidate_markets"]["US"]["candidate_records"][1][key] = value
                with self.assertRaisesRegex(ValueError, error):
                    self.read(json.dumps(report).encode())
