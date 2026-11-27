import json
import unittest
from datetime import date, datetime, timedelta
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile

from test_iwb_daily import ROOT
from test_iwb_notifications import RUN
from test_iwb_paper import SIGNAL_BAR, START, T1, T2, candidate, position_day, position_policy
from us_watchlist.app.iwb_automation import DAILY_PREFIX, automate_iwb
from us_watchlist.app.iwb_daily import REPORT_FILES
from us_watchlist.app.iwb_notifications import send_iwb_email
from us_watchlist.app.iwb_paper import run_study
from us_watchlist.domain.company_catalog import issuer_key
from us_watchlist.domain.paper import ACCOUNT_POLICY, POSITION_PROTOCOL, Mode, Status, check_policy
from us_watchlist.integrations.github_artifacts import Artifact, GitHubArtifacts, paper_workflow_variables
from us_watchlist.integrations.paper_bundle import PAPER_PREFIX, verify_bundle
from us_watchlist.integrations.xnys import next_session, regular_windows

ACCOUNT = {
    "max_open_positions": 8, "max_new_entries_per_session": 3, "cooldown_sessions": 5,
    "deduplicate_issuer": True, "core_only": False,
}
PASS = ("100", "104", "96", "102")
GAP = ("94", "104", "93", "102")
STOP = ("100", "104", "94", "102")
MARKUP = (
    '<html><head></head><body><a href="#overview">今日总览</a>'
    '<section id="candidates" class="panel"></section></body></html>'
).encode("utf-8")


def plan(symbol, rank=None, *, fresh=True, stage="W2_TO_W3_TRANSITION_PROXY", risk="0.05", rr="4"):
    row = candidate(symbol)
    row.update(issuer_key=issuer_key(symbol), core_rank=rank, entry_risk=risk, fresh_turn=fresh, structure_origin=None)
    row["structure"]["stage"] = stage
    row["levels"]["rr"] = rr
    return row


class PaperTests(unittest.TestCase):
    def setUp(self):
        directory = ROOT / ".runtime" / "tmp"
        directory.mkdir(parents=True, exist_ok=True)
        temp = TemporaryDirectory(dir=directory)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)


