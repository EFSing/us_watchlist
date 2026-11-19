import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from us_watchlist.app.smoke import run_smoke
from us_watchlist.domain.models import SessionKind
from us_watchlist.integrations.local_artifacts import publish_once
from us_watchlist.integrations.smoke_fixture import read_fixture
from us_watchlist.market_data.quality import completed_bars
from us_watchlist.universe.eligibility import eligible_symbols

FIXTURE = Path(__file__).resolve().parents[1] / "configs" / "smoke.toml"
TEMP_ROOT = FIXTURE.parents[1] / ".runtime" / "tmp"


def setUpModule():
    TEMP_ROOT.mkdir(parents=True, exist_ok=True)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.universe, self.market, self.cutoff, _ = read_fixture(FIXTURE)

    def test_lookahead_and_incomplete_session_fail(self):
        with self.assertRaisesRegex(ValueError, "Universe snapshot was unavailable"):
            eligible_symbols(
                self.universe, self.market.session, self.universe.provenance.available_at
                - timedelta(seconds=1),
            )
        future_roster = replace(
            self.universe, effective_date=self.market.session.trading_date + timedelta(days=1)
        )
        with self.assertRaisesRegex(ValueError, "Universe snapshot was unavailable"):
            eligible_symbols(future_roster, self.market.session, self.cutoff)
        with self.assertRaisesRegex(ValueError, "market snapshot was unavailable"):
            completed_bars(self.market, ("DEMOA",), self.market.session.closes_at)
        incomplete = replace(
            self.market,
            provenance=replace(
                self.market.provenance, available_at=self.market.session.closes_at - timedelta(seconds=1)
            ),
        )
        with self.assertRaisesRegex(ValueError, "before the session closes"):
            completed_bars(incomplete, ("DEMOA",), self.cutoff)

    def test_duplicate_universe_and_bars_fail(self):
        duplicate_universe = replace(self.universe, members=self.universe.members * 2)
        with self.assertRaisesRegex(ValueError, "duplicate symbols"):
            eligible_symbols(duplicate_universe, self.market.session, self.cutoff)
        duplicate_bars = replace(self.market, bars=self.market.bars * 2)
        with self.assertRaisesRegex(ValueError, "duplicate bars"):
            completed_bars(duplicate_bars, ("DEMOA",), self.cutoff)

    def test_invalid_bar_range_and_local_time_fail(self):
        with self.assertRaisesRegex(ValueError, "Inconsistent OHLC"):
            replace(self.market.bars[0], high=self.market.bars[0].low)
        with self.assertRaisesRegex(ValueError, "must use UTC"):
            replace(self.market.session, opens_at=self.market.session.opens_at.replace(tzinfo=None))


class SmokeTests(unittest.TestCase):
    def test_pipeline_reports_coverage_and_reuses_artifact(self):
        with TemporaryDirectory(dir=TEMP_ROOT) as directory:
            output = Path(directory)
            path = run_smoke(FIXTURE, output)
            report = path.read_text(encoding="utf-8")
            self.assertEqual(path.name, "US_2026-01-05_regular.html")
            self.assertIn("Synthetic input coverage", report)
            self.assertIn("smoke-universe-1", report)
            self.assertIn("Input SHA-256", report)
            self.assertIn("<dt>Completed bars</dt><dd>DEMOA, DEMOB</dd>", report)
            self.assertIn("<dt>Missing bars</dt><dd>DEMOD</dd>", report)
            self.assertIn("<dt>Median volume</dt><dd>180.0</dd>", report)
            self.assertNotIn("DEMOC", report)
            self.assertEqual(run_smoke(FIXTURE, output), path)
            self.assertEqual(list(output.iterdir()), [path])

    def test_all_sessions_have_distinct_artifact_identities(self):
        with TemporaryDirectory(dir=TEMP_ROOT) as directory:
            root = Path(directory)
            source = FIXTURE.read_text(encoding="utf-8")
            results = set()
            for kind in SessionKind:
                config = root / f"{kind}.toml"
                session = source.replace('kind = "regular"', f'kind = "{kind}"')
                if kind is SessionKind.IBKR_OVERNIGHT:
                    session = session.replace("2026-01-05T14:30:00Z", "2026-01-04T23:00:00Z")
                config.write_text(session, encoding="utf-8")
                results.add(run_smoke(config, root / "artifacts").name)
            self.assertEqual(len(results), 4)

    def test_non_us_fixture_creates_no_artifacts(self):
        with TemporaryDirectory(dir=TEMP_ROOT) as directory:
            root = Path(directory)
            config = root / "foreign.toml"
            source = FIXTURE.read_text(encoding="utf-8")
            config.write_text(source.replace('market = "US"', 'market = "CN"'), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "US synthetic_smoke fixture"):
                run_smoke(config, root / "artifacts")
            self.assertFalse((root / "artifacts").exists())

    def test_changed_fixture_cannot_replace_existing_output(self):
        with TemporaryDirectory(dir=TEMP_ROOT) as directory:
            root = Path(directory)
            output = root / "artifacts"
            path = run_smoke(FIXTURE, output)
            original = path.read_bytes()
            config = root / "changed.toml"
            config.write_bytes(FIXTURE.read_bytes().replace(b"close = 11.25", b"close = 11.75"))
            with self.assertRaisesRegex(ValueError, "different content"):
                run_smoke(config, output)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(output.iterdir()), [path])

    def test_conflicting_publishers_leave_one_complete_file(self):
        with TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "report.html"
            bodies = (b"abc" * 20000, b"xyz" * 20000)
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [executor.submit(publish_once, path, body) for body in bodies]
            winners = [body for body, future in zip(bodies, futures) if future.exception() is None]
            failures = [future.exception() for future in futures if future.exception() is not None]
            self.assertEqual(winners, [path.read_bytes()])
            self.assertEqual(len(failures), 1)
            self.assertIsInstance(failures[0], ValueError)
            self.assertEqual(list(path.parent.iterdir()), [path])
