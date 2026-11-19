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
from us_watchlist.app.iwb_automation import DAILY_PREFIX, POOL_PREFIX, _manual_target, _scheduled_target, automate_iwb
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

    def test_schedule_uses_local_date_and_records_the_early_close(self):
        created = datetime(2025, 11, 28, 22, 37, tzinfo=UTC)
        state = {}
        self.assertEqual(_scheduled_target(datetime(2025, 11, 29, 1, tzinfo=UTC), created, state), (TARGET, None))
        self.assertEqual(state["session_close_utc"], "2025-11-28T18:00:00+00:00")
        self.assertEqual(state["settlement_ready_at"], "2025-11-28T18:30:00+00:00")
        self.assertEqual(state["scheduled_for_utc"], created.isoformat())
        self.assertEqual(_scheduled_target(datetime(2025, 12, 1, 23, tzinfo=UTC), created, {}),
                         (TARGET, "SKIPPED_SCHEDULE_EXPIRED"))
        early = datetime(2025, 11, 28, 18, 20, tzinfo=UTC)
        self.assertEqual(_scheduled_target(early, early, {}), (TARGET, "SKIPPED_NOT_READY"))
        with self.assertRaisesRegex(ValueError, "MANUAL_TARGET_REQUIRES_COMPLETED"):
            _manual_target(datetime(2025, 11, 28, 17, 55, tzinfo=UTC), TARGET)
        self.assertEqual(_manual_target(early, None), TARGET)

    def test_schedule_switches_utc_hour_at_daylight_saving(self):
        for month, day, utc_hour in ((3, 7, 22), (3, 10, 21), (10, 31, 21), (11, 3, 22)):
            due = datetime(2025, month, day, utc_hour, 37, tzinfo=UTC)
            state = {}
            with self.subTest(due=due):
                self.assertEqual(_scheduled_target(due, due, state), (due.date(), None))
                self.assertEqual(state["scheduled_for_utc"], due.isoformat())

    def test_scheduled_event_does_not_use_manual_dates_or_touch_archives_on_holidays(self):
        archive = Mock(spec=GitHubArtifacts)
        holiday = datetime(2025, 11, 27, 22, 37, tzinfo=UTC)
        archive.schedule_created_at.return_value = holiday
        for option in ("trade_date", "holdings_date"):
            state, _ = automate_iwb(self.root / option, archive, "a" * 40, scheduled=True, **{option: TARGET})
            self.assertIn("IWB_SCHEDULE_DISALLOWS_MANUAL_DATES", state["error"])
        archive.schedule_created_at.assert_not_called()
        with patch("us_watchlist.app.iwb_automation.datetime", wraps=datetime) as clock:
            clock.now.return_value = holiday
            state, outputs = automate_iwb(self.root / "holiday", archive, "a" * 40, scheduled=True)
        self.assertEqual(state["status"], "SKIPPED_XNYS_CLOSED")
        self.assertEqual(state["trade_date"], "2025-11-27")
        self.assertNotIn("report_name", outputs)
        archive.schedule_created_at.assert_called_once_with("a" * 40)
        archive.catalog.assert_not_called()

    def test_schedule_uses_original_github_run_creation_time(self):
        env = {"GITHUB_REPOSITORY": "example/example", "IWB_DEFAULT_BRANCH": "main", "GH_TOKEN": "unused",
               "GITHUB_RUN_ID": "42"}
        row = {"id": 42, "event": "schedule", "head_branch": "main", "head_sha": "a" * 40,
               "created_at": "2025-11-28T22:37:05Z", "run_started_at": "2025-11-29T01:00:00Z"}
        with patch.dict("os.environ", env):
            archive = GitHubArtifacts()
            with patch.object(archive, "_read", return_value=json.dumps(row).encode()) as read:
                self.assertEqual(archive.schedule_created_at("a" * 40), datetime(2025, 11, 28, 22, 37, 5, tzinfo=UTC))
                read.assert_called_once_with(f"{archive.actions_root}/runs/42")
                with self.assertRaisesRegex(ValueError, "GITHUB_SCHEDULE_RUN_MISMATCH"):
                    archive.schedule_created_at("b" * 40)
            row["event"] = "workflow_dispatch"
            with patch.object(archive, "_read", return_value=json.dumps(row).encode()):
                with self.assertRaisesRegex(ValueError, "GITHUB_SCHEDULE_RUN_MISMATCH"):
                    archive.schedule_created_at("a" * 40)

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
        self.assertFalse(observe.call_args.kwargs["require_yahoo_close"])
        archive.schedule_created_at.assert_not_called()
        retry.assert_called_once_with()
        verify.assert_called_once_with(self.root / "attempt-2", TARGET)
        self.assertEqual(outputs["report_name"], DAILY_PREFIX + TARGET.isoformat())
        self.assertEqual(outputs["diagnostic_attempt_1"], str(self.root / "attempt-1"))
        self.assertNotIn("diagnostic_attempt_2", outputs)
        self.assertEqual(json.loads(Path(outputs["diagnostic_receipt"]).read_bytes()), state)

    def test_scheduled_close_qualification_retains_both_failed_attempts_without_publishing(self):
        archive = Mock(spec=GitHubArtifacts)
        archive.catalog.return_value = {}
        created = datetime(2025, 11, 28, 22, 37, tzinfo=UTC)
        archive.schedule_created_at.return_value = created
        unavailable = {"status": "YAHOO_TARGET_COVERAGE_BELOW_FLOOR", "yahoo_zip_sha256": "1" * 64,
                       "holdings_csv_sha256": "a" * 64, "target_bars": 0, "observed_at": created.isoformat()}
        with (
            patch("us_watchlist.app.iwb_automation.datetime", wraps=datetime) as clock,
            patch("us_watchlist.app.iwb_automation._prepare_pool"),
            patch("us_watchlist.app.iwb_automation.observe_iwb", return_value=unavailable) as observe,
            patch("us_watchlist.app.iwb_automation.wait_before_recapture") as retry,
        ):
            clock.now.return_value = created
            state, outputs = automate_iwb(self.root, archive, "a" * 40, scheduled=True)
        self.assertEqual(state["status"], unavailable["status"])
        self.assertEqual([record["status"] for record in state["attempts"]], [unavailable["status"]] * 2)
        self.assertEqual(observe.call_count, 2)
        self.assertTrue(all(call.kwargs["require_yahoo_close"] for call in observe.call_args_list))
        retry.assert_called_once_with()
        self.assertIn("diagnostic_attempt_1", outputs)
        self.assertIn("diagnostic_attempt_2", outputs)
        self.assertNotIn("report_name", outputs)

    def test_schedule_expires_if_capture_or_retry_crosses_new_york_midnight(self):
        archive = Mock(spec=GitHubArtifacts)
        archive.catalog.return_value = {}
        archive.schedule_created_at.return_value = datetime(2025, 11, 28, 22, 37, tzinfo=UTC)
        before = datetime(2025, 11, 29, 4, 59, tzinfo=UTC)
        midnight = datetime(2025, 11, 29, 5, tzinfo=UTC)
        for status, observed, attempt_status in (
            ("PARTIAL_COVERAGE", midnight, "SKIPPED_SCHEDULE_EXPIRED"),
            ("YAHOO_TARGET_COVERAGE_BELOW_FLOOR", before, "YAHOO_TARGET_COVERAGE_BELOW_FLOOR"),
        ):
            with (
                self.subTest(status=status),
                patch("us_watchlist.app.iwb_automation.datetime", wraps=datetime) as clock,
                patch("us_watchlist.app.iwb_automation._prepare_pool"),
                patch("us_watchlist.app.iwb_automation.observe_iwb", return_value={
                    "status": status, "observed_at": observed.isoformat(), "yahoo_zip_sha256": "1" * 64,
                    "holdings_csv_sha256": "a" * 64, "target_bars": 10,
                }) as observe,
                patch("us_watchlist.app.iwb_automation.wait_before_recapture",
                      side_effect=lambda: setattr(clock.now, "return_value", midnight)) as retry,
            ):
                clock.now.return_value = before
                state, outputs = automate_iwb(self.root / status, archive, "a" * 40, scheduled=True)
                self.assertEqual(state["status"], "SKIPPED_SCHEDULE_EXPIRED")
                self.assertEqual([record["status"] for record in state["attempts"]], [attempt_status])
                self.assertEqual(retry.call_count, int(observed == before))
                observe.assert_called_once()
                self.assertIn("diagnostic_attempt_1", outputs)
                self.assertNotIn("report_name", outputs)

    def test_successful_evidence_replays_and_published_identity_skips_live_acquisition(self):
        pool = self.root / "pool"
        published = self.root / "published"
        source = holdings().replace(b"ABC0,", b"SNDK,", 1)
        with patch("us_watchlist.integrations.iwb_holdings.urlopen", return_value=HoldingsResponse(source)):
            refresh_holdings(pool, None, TARGET)
        windows = regular_windows(TARGET, HISTORY_SESSIONS)
        stamps = [int(window.opens_at.timestamp()) for window in windows]

        def fetch(symbol, first, through):
            series = stamps[-2:] if symbol == "SNDK" else stamps
            body = response(series, symbol=symbol, market_time=int(windows[-1].closes_at.timestamp()))
            return {"symbol": symbol, "url": _chart_url(HOSTS[0], symbol, first, through), "attempts": [],
                    "received_at": datetime.now(UTC).isoformat(), "sha256": sha256(body).hexdigest()}, body

        with patch("us_watchlist.integrations.yahoo_chart._fetch", side_effect=fetch):
            run = observe_iwb(TARGET, pool, published, "a" * 40, require_yahoo_close=True)
        self.assertEqual(run["status"], "PARTIAL_COVERAGE")
        self.assertEqual(run["target_bars"], run["listed_equities"])
        self.assertEqual(run["full_history_symbols"], run["listed_equities"] - 1)
        self.assertEqual(run["symbol_diagnostics"], {"SNDK": "YAHOO_REGULAR_HISTORY_GAP 2/120"})
        for strategy in run["strategies"].values():
            self.assertEqual(strategy["evaluated"], run["listed_equities"])
            self.assertEqual(strategy["incomplete_history"], 1)
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
        scheduled_at = datetime(2025, 11, 28, 22, 37, tzinfo=UTC)
        with (
            patch("us_watchlist.app.iwb_automation.datetime", wraps=datetime) as clock,
            patch.object(archive, "schedule_created_at", return_value=scheduled_at),
            patch.object(archive, "_read", side_effect=(json.dumps({"artifacts": [row]}).encode(), body.getvalue())),
            patch("us_watchlist.app.iwb_automation.observe_iwb") as observe,
        ):
            clock.now.return_value = datetime(2025, 11, 29, 1, tzinfo=UTC)
            state, outputs = automate_iwb(self.root / "scheduled-rerun", archive, "b" * 40, scheduled=True)
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