class AccountPolicyTests(PaperTests):
    def run_account(self, days, *, model=None, **limits):
        policy = position_policy(**(model or {})) | {ACCOUNT_POLICY: ACCOUNT | limits}
        previous = {}
        views = {}
        for day, (plans, new_bars) in days.items():
            data = position_day(day)
            data["candidates"] = plans
            symbols = previous.keys() | new_bars.keys() | {row["symbol"] for row in plans}
            data["quotes"] = {
                symbol: {"current": list(new_bars.get(symbol, PASS)),
                         "previous": list(previous.get(symbol, SIGNAL_BAR)), "diagnostic": "", "structures": {}}
                for symbol in symbols
            }
            previous = {symbol: quote["current"] for symbol, quote in data["quotes"].items()}
            _, views[day] = run_study(
                self.root, Mode.SYNTHETIC, START, day, policy, protocol=POSITION_PROTOCOL,
                initialize=day == START, evidence_loader=lambda _: data,
            )
        return views

    @staticmethod
    def reasons(view, day, signal):
        return {
            row["plan"]["symbol"]: [event["reason"] for event in row["history"] if event["trade_date"] == str(day)]
            for row in view["records"].values() if row["plan"]["signal_date"] == str(signal)
        }

    def test_strict_policy_validation(self):
        for overrides in (
            {"max_open_positions": True}, {"max_open_positions": 0}, {"max_new_entries_per_session": 0},
            {"cooldown_sessions": -1}, {"deduplicate_issuer": 1}, {"core_only": "false"}, {"unknown": 1},
        ):
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, "PAPER_INVALID_ACCOUNT_POLICY"):
                check_policy(position_policy() | {ACCOUNT_POLICY: ACCOUNT | overrides}, POSITION_PROTOCOL)
        with self.assertRaisesRegex(ValueError, "PAPER_UNKNOWN_POLICY_STRATEGY"):
            check_policy(position_policy() | {ACCOUNT_POLICY: ACCOUNT})
        check_policy(json.loads((ROOT / "configs/iwb_paper_us_b_v2.json").read_bytes()), POSITION_PROTOCOL)

    def test_core_and_priority_win_day_limit_and_deduplicate_different_tiers(self):
        first = [plan("AAA"), plan("TALL", 1, fresh=False), plan("ZETA", 0),
                 plan("LLYVA", 2), plan("LLYVK", 3)]
        views = self.run_account({START: (first, {}), T1: ([plan("ZETA", 0), plan("LLYVK", 1)], {}), T2: ([], {})})
        checks = self.reasons(views[T1], T1, START)
        for filled in ("ZETA", "TALL", "LLYVA"):
            self.assertEqual(checks[filled][0], "FILLED_AT_T1_OPEN")
        self.assertEqual(checks["AAA"], ["DAILY_NEW_ENTRY_LIMIT_REACHED"])
        self.assertEqual(checks["LLYVK"], ["ALREADY_HOLDING_SYMBOL"])
        self.assertEqual(self.reasons(views[T2], T2, T1), {
            "ZETA": ["ALREADY_HOLDING_SYMBOL"], "LLYVK": ["ALREADY_HOLDING_SYMBOL"],
        })

    def test_secondary_priority_and_core_only(self):
        first = [
            plan("A", fresh=False, risk="0.01"), plan("B", stage="W2_PULLBACK_PROXY", risk="0.01"),
            plan("C", risk="0.06", rr="9"), plan("D", rr="3"), plan("F", rr="4"), plan("E", rr="4"),
        ]
        view = self.run_account({START: (first, {}), T1: ([], {})})[T1]
        opened = sorted(symbol for symbol, reasons in self.reasons(view, T1, START).items()
                        if reasons[0] == "FILLED_AT_T1_OPEN")
        self.assertEqual(opened, ["D", "E", "F"])
        view = self.run_account({START: ([plan("A"), plan("Z", 0)], {}), T1: ([], {})}, core_only=True)[T1]
        self.assertEqual(self.reasons(view, T1, START)["A"], ["OUTSIDE_CORE_SHORTLIST"])

    def test_position_limit_and_intraday_exit_matches_opening_capacity(self):
        t3, t4 = next_session(T2), next_session(next_session(T2))
        days = {
            START: ([plan(symbol) for symbol in ("A", "B", "C")], {}),
            T1: ([plan(symbol) for symbol in ("D", "E", "F")], {}),
            T2: ([plan("G", 0), plan("H", 1), plan("I", 2)], {}),
            t3: ([plan("I", 0), plan("J", 1)], {"A": STOP}),
            t4: ([], {"B": GAP}),
        }
        views = self.run_account(days)
        self.assertEqual(self.reasons(views[t3], t3, T2)["I"], ["MAX_OPEN_POSITIONS_REACHED"])
        self.assertEqual(self.reasons(views[t4], t4, t3)["J"][0], "FILLED_AT_T1_OPEN")
        self.assertEqual(sum(row["status"] == Status.OPEN for row in views[t4]["records"].values()), 8)

    def test_gap_frees_slot_and_five_full_following_sessions_are_in_cooldown(self):
        days = {START: ([plan("LLYVA")], {}), T1: ([plan("LLYVK", 0), plan("GOOG", 1)], {}),
                T2: ([plan("LLYVK")], {"LLYVA": GAP})}
        day = T2
        for _ in range(6):
            day = next_session(day)
            days[day] = ([plan("LLYVK")], {})
        # Hold room after GOOG's first-day intraday exit.
        days[T2][1]["GOOG"] = STOP
        views = self.run_account(days, max_open_positions=1)
        self.assertEqual(self.reasons(views[T2], T2, T1), {
            "LLYVK": ["RECENT_EXIT_COOLDOWN"], "GOOG": ["FILLED_AT_T1_OPEN", "ACTIVE_STOP_TOUCHED"],
        })
        sessions = list(days)[2:]
        for signal, target in zip(sessions[:5], sessions[1:6]):
            self.assertEqual(self.reasons(views[target], target, signal)["LLYVK"], ["RECENT_EXIT_COOLDOWN"])
        self.assertEqual(self.reasons(views[day], day, sessions[-2])["LLYVK"][0], "FILLED_AT_T1_OPEN")

    def test_scheduled_open_exit_releases_capacity_and_starts_cooldown(self):
        first = plan("LLYVA")
        first["structure_origin"] = {
            "floor_anchor": "L2", "points": {"L2": [str(START), "98"]}, "known_on": str(START),
        }
        competing = [first | {"symbol": "LLYVK", "core_rank": 0}, first | {
            "symbol": "GOOG", "core_rank": 1, "issuer_key": issuer_key("GOOG"),
        }]
        days = {START: ([first], {}), T1: (competing, {"LLYVA": ("100", "103", "96", "97")}), T2: ([], {})}
        view = self.run_account(days, model={"structure_exit": True}, max_open_positions=1)[T2]
        self.assertEqual(self.reasons(view, T2, START)["LLYVA"], ["STRUCTURE_NEXT_OPEN"])
        self.assertEqual(self.reasons(view, T2, T1)["LLYVK"], ["RECENT_EXIT_COOLDOWN"])
        self.assertEqual(self.reasons(view, T2, T1)["GOOG"][0], "FILLED_AT_T1_OPEN")

    def test_prospective_requires_availability_and_blocks_plans_published_after_open(self):
        paper_root = self.root / "late"
        first = position_day(START)
        first["candidates"] = [plan("ALFA")]
        second = position_day(T1)
        for day, data in ((START, first), (T1, second)):
            available = regular_windows(T1, 1)[0].opens_at if day == START else regular_windows(T1, 1)[0].closes_at
            if day == T1:
                available += timedelta(hours=2)
            with self.assertRaisesRegex(ValueError, "PAPER_PROSPECTIVE_AVAILABILITY_REQUIRED"):
                run_study(paper_root, Mode.PROSPECTIVE, START, day, position_policy(),
                          protocol=POSITION_PROTOCOL, initialize=day == START, evidence_loader=lambda _: data)
            data["source"]["available_at"] = available.isoformat()
            _, view = run_study(paper_root, Mode.PROSPECTIVE, START, day, position_policy(),
                                protocol=POSITION_PROTOCOL, initialize=day == START, evidence_loader=lambda _: data)
        self.assertEqual(self.reasons(view, T1, START)["ALFA"], ["SIGNAL_NOT_KNOWN_BEFORE_T1_OPEN"])


