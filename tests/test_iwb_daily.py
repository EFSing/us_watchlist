import json
import unittest
from datetime import UTC, date, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from us_watchlist.app.iwb_daily import observe_iwb
from us_watchlist.domain.models import Provenance
from us_watchlist.integrations.iwb_holdings import LATEST, parse_holdings, read_holdings, refresh_holdings
from us_watchlist.integrations.xnys import completed_session, regular_windows

TARGET = date(2025, 11, 28)
ROOT = Path(__file__).resolve().parents[1]


def holdings(old=False):
    when = "Nov 12, 2025" if old else "Nov 26, 2025"
    equities = "".join(f"ABC{index},Equity,NASDAQ,USD\n" for index in range(900))
    return (
        f'iShares Russell 1000 ETF\nFund Holdings as of,"{when}"\n'
        "Ticker,Asset Class,Exchange,Market Currency\n"
        f"{equities}BRK B,Equity,NYSE,USD\nHOLX,Equity,NO MARKET (E.G. UNLISTED),USD\n"
        "USD,Cash,-,USD\n"
    ).encode()


class HoldingsResponse(BytesIO):
    def geturl(self):
        return LATEST

    @property
    def headers(self):
        from email.message import Message

        headers = Message()
        headers["Content-Type"] = "text/csv"
        return headers


class IwbDailyTests(unittest.TestCase):
    def setUp(self):
        root = ROOT / ".runtime" / "tmp"
        root.mkdir(parents=True, exist_ok=True)
        temp = TemporaryDirectory(dir=root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.pool = self.root / "pool"

    def refresh(self, raw=None):
        with patch("us_watchlist.integrations.iwb_holdings.urlopen", return_value=HoldingsResponse(raw or holdings())):
            return refresh_holdings(self.pool, None, TARGET)

    def test_official_equity_snapshot_is_immutable_and_reports_membership_exclusions(self):
        path, version = self.refresh()
        original = path.read_bytes()
        self.assertEqual(path.name, "IWB_2025-11-26.zip")
        self.assertEqual(len(version.snapshot.members), 902)
        self.assertEqual(version.non_equity_rows, 1)
        self.assertEqual(version.inactive, (("HOLX", "IWB_UNLISTED_OR_NO_MARKET"),))
        self.assertIn("BRK-B", {member.symbol for member in version.snapshot.members})
        self.assertEqual(read_holdings(path), version)
        self.assertEqual(self.refresh(), (path, version))
        with self.assertRaisesRegex(ValueError, "IWB_SAME_DATE_CONTENT_CONFLICT"):
            self.refresh(holdings().replace(b"ABC0,", b"XYZ,"))
        with self.assertRaisesRegex(ValueError, "IWB_DOWNLOAD_DATE_UNUSABLE"):
            self.refresh(holdings(old=True))
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.pool.iterdir()), [path])

    def test_invalid_market_and_duplicate_normalized_symbols_are_rejected(self):
        provenance = Provenance(LATEST, "test", datetime(2025, 11, 28, tzinfo=UTC))
        for raw, message in (
            (holdings().replace(b"NASDAQ,USD", b"SIX,USD", 1), "UNKNOWN_EQUITY_EXCHANGE"),
            (holdings().replace(b"NASDAQ,USD", b"NASDAQ,CAD", 1), "MARKET_CURRENCY"),
            (holdings() + b"BRK.B,Equity,NYSE,USD\n", "DUPLICATE_SYMBOL"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                parse_holdings(raw, provenance)

    def test_observation_preserves_provider_failure_and_reuses_frozen_inputs(self):
        self.refresh()
        output = self.root / "daily"

        def unavailable(symbol, first, through):
            return {"symbol": symbol, "attempts": ["query1 HTTP_429", "query2 HTTP_429"]}, None

        with patch("us_watchlist.integrations.yahoo_chart._fetch", side_effect=unavailable) as fetch:
            run = observe_iwb(TARGET, self.pool, output, "a" * 40)
            self.assertEqual(observe_iwb(TARGET, self.pool, output, "a" * 40), run)
            self.assertLess(fetch.call_count, 901)
        self.assertEqual(run["status"], "YAHOO_TARGET_COVERAGE_BELOW_FLOOR")
        self.assertEqual(run["listed_equities"], 901)
        self.assertEqual(run["target_bars"], 0)
        self.assertEqual(run["session_close_utc"], "2025-11-28T18:00:00+00:00")
        self.assertEqual(run["report_sha256"], sha256((output / "report.html").read_bytes()).hexdigest())
        self.assertEqual(json.loads((output / "run.json").read_bytes()), run)
        self.assertIn("研究效果未验证", (output / "report.html").read_text(encoding="utf-8"))
        with self.assertRaisesRegex(ValueError, "identity already used"):
            observe_iwb(TARGET, self.pool, output, "b" * 40)

    def test_xnys_holiday_early_close_and_dst(self):
        before = datetime(2025, 11, 28, 17, 59, tzinfo=UTC)
        after = datetime(2025, 11, 28, 18, 1, tzinfo=UTC)
        self.assertEqual(completed_session(before), date(2025, 11, 26))
        self.assertEqual(completed_session(after), TARGET)
        self.assertEqual(regular_windows(date(2025, 7, 1), 1)[0].closes_at.hour, 20)
        with self.assertRaisesRegex(ValueError, "NOT_XNYS_SESSION"):
            regular_windows(date(2025, 11, 27), 1)
