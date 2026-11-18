import json
import unittest
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from us_watchlist.domain.models import Provenance, SessionKind, SessionWindow
from us_watchlist.integrations.yahoo_chart import _quote_rows, capture_yahoo, read_yahoo

ROOT = Path(__file__).resolve().parents[1]


def session(day: date) -> SessionWindow:
    return SessionWindow(
        day, SessionKind.REGULAR, datetime(day.year, day.month, day.day, 14, 30, tzinfo=UTC),
        datetime(day.year, day.month, day.day, 21, tzinfo=UTC),
    )


def response(stamps: list[int], symbol: str = "ABC", splits: tuple[int, ...] = ()) -> bytes:
    return json.dumps({"chart": {"error": None, "result": [{
        "meta": {"symbol": symbol, "currency": "USD", "instrumentType": "EQUITY",
                 "exchangeTimezoneName": "America/New_York", "dataGranularity": "1d"},
        "timestamp": stamps,
        "events": {"splits": {str(t): {"date": t} for t in splits}},
        "indicators": {
            "quote": [{key: [value] * len(stamps) for key, value in
                       (("open", 10), ("high", 12), ("low", 9), ("close", 11), ("volume", 100))}],
            "adjclose": [{"adjclose": [3] * len(stamps)}],
        },
    }]}}).encode()


class YahooChartTests(unittest.TestCase):
    def test_quote_uses_regular_unadjusted_for_dividends_and_trims_splits_and_post_target_bars(self):
        first, second, later = (session(date(2026, 11, day)) for day in (13, 16, 17))
        windows = {window.trading_date: window for window in (first, second)}
        stamps = [int(window.opens_at.timestamp()) for window in (first, second, later)]
        rows, gap = _quote_rows("ABC", response(stamps, splits=(stamps[0],)), windows, later.trading_date)
        self.assertEqual(list(rows), [second.trading_date])
        self.assertEqual(rows[second.trading_date].close, 11)
        self.assertIn("2026-11-13", gap)
        rows, gap = _quote_rows("ABC", response(stamps, splits=(stamps[-1],)), windows, later.trading_date)
        self.assertEqual(rows, {})
        self.assertIn("2026-11-17", gap)
        for invalid, message in (
            (response(stamps, symbol="WRONG"), "INCONSISTENT_SYMBOL"),
            (response([stamps[0], stamps[0]]), "DUPLICATE"),
            (response([stamps[0] - 60]), "UNEXPECTED_REGULAR"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                _quote_rows("ABC", invalid, windows, later.trading_date)

    def test_capture_freezes_xnys_sessions_and_preserves_failed_provider_state(self):
        target = date(2025, 11, 28)
        provenance = Provenance("verified test input", "a" * 64, datetime.now(UTC) - timedelta(hours=1))
        temp = ROOT / ".runtime" / "tmp"
        temp.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=temp) as directory:
            bundle = Path(directory) / "chart.zip"
            with patch("us_watchlist.integrations.yahoo_chart._fetch",
                       return_value=({"symbol": "ABC", "attempts": ["query1 HTTP_503"]}, None)):
                digest, count = capture_yahoo(bundle, target, ("ABC",), provenance, 76)
            self.assertEqual(count, 0)
            payload = bundle.read_bytes()
            history, observed, calendar, gaps = read_yahoo(payload, digest, target, ("ABC",), provenance)
            self.assertEqual(len(history), 76)
            self.assertEqual(history[-1].session.closes_at.hour, 18)  # day after Thanksgiving
            self.assertEqual(history[-1].provenance.available_at, observed)
            self.assertIn("XNYS", calendar)
            self.assertIn("YAHOO_FETCH_FAILED", gaps[0][1])
            with ZipFile(bundle) as archive:
                self.assertEqual(archive.namelist(), ["manifest.json"])
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                read_yahoo(payload, "0" * 64, target, ("ABC",), provenance)
            with self.assertRaisesRegex(ValueError, "does not match the published Candidate list"):
                read_yahoo(payload, digest, target, ("DEF",), provenance)
