import json
import unittest
from datetime import UTC, date, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from zipfile import ZipFile

from test_iwb_daily import HoldingsResponse, ROOT, TARGET, holdings
from test_yahoo_chart import response
from us_watchlist.app.iwb_automation import DAILY_PREFIX, POOL_PREFIX, _target, automate_iwb
from us_watchlist.app.iwb_daily import HISTORY_SESSIONS, REPORT_FILES, observe_iwb, verify_completed
from us_watchlist.integrations.github_artifacts import Artifact, GitHubArtifacts
from us_watchlist.integrations.iwb_holdings import refresh_holdings
from us_watchlist.integrations.xnys import regular_windows
from us_watchlist.integrations.yahoo_chart import HOSTS, _chart_url


class AutomationTests(unittest.TestCase):
    def setUp(self):
        root = ROOT / ".runtime" / "tmp"
        root.mkdir(parents=True, exist_ok=True)
        temp = TemporaryDirectory(dir=root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_schedule_uses_new_york_date_and_rejects_holidays_and_pre_close(self):
        self.assertEqual(_target(datetime(2025, 11, 27, 22, 37, tzinfo=UTC), True, None),
                         (date(2025, 11, 27), "SKIPPED_XNYS_CLOSED"))
        self.assertEqual(_target(datetime(2025, 11, 28, 18, 20, tzinfo=UTC), True, None),
                         (TARGET, "SKIPPED_NOT_READY"))
        self.assertEqual(_target(datetime(2025, 11, 29, 1, 0, tzinfo=UTC), True, None), (TARGET, None))
        with self.assertRaisesRegex(ValueError, "MANUAL_TARGET_REQUIRES_COMPLETED"):
            _target(datetime(2025, 11, 28, 17, 55, tzinfo=UTC), False, TARGET)

    def test_download_retries_recent_unavailable_artifact_without_exposing_token(self):
        env = {"GITHUB_REPOSITORY": "example/example", "IWB_DEFAULT_BRANCH": "main", "GH_TOKEN": "test-token"}
        with patch.dict("os.environ", env):
            archive = GitHubArtifacts()
        url = f"{archive.root}/1/zip"
        error = HTTPError(url, 404, "Not Found", {}, None)
        with (
            patch("us_watchlist.integrations.github_artifacts.urlopen", side_effect=(error, BytesIO(b"present"))) as request,
            patch("us_watchlist.integrations.github_artifacts.sleep") as delay,
        ):
            self.assertEqual(archive._read(url), b"present")
        self.assertEqual(request.call_count, 2)
        self.assertNotIn("Authorization", request.call_args.args[0].headers)
        self.assertIn("Authorization", request.call_args.args[0].unredirected_hdrs)
        delay.assert_called_once_with(2)

    def test_retry_retains_failed_attempt_and_uses_same_restored_pool(self):
        pool_name = POOL_PREFIX + "2025-11-26"
        archive = Mock(spec=GitHubArtifacts)
        archive.catalog.return_value = {pool_name: Artifact(pool_name, 1, "", 42)}
        incomplete = {"status": "YAHOO_TARGET_COVERAGE_BELOW_FLOOR", "yahoo_zip_sha256": "1" * 64,
                      "holdings_csv_sha256": "a" * 64, "target_bars": 0}
        complete = {**incomplete, "status": "PARTIAL_COVERAGE", "yahoo_zip_sha256": "2" * 64,
                    "report_sha256": "3" * 64, "target_bars": 901}
        with (
            patch("us_watchlist.app.iwb_automation.read_holdings", return_value=Mock(day=date(2025, 11, 26))),
            patch("us_watchlist.app.iwb_automation.observe_iwb", side_effect=(incomplete, complete)) as observe,
            patch("us_watchlist.app.iwb_automation.verify_completed") as verify,
            patch("us_watchlist.app.iwb_automation.wait_before_recapture") as retry,
        ):
            state, outputs = automate_iwb(self.root, archive, "a" * 40, scheduled=False, trade_date=TARGET)
        self.assertEqual(state["status"], "PARTIAL_COVERAGE")
        self.assertEqual(state["pool_restored"], {"date": "2025-11-26", "run_id": 42})
        self.assertEqual([record["status"] for record in state["attempts"]], [incomplete["status"], complete["status"]])
        self.assertEqual(observe.call_args_list[0].args[1], observe.call_args_list[1].args[1])
        retry.assert_called_once_with()
        verify.assert_called_once_with(self.root / "attempt-2", TARGET)
        self.assertEqual(outputs["report_name"], DAILY_PREFIX + TARGET.isoformat())
        self.assertEqual(outputs["diagnostic_attempt_1"], str(self.root / "attempt-1"))
        self.assertNotIn("diagnostic_attempt_2", outputs)
        self.assertEqual(json.loads(Path(outputs["diagnostic_receipt"]).read_bytes()), state)

    def test_successful_evidence_replays_and_published_identity_skips_live_acquisition(self):
        pool = self.root / "pool"
        published = self.root / "published"
        with patch("us_watchlist.integrations.iwb_holdings.urlopen", return_value=HoldingsResponse(holdings())):
            refresh_holdings(pool, None, TARGET)
        windows = regular_windows(TARGET, HISTORY_SESSIONS)
        stamps = [int(window.opens_at.timestamp()) for window in windows]

        def fetch(symbol, first, through):
            body = response(stamps, symbol=symbol)
            return {"symbol": symbol, "url": _chart_url(HOSTS[0], symbol, first, through), "attempts": [],
                    "received_at": datetime.now(UTC).isoformat(), "sha256": sha256(body).hexdigest()}, body

        with patch("us_watchlist.integrations.yahoo_chart._fetch", side_effect=fetch):
            run = observe_iwb(TARGET, pool, published, "a" * 40)
        self.assertEqual(run["status"], "PARTIAL_COVERAGE")
        self.assertEqual(verify_completed(published, TARGET), run)
        stamps = stamps[-1:]
        with patch("us_watchlist.integrations.yahoo_chart._fetch", side_effect=fetch):
            short = observe_iwb(TARGET, pool, self.root / "short-history", "a" * 40)
        self.assertEqual(short["target_bars"], short["listed_equities"])
        self.assertEqual(short["status"], "YAHOO_STRATEGY_HISTORY_UNAVAILABLE")
        body = BytesIO()
        with ZipFile(body, "w") as bundle:
            for name in REPORT_FILES:
                bundle.write(published / name, arcname=name)
        name = DAILY_PREFIX + TARGET.isoformat()
        digest = f"sha256:{sha256(body.getvalue()).hexdigest()}"
        row = {"name": name, "id": 1, "expired": False, "digest": digest, "workflow_run": {
            "id": 42, "head_branch": "main", "repository_id": 3, "head_repository_id": 3,
        }}
        env = {"GITHUB_REPOSITORY": "example/example", "IWB_DEFAULT_BRANCH": "main", "GH_TOKEN": "unused"}
        with patch.dict("os.environ", env):
            archive = GitHubArtifacts()
        with (
            patch.object(archive, "_read", side_effect=(json.dumps({"artifacts": [row]}).encode(), body.getvalue())),
            patch("us_watchlist.app.iwb_automation.observe_iwb") as observe,
        ):
            state, outputs = automate_iwb(self.root / "rerun", archive, "b" * 40, scheduled=False, trade_date=TARGET)
        self.assertEqual(state["status"], "REUSED_PUBLISHED_REPORT")
        self.assertEqual(state["existing_report"]["report_sha256"], run["report_sha256"])
        self.assertNotIn("report_name", outputs)
        observe.assert_not_called()
        (published / "report.html").write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "IWB_ARCHIVED_FILE_SHA_MISMATCH"):
            verify_completed(published, TARGET)
        with patch.object(archive, "_read", return_value=json.dumps({"artifacts": [row, row]}).encode()):
            with self.assertRaisesRegex(ValueError, "GITHUB_ARTIFACT_IDENTITY_CONFLICT"):
                archive.catalog()
        with patch.object(archive, "_read", return_value=b"altered"):
            with self.assertRaisesRegex(ValueError, "GITHUB_ARTIFACT_DIGEST_MISMATCH"):
                archive.restore(Artifact(name, 1, digest, 42), self.root / "bad", REPORT_FILES)