class PaperAutomationTests(PaperTests):
    start = date(2025, 11, 26)
    second = date(2025, 11, 28)  # Thanksgiving is not a session.
    third = date(2025, 12, 1)
    policy_path = ROOT / "configs/iwb_paper_us_b_v2.json"

    def setUp(self):
        super().setUp()
        env = {"GITHUB_REPOSITORY": "example/example", "IWB_DEFAULT_BRANCH": "main", "GH_TOKEN": "unused"}
        with patch.dict("os.environ", env):
            self.archive = GitHubArtifacts()
        self.artifacts = {}
        read = patch.object(self.archive, "_read", side_effect=self.read)
        verify = patch("us_watchlist.app.iwb_automation.verify_completed", side_effect=self.verify_daily)
        evidence = patch("us_watchlist.app.iwb_paper.load_day", side_effect=self.load_day)
        for dependency in (read, verify, evidence):
            dependency.start()
            self.addCleanup(dependency.stop)

    @staticmethod
    def available(target):
        return regular_windows(target, 1)[0].closes_at + timedelta(hours=2)

    @staticmethod
    def archive_data(files):
        data = BytesIO()
        with ZipFile(data, "w") as bundle:
            for name, content in files.items():
                bundle.writestr(name, content)
        return data.getvalue()

    def add_artifact(self, name, target, files):
        body = self.archive_data(files)
        artifact_id = len(self.artifacts) + 1
        row = {"name": name, "id": artifact_id, "expired": False, "digest": f"sha256:{sha256(body).hexdigest()}",
               "created_at": self.available(target).isoformat(), "workflow_run": {
                   "id": 42, "head_branch": "main", "repository_id": 3, "head_repository_id": 3,
               }}
        self.artifacts[name] = (row, body)

    def read(self, url):
        if "?per_page=" in url:
            return json.dumps({"artifacts": [row for row, _ in self.artifacts.values()]}).encode()
        artifact_id = int(url.split("/")[-2])
        return next(body for row, body in self.artifacts.values() if row["id"] == artifact_id)

    def add_daily(self, target):
        report = MARKUP + f"<!-- {target} -->".encode()
        files = {name: b"fixture" for name in REPORT_FILES} | {"report.html": report}
        self.add_artifact(DAILY_PREFIX + str(target), target, files)

    def add_paper(self, target, outputs):
        directory = Path(outputs["paper_dir"])
        self.add_artifact(PAPER_PREFIX + str(target), target, {
            file.relative_to(directory).as_posix(): file.read_bytes() for file in directory.rglob("*") if file.is_file()
        })

    @staticmethod
    def verify_daily(directory, target):
        return RUN | {"trade_date": str(target), "report_sha256": sha256((directory / "report.html").read_bytes()).hexdigest()}

    @staticmethod
    def load_day(directory, target, symbols, *, position_policy, available_at):
        evidence = position_day(target)
        evidence["source"].update(
            report_sha256=PaperAutomationTests.verify_daily(directory, target)["report_sha256"],
            available_at=available_at.isoformat(),
        )
        return evidence

    def automate(self, workspace, day, *, enabled=True):
        return automate_iwb(self.root / workspace, self.archive, "a" * 40, scheduled=False, trade_date=day,
                            paper_enabled=enabled, paper_start_date=self.start, paper_policy_path=self.policy_path)

    def test_disabled_gate_initialization_restore_and_idempotent_second_day(self):
        self.add_daily(self.start)
        self.add_daily(self.second)
        with patch.dict("os.environ", {"US_IWB_PAPER_ENABLED": "false", "US_IWB_PAPER_START_DATE": str(self.start)}):
            enabled, _ = paper_workflow_variables()
        state, disabled = self.automate("disabled", self.start, enabled=enabled)
        self.assertEqual(state["status"], "REUSED_PUBLISHED_REPORT")
        self.assertFalse(any(key.startswith("paper") for key in disabled))
        first, outputs = self.automate("first", self.start)
        self.assertEqual(first["status"], "REUSED_PUBLISHED_REPORT", first)
        self.add_paper(self.start, outputs)
        second, outputs = self.automate("second", self.second)
        self.assertEqual(second["status"], "REUSED_PUBLISHED_REPORT", second)
        directory = Path(outputs["paper_dir"])
        self.assertEqual(outputs["paper_name"], PAPER_PREFIX + str(self.second))
        _, receipt, merged, _ = verify_bundle(directory, self.second)
        self.assertIn("前瞻单账户模拟跟踪".encode(), merged)
        evidence = json.loads((directory / "days" / f"{self.second}.json").read_bytes())
        self.assertEqual(evidence["body"]["previous_sha256"], first["paper"]["ledger_sha256"])
        self.add_paper(self.second, outputs)
        with patch("us_watchlist.app.iwb_paper_automation.replay_archive") as replay:
            reused, outputs = self.automate("reuse", self.second)
        replay.assert_not_called()
        self.assertTrue(reused["paper"]["reused"])
        self.assertNotIn("paper_dir", outputs)
        self.assertEqual(verify_bundle(Path(outputs["paper_bundle_dir"]), self.second)[1], receipt)

    def test_new_observation_publishes_separate_files_and_scheduled_reuse_skips_email(self):
        files = {name: b"fixture" for name in REPORT_FILES} | {"report.html": MARKUP}

        def observe(target, pool, directory, code_sha, *, require_yahoo_close):
            directory.mkdir(parents=True)
            for name, body in files.items():
                (directory / name).write_bytes(body)
            return self.verify_daily(directory, target) | {
                "yahoo_zip_sha256": "1" * 64, "holdings_csv_sha256": "2" * 64,
                "observed_at": self.available(target).isoformat(),
            }

        with (patch("us_watchlist.app.iwb_automation.observe_iwb", side_effect=observe),
              patch("us_watchlist.app.iwb_automation._prepare_pool"),
              patch("us_watchlist.app.iwb_automation.datetime", wraps=datetime) as clock):
            clock.now.return_value = self.available(self.start)
            state, outputs = self.automate("new", self.start)
        self.assertEqual(state["status"], RUN["status"], state)
        directory = Path(outputs["report_dir"])
        self.assertEqual({file.name: file.read_bytes() for file in directory.iterdir()}, files)
        self.assertNotEqual(outputs["report_dir"], outputs["paper_dir"])
        self.add_artifact(DAILY_PREFIX + str(self.start), self.start, files)
        self.add_paper(self.start, outputs)
        scheduled_at = self.available(self.start) + timedelta(minutes=15)
        with (patch.object(self.archive, "schedule_created_at", return_value=scheduled_at),
              patch("us_watchlist.app.iwb_automation.datetime", wraps=datetime) as clock):
            clock.now.return_value = scheduled_at
            state, outputs = automate_iwb(
                self.root / "scheduled", self.archive, "a" * 40, scheduled=True,
                paper_enabled=True, paper_start_date=self.start, paper_policy_path=self.policy_path,
            )
        self.assertEqual(state["status"], "REUSED_PUBLISHED_REPORT", state)
        self.assertTrue(state["paper"]["reused"])
        self.assertFalse({"paper_dir", "paper_bundle_dir", "email_report_dir"} & outputs.keys())

    def test_catchup_from_first_day_or_previous_bundle_and_missing_session(self):
        self.add_daily(self.start)
        self.add_daily(self.third)
        first, outputs = self.automate("first", self.start)
        self.assertEqual(first["status"], "REUSED_PUBLISHED_REPORT", first)
        missing, outputs = self.automate("missing", self.third)
        self.assertEqual(missing["status"], "FAILED")
        self.assertIn(f"PAPER_REQUIRED_DAILY_ARTIFACT_MISSING {self.second}", missing["error"])
        self.assertNotIn("paper_dir", outputs)
        self.add_daily(self.second)
        catchup, outputs = self.automate("catchup", self.third)
        self.assertEqual(catchup["status"], "REUSED_PUBLISHED_REPORT", catchup)
        self.assertEqual(len(list((Path(outputs["paper_dir"]) / "days").iterdir())), 3)
        # Same evidence and head when catching up from the most recent paper snapshot.
        self.add_paper(self.start, {"paper_dir": self.root / "first" / "paper_bundle"})
        from_bundle, _ = self.automate("from-bundle", self.third)
        self.assertEqual(from_bundle["paper"]["ledger_sha256"], catchup["paper"]["ledger_sha256"])

    def test_bundle_attachment_and_tampering_refuses_transport(self):
        self.add_daily(self.start)
        state, outputs = self.automate("daily", self.start)
        self.assertEqual(state["status"], "REUSED_PUBLISHED_REPORT", state)
        directory = Path(outputs["email_report_dir"])
        bundle = Path(outputs["paper_bundle_dir"])
        with (patch("us_watchlist.app.iwb_notifications.verify_completed", side_effect=self.verify_daily),
              patch("us_watchlist.app.iwb_notifications.send_mail") as send):
            send_iwb_email(directory, self.start, paper_bundle=bundle)
            _, plain, html, attachment, _ = send.call_args.args
            self.assertIn("单账户模拟持仓摘要", plain)
            self.assertIn("单账户模拟持仓摘要", html)
            self.assertIn("累计胜率", plain)
            self.assertIn(b'id="paper-research"', attachment)
            for filename, error in (("combined-report.html", "COMBINED_REPORT_SHA"), ("paper-summary.txt", "SUMMARY_SHA"),
                                    (f"days/{self.start}.json", "LEDGER_INTEGRITY_CONFLICT")):
                with self.subTest(filename=filename):
                    path = bundle / filename
                    original = path.read_bytes()
                    path.write_bytes(original.replace(b"fixture", b"tampered") if b"fixture" in original else original + b" ")
                    send.reset_mock()
                    with self.assertRaisesRegex(ValueError, error):
                        send_iwb_email(directory, self.start, paper_bundle=bundle)
                    send.assert_not_called()
                    path.write_bytes(original)

    def test_paper_zip_rejects_paths_digest_and_size_before_writing(self):
        fixed = {name: b"data" for name in ("study.json", "paper-receipt.json", "paper-summary.txt", "combined-report.html")}
        fixed[f"days/{self.start}.json"] = b"day"
        cases = [(fixed | {name: b"bad"}, 1024, False, "UNEXPECTED_ENTRIES") for name in (
            "../escaped", "/escaped", "days/../escaped", "C:/escaped",
        )]
        cases.extend(((fixed, 8, False, "UNEXPECTED_ENTRIES"), (fixed, 1024, True, "DIGEST_MISMATCH")))
        for files, limit, bad_digest, error in cases:
            with self.subTest(files=files.keys(), limit=limit, error=error):
                body = self.archive_data(files)
                digest = "bad" if bad_digest else f"sha256:{sha256(body).hexdigest()}"
                with (patch.object(self.archive, "_read", return_value=body),
                      patch("us_watchlist.integrations.github_artifacts.MAX_ARTIFACT_BYTES", limit),
                      self.assertRaisesRegex(ValueError, error)):
                    self.archive.restore_paper_bundle(Artifact("paper", 1, digest, 42), self.root / "bad")
                self.assertFalse((self.root / "bad").exists())
