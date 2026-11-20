import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from us_watchlist.app.iwb_paper import run_study
from us_watchlist.app.paper_inputs import _screening, load_day
from us_watchlist.domain.paper import BASIS, B_VERSION, STRATEGIES, Mode, Status, check_policy
from us_watchlist.domain.replay_research import VOLUME_FIELDS
from us_watchlist.integrations.paper_archive import read_report_records
from us_watchlist.integrations.xnys import next_session

START = date(2026, 1, 5)
T1 = date(2026, 1, 6)
T2 = date(2026, 1, 7)
T3 = date(2026, 1, 8)
_, BALANCED, CONSERVATIVE = list(STRATEGIES)
RULE = {"min_actual_rr": "2", "min_target_upside": "0.05", "max_open_premium": "0.08", "exit_model": "FIXED_STOP"}
POLICY = {
    B_VERSION: {"B_NUMERIC_QUALIFIED:UNKNOWN": RULE},
    BALANCED: {"C_PRICE_RESEARCH:CLEAR": RULE},
    CONSERVATIVE: {"C_PRICE_RESEARCH:CLEAR": {**RULE, "min_target_upside": "0.18"}},
}
SIGNAL_BAR = ("100", "104", "96", "101")


def candidate(symbol, strategy=B_VERSION, *, rejected=False, warning="UNKNOWN"):
    qualification = "C_PRICE_RESEARCH" if strategy != B_VERSION else (
        "B_NUMERIC_REJECTED" if rejected else "B_NUMERIC_QUALIFIED"
    )
    return {
        "symbol": symbol, "strategy_version": strategy, "matched": True, "qualification": qualification,
        "qualification_reason": None, "risk_warning": warning, "structure": {"stage": "W2_TO_W3_TRANSITION_PROXY"},
        "volume": [{"field": field, "value": "1"} for field in VOLUME_FIELDS],
        "levels": {"trigger": "100", "stop": "95", "target": "120", "entry": "100", "rr": "4", "target_rule": "TEST"},
        "reference_missing_reason": None,
    }


def evidence(day, candidates=(), *, bars=None, prior=None):
    bars = bars or {}
    prior = prior or {}
    symbols = set(bars) | set(prior) | {plan["symbol"] for plan in candidates}
    return {
        "trade_date": str(day), "opens_at": f"{day}T14:30:00+00:00", "next_session": str(next_session(day)),
        "source": {
            "observed_at": f"{day}T22:00:00+00:00", "report_id": f"synthetic-{day}", "report_sha256": "a" * 64,
            "input_sha256": sha256(str(day).encode()).hexdigest(), "research_version": "synthetic-research",
        },
        "candidates": list(candidates),
        "quotes": {
            symbol: {
                "current": list(bars.get(symbol, SIGNAL_BAR)) if bars.get(symbol, True) is not None else None,
                "previous": list(prior.get(symbol, SIGNAL_BAR)) if prior.get(symbol, True) is not None else None,
                "diagnostic": "YAHOO_SPLIT_BASIS_UNVERIFIED" if bars.get(symbol, True) is None else "",
                "structures": {B_VERSION: "W2_TO_W3_TRANSITION_PROXY", BALANCED: "C_CLOSE_REBOUND_CONFIRMED"},
            }
            for symbol in sorted(symbols)
        },
    }


def demo_days():
    first = evidence(START, (
        candidate("ALFA"), candidate("BRAV", BALANCED, warning="CLEAR"),
        candidate("CHAR", BALANCED, warning="WARNING"), candidate("DELT", rejected=True),
        candidate("ECHO"), candidate("FOXT"), candidate("GOLF"), candidate("HOTL"),
        candidate("INDI", CONSERVATIVE, warning="CLEAR"), candidate("JULI"),
    ))
    second = evidence(T1, bars={
        "ALFA": ("100", "114", "98", "105"), "BRAV": ("101", "113", "98", "107"),
        "CHAR": SIGNAL_BAR, "DELT": SIGNAL_BAR, "ECHO": ("97", "125", "96", "108"),
        "FOXT": ("95", "101", "92", "96"), "GOLF": ("120", "124", "119", "122"),
        "HOTL": ("108", "110", "101", "103"), "INDI": ("104", "108", "100", "105"),
        "JULI": ("109", "111", "99", "107"),
    })
    third = evidence(T2, bars={
        "ALFA": ("102", "130", "93", "122"), "BRAV": ("110", "122", "109", "121"),
    }, prior={symbol: second["quotes"][symbol]["current"] for symbol in ("ALFA", "BRAV")})
    fourth = evidence(T3, bars={"BRAV": ("90", "120", "85", "111")}, prior={"BRAV": third["quotes"]["BRAV"]["current"]})
    return first, second, third, fourth


def run_day(root, day, *, policy=POLICY, **options):
    def load(symbols):
        if symbols - day["quotes"].keys():
            raise AssertionError("Synthetic archive missing quote evidence")
        return day

    return run_study(
        root, Mode.SYNTHETIC, START, date.fromisoformat(day["trade_date"]), policy,
        evidence_loader=load, **options,
    )


class PaperTests(unittest.TestCase):
    def setUp(self):
        root = Path(".runtime/tmp")
        root.mkdir(parents=True, exist_ok=True)
        temp = TemporaryDirectory(dir=root)
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    @staticmethod
    def by_symbol(view):
        return {row["plan"]["symbol"]: row for row in view["records"].values()}

    def test_full_lifecycle_and_all_open_checks(self):
        first, second, third, fourth = demo_days()
        output, t = run_day(self.root, first, initialize=True)
        self.assertEqual({row["status"] for row in t["records"].values()}, {Status.PENDING})
        self.assertIn("当前模拟持仓 0 只", (output / "paper-report.html").read_text(encoding="utf-8"))
        self.assertIn("当前模拟持仓 0 只", (output / "paper-email.txt").read_text(encoding="utf-8"))

        output, t1 = run_day(self.root, second, expect_previous=t["ledger_sha256"])
        rows = self.by_symbol(t1)
        for symbol, reason in {
            "CHAR": "COHORT_NOT_ENABLED", "DELT": "COHORT_NOT_ENABLED", "ECHO": "OPEN_BELOW_TRIGGER",
            "FOXT": "OPEN_AT_OR_BELOW_STOP", "GOLF": "OPEN_AT_OR_ABOVE_TARGET",
            "HOTL": "RR_BELOW_CONFIGURED_MINIMUM", "INDI": "TARGET_UPSIDE_BELOW_CONFIGURED_MINIMUM",
            "JULI": "OPEN_ABOVE_CONFIGURED_PREMIUM",
        }.items():
            with self.subTest(symbol=symbol):
                self.assertEqual(rows[symbol]["status"], Status.NOT_FILLED)
                self.assertEqual(rows[symbol]["history"][-1]["reason"], reason)
                self.assertIsNone(rows[symbol]["position"])
        self.assertEqual(rows["ALFA"]["position"]["r"], "1")
        self.assertEqual(rows["ALFA"]["position"]["mfe_r"], "2.8")
        self.assertEqual(rows["ALFA"]["position"]["mae_r"], "-0.4")
        self.assertEqual(rows["ALFA"]["position"]["initial_rr"], "4")
        self.assertEqual(rows["ALFA"]["position"]["units"], 1)
        self.assertIn("当前模拟持仓 2 只", (output / "paper-report.html").read_text(encoding="utf-8"))
        self.assertTrue(all(stat["win_rate"] is None for stat in t1["performance"]))

        output, t2 = run_day(self.root, third)
        rows = self.by_symbol(t2)
        self.assertEqual(rows["ALFA"]["status"], Status.CLOSED)
        self.assertEqual(rows["ALFA"]["position"]["exit_price"], "95")
        self.assertEqual(rows["ALFA"]["position"]["r"], "-1")
        self.assertEqual(rows["ALFA"]["position"]["mfe_r"], "2.8")
        self.assertEqual(rows["ALFA"]["position"]["mae_r"], "-1")
        self.assertFalse(rows["ALFA"]["position"]["target_seen"])
        self.assertEqual(rows["BRAV"]["position"]["priced_on"], str(T2))
        self.assertTrue(rows["BRAV"]["position"]["target_seen"])
        self.assertEqual(rows["BRAV"]["status"], Status.OPEN)
        self.assertIn("当前模拟持仓 1 只", (output / "paper-report.html").read_text(encoding="utf-8"))
        b_stat, c_stat, *_ = t2["performance"]
        self.assertEqual((b_stat["win_rate"], b_stat[Status.CLOSED], b_stat["mean_r"]), (0, 1, -1))
        self.assertEqual((c_stat[Status.OPEN], c_stat["total_r"]), (1, 0))
        _, t3 = run_day(self.root, fourth)
        state = self.by_symbol(t3)["BRAV"]["position"]
        self.assertEqual((state["exit_reason"], state["exit_price"], state["r"][:7]),
                         ("GAP_THROUGH_STOP", "90", "-1.8333"))

    def test_entry_day_stop_is_sequenced_after_open(self):
        day = evidence(START, (candidate("ALFA"), candidate("ALFA", BALANCED, warning="CLEAR")))
        run_day(self.root, day, initialize=True)
        _, view = run_day(self.root, evidence(T1, bars={"ALFA": ("100", "125", "90", "120")}))
        self.assertEqual(len(view["records"]), 2)
        for row in view["records"].values():
            self.assertEqual([event["status"] for event in row["history"]], [Status.PENDING, Status.OPEN, Status.CLOSED])
            self.assertEqual((row["position"]["mfe_r"], row["position"]["mae_r"]), ("0", "-1"))
        self.assertEqual({row["plan"]["risk_warning"] for row in view["records"].values()}, {"CLEAR", "UNKNOWN"})

    def test_legacy_r_protection_is_causal_and_only_realizes_on_exit(self):
        rule = {**RULE, "exit_model": "LEGACY_R_PROTECTION"}
        policy = {B_VERSION: {"B_NUMERIC_QUALIFIED:UNKNOWN": rule}}
        run_day(self.root, evidence(START, (candidate("ALFA"),)), initialize=True, policy=policy)
        day = ("100", "111", "98", "108")
        _, raised = run_day(self.root, evidence(T1, bars={"ALFA": day}), policy=policy)
        row = self.by_symbol(raised)["ALFA"]
        self.assertEqual((row["position"]["stop"], row["history"][-1]["reason"]),
                         ("106.0", "STOP_RAISED_FOR_NEXT_SESSION"))
        self.assertIsNone(raised["performance"][0]["win_rate"])
        second = ("109", "115", "108", "109")
        _, pending = run_day(self.root, evidence(T2, bars={"ALFA": second}, prior={"ALFA": day}), policy=policy)
        row = self.by_symbol(pending)["ALFA"]
        self.assertTrue(row["position"]["exit_next_open"])
        self.assertEqual(row["history"][-1]["reason"], "PROFIT_PROTECTION_ARMED")
        _, ended = run_day(self.root, evidence(T3, bars={"ALFA": ("108", "125", "90", "110")},
                                              prior={"ALFA": second}), policy=policy)
        final = self.by_symbol(ended)["ALFA"]["position"]
        self.assertEqual((final["exit_reason"], final["exit_price"], final["mfe_r"]),
                         ("PROFIT_PROTECTION_NEXT_OPEN", "108", "3"))
        self.assertEqual(ended["performance"][0]["win_rate"], 1)
        self.assertEqual(str(ended["performance"][0]["total_r"]), "1.6")

    def test_missing_next_bar_delayed_signal_and_price_basis_conflict(self):
        first = evidence(START, (candidate("ALFA"), candidate("BRAV"), candidate("CHAR")))
        first["source"]["observed_at"] = str(T1) + "T14:30:00+00:00"
        run_day(self.root, first, initialize=True)
        _, view = run_day(self.root, evidence(T1, bars={symbol: SIGNAL_BAR for symbol in ("ALFA", "BRAV", "CHAR")}))
        self.assertTrue(all(row["history"][-1]["reason"] == "SIGNAL_NOT_KNOWN_BEFORE_T1_OPEN"
                            for row in view["records"].values()))

        first = evidence(START, (candidate("ALFA"), candidate("BRAV"), candidate("CHAR")))
        root = self.root / "timely"
        run_day(root, first, initialize=True)
        _, view = run_day(root, evidence(T1, bars={"ALFA": None, "CHAR": SIGNAL_BAR},
                                       prior={"BRAV": ("90", "91", "89", "90"), "CHAR": None}))
        rows = self.by_symbol(view)
        self.assertEqual(rows["ALFA"]["history"][-1]["reason"], "MISSING_OR_SPLIT_UNVERIFIED_YAHOO_BAR")
        self.assertEqual(rows["ALFA"]["history"][-1]["diagnostic"], "YAHOO_SPLIT_BASIS_UNVERIFIED")
        self.assertEqual(rows["BRAV"]["history"][-1]["reason"], "PRIOR_PRICE_BASIS_CHANGED")
        self.assertEqual(rows["CHAR"]["status"], Status.UNAVAILABLE)
        _, later = run_day(root, evidence(T2))
        self.assertEqual(view["records"], later["records"])

    def test_open_gap_retains_price_and_freezes_until_chain_recovery(self):
        run_day(self.root, evidence(START, (candidate("ALFA"),)), initialize=True)
        _, first = run_day(self.root, evidence(T1, bars={"ALFA": SIGNAL_BAR}))
        _, missing = run_day(self.root, evidence(T2, bars={"ALFA": None}))
        _, later = run_day(self.root, evidence(T3, bars={"ALFA": ("80", "84", "70", "73")}))
        last = self.by_symbol(later)["ALFA"]
        self.assertEqual(last["position"], self.by_symbol(first)["ALFA"]["position"])
        self.assertEqual(last["status"], Status.OPEN)
        self.assertEqual(last["suspended_at"], str(T2))
        self.assertEqual(self.by_symbol(missing)["ALFA"]["history"][-1]["observation"], Status.UNAVAILABLE)
        self.assertEqual(last["history"][-1]["reason"], "UNRESOLVED_PRIOR_GAP")

    def test_idempotence_state_conflict_and_missing_day_fail_closed(self):
        first, second, third, _ = demo_days()
        first_path, view = run_day(self.root, first, initialize=True)
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = list(workers.map(lambda _: run_day(self.root, second), range(2)))
        output, t1 = results[0]
        self.assertEqual(t1, results[1][1])
        original = (output / "day.json").read_bytes()
        (output / "paper-report.html").unlink()
        self.assertEqual(run_study(self.root, Mode.SYNTHETIC, START, T1, POLICY)[1], t1)
        changed = deepcopy(second)
        changed["source"]["report_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "identity already used"):
            run_day(self.root, changed)
        self.assertEqual((output / "day.json").read_bytes(), original)
        with self.assertRaisesRegex(ValueError, "PAPER_EXPECTED_PREDECESSOR_MISMATCH"):
            run_day(self.root, second, expect_previous="0" * 64)
        with self.assertRaisesRegex(ValueError, "PAPER_PROSPECTIVE_DISABLED"):
            run_study(self.root, Mode.PROSPECTIVE, START, T1, POLICY)
        with self.assertRaises(OSError):
            run_study(self.root, Mode.HISTORICAL_REPLAY, START, T1, POLICY)
        (first_path / "day.json").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "PAPER_LEDGER_DAY_MISSING"):
            run_day(self.root, third)
        self.assertEqual(run_day(self.root, first, initialize=True)[1], view)
        (output / "day.json").write_bytes(original.replace(b"synthetic-2026", b"corrupted-2026"))
        with self.assertRaisesRegex(ValueError, "PAPER_LEDGER_INTEGRITY_CONFLICT"):
            run_day(self.root, third)

    def test_evidence_only_no_t1_fill_and_no_cross_mode_restore(self):
        _, view = run_day(self.root, evidence(START, (candidate("ALFA"),)), initialize=True, policy={})
        _, t1 = run_day(self.root, evidence(T1, bars={"ALFA": SIGNAL_BAR}), policy={})
        plan = self.by_symbol(view)["ALFA"]["plan"]
        row = self.by_symbol(t1)["ALFA"]
        self.assertEqual(plan["simulation_eligibility"], "POLICY_UNSET")
        self.assertEqual((row["status"], row["history"][-1]["actual_rr"]), (Status.UNAVAILABLE, "4"))
        self.assertEqual(next_session(date(2025, 11, 26)), date(2025, 11, 28))
        with self.assertRaisesRegex(ValueError, "PAPER_UNKNOWN_POLICY_COHORT"):
            check_policy({B_VERSION: {"C_PRICE_RESEARCH:CLEAR": RULE}})

    def test_archive_hash_and_duplicate_records_are_rejected(self):
        html = f'<script type="application/json" data-strategy="{B_VERSION}">{{}}</script>'.encode()
        with self.assertRaisesRegex(ValueError, "PAPER_REPORT_SHA_MISMATCH"):
            read_report_records(html, "0" * 64)
        with self.assertRaisesRegex(ValueError, "PAPER_DUPLICATE_REPORT_RECORD"):
            read_report_records(html * 2, sha256(html * 2).hexdigest())
        with patch("us_watchlist.app.paper_inputs.verify_completed", side_effect=ValueError("archive conflict")):
            with self.assertRaisesRegex(ValueError, "archive conflict"):
                load_day(self.root, START, set())
        self.assertFalse(list(self.root.iterdir()))

    def test_screening_and_reference_records_must_agree(self):
        fields = {"trade_date": str(START), "cutoff": f"{START}T22:00:00+00:00", "manifest_sha256": "test-sha",
                  "mode": "iwb_yahoo_observation"}
        run = {"trade_date": str(START), "observed_at": fields["cutoff"], "input_sha256": fields["manifest_sha256"],
               "strategies": {version: {"matches": 0} for version in STRATEGIES}}
        records = {version: {**fields, "schema": "us_offline_screening_v1", "version": version, "error": None,
                             "evaluations": [{"symbol": "ALFA", "matched": False, "reason": "NO_MATCH"}]}
                   for version in STRATEGIES}
        records["record-research"] = {**fields, "price_basis": BASIS, "candidates": []}
        self.assertEqual(_screening(run, records, ("ALFA",))[0], [])
        records[B_VERSION]["evaluations"][0]["matched"] = True
        with self.assertRaisesRegex(ValueError, "PAPER_SCREENING_COUNT_MISMATCH"):
            _screening(run, records, ("ALFA",))
        run["strategies"][B_VERSION]["matches"] = 1
        with self.assertRaisesRegex(ValueError, "PAPER_RESEARCH_MATCH_SET_MISMATCH"):
            _screening(run, records, ("ALFA",))
