"""Notification transport and workflow branching, without sending live messages."""

import io
import json
import os
import smtplib
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from us_watchlist.app.iwb_notifications import send_iwb_email
from us_watchlist.domain.screening import B_SHAPE_V1, B_US_V2
from us_watchlist.integrations.smtp_mail import send_mail
from us_watchlist.reporting.iwb_email import render_email_summary

ROOT = Path(__file__).resolve().parents[1]
TARGET = date(2026, 11, 18)
RETIRED = "us_c_trend_pullback_conservative_b_v1"
SMTP = {
    "SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587", "SMTP_USERNAME": "example@gmail.com",
    "SMTP_PASSWORD": "application-password", "SMTP_FROM": "example@gmail.com",
    "SMTP_TO": "receiver@qq.com", "SMTP_USE_TLS": "true",
}
RUN = {
    "trade_date": TARGET.isoformat(), "status": "PARTIAL_COVERAGE", "base_equities": 1021,
    "listed_equities": 1020, "target_bars": 1020, "full_history_symbols": 994,
    "strategies": {
        B_SHAPE_V1: {"matches": 31},
        "us_c_trend_pullback_balanced_a_v1": {"matches": 3},
    },
}


class MailTests(unittest.TestCase):
    def test_v2_summary_uses_the_active_b_version(self):
        current = {**RUN, "strategies": {**RUN["strategies"], B_US_V2: {"matches": 51}}}
        v2_only = {**current, "strategies": {version: row for version, row in current["strategies"].items()
                                             if version != B_SHAPE_V1}}
        self.assertEqual(render_email_summary(v2_only), render_email_summary(current))
        _, plain, html = render_email_summary(current)
        self.assertIn("B 美股突破回踩 V2：51 只", plain)
        self.assertIn("51 只</td>", html)

    def test_two_rule_and_historical_three_rule_receipts_have_the_same_summary(self):
        legacy = {**RUN, "strategies": {**RUN["strategies"], RETIRED: {"matches": 1}}}
        current = render_email_summary(RUN)
        self.assertEqual(render_email_summary(legacy), current)
        for part in current[1:]:
            self.assertIn("C 均衡", part)
            self.assertNotIn("C 保守", part)

    def test_chinese_summary_and_exact_html_attachment(self):
        report_html = "<!doctype html><html lang='zh'><body>参考止损与量能</body></html>"
        with patch("us_watchlist.integrations.smtp_mail.smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {}
            send_mail(*render_email_summary(RUN), report_html.encode(), "美股研究日报_2026-11-18.html", SMTP)
        message = smtp.return_value.__enter__.return_value.send_message.call_args.args[0]
        self.assertIn("2026-11-18", message["Subject"])
        self.assertIn("部分覆盖", message["Subject"])
        text_part, html_part, attachment = (
            part for part in message.walk() if part.get_content_maintype() != "multipart"
        )
        self.assertEqual(text_part.get_content_type(), "text/plain")
        self.assertIn("B 突破回踩：31 只", text_part.get_content())
        self.assertIn("C 均衡：3 只", text_part.get_content())
        self.assertIn("120 日完整历史：994/1,020", text_part.get_content())
        self.assertEqual(html_part.get_content_type(), "text/html")
        self.assertIn("部分覆盖", html_part.get_content())
        self.assertEqual(attachment.get_filename(), "美股研究日报_2026-11-18.html")
        self.assertEqual(attachment.get_payload(decode=True), report_html.encode("utf-8"))
        self.assertEqual(attachment.get_content_charset(), "utf-8")
        self.assertEqual(attachment.get_content_disposition(), "attachment")

    def test_complete_status_is_not_marked_partial(self):
        subject, _, _ = render_email_summary({**RUN, "status": "SUCCESS"})
        self.assertIn("｜完成", subject)

    def test_core_summary_is_read_from_the_verified_attachment(self):
        html = ('<article data-core-symbol="AHR" data-core-name="美国医疗地产" '
                'data-core-sector="房地产/REITs"></article>').encode("utf-8")
        with (patch("us_watchlist.app.iwb_notifications.verify_completed", return_value=RUN),
              patch("us_watchlist.app.iwb_notifications.read_artifact", return_value=html),
              patch("us_watchlist.app.iwb_notifications.send_mail") as deliver):
            send_iwb_email(Path("/fake/workbench"), TARGET)
        for part in deliver.call_args.args[1:3]:
            self.assertIn("AHR（美国医疗地产 · 房地产/REITs）", part)
        self.assertEqual(deliver.call_args.args[3], html)

    def test_legacy_published_report_without_history_coverage_is_emailed(self):
        legacy = {key: value for key, value in RUN.items() if key != "full_history_symbols"}
        html = b"<!doctype html><html><body>Original archived report</body></html>"
        directory = Path("/fake/legacy-archive")
        with (patch("us_watchlist.app.iwb_notifications.verify_completed", return_value=legacy),
              patch("us_watchlist.app.iwb_notifications.read_artifact", return_value=html),
              patch("us_watchlist.app.iwb_notifications.send_mail") as deliver):
            send_iwb_email(directory, TARGET)
        self.assertIn("旧版归档未记录", deliver.call_args.args[1])
        self.assertIn("旧版归档未记录", deliver.call_args.args[2])
        self.assertEqual(deliver.call_args.args[3], html)

    def test_smtp_uses_existing_gmail_to_qq_secrets_with_starttls(self):
        with patch("us_watchlist.integrations.smtp_mail.smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {}
            send_mail("研究日报", "正文", "<p>正文</p>", "<h1>报告</h1>".encode(), "daily.html", SMTP)
        smtp.assert_called_once_with("smtp.gmail.com", 587, timeout=20)
        connection = smtp.return_value.__enter__.return_value
        connection.starttls.assert_called_once_with()
        connection.login.assert_called_once_with("example@gmail.com", "application-password")
        message = connection.send_message.call_args.args[0]
        self.assertEqual(message["From"], "example@gmail.com")
        self.assertEqual(message["To"], "receiver@qq.com")

    def test_missing_secrets_and_recipient_rejection_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "IWB_SMTP_NOT_CONFIGURED"):
            send_mail("x", "x", "x", b"x", "x.html", {})
        with self.assertRaisesRegex(ValueError, "IWB_SMTP_REQUIRES_STARTTLS"):
            send_mail("x", "x", "x", b"x", "x.html", {**SMTP, "SMTP_USE_TLS": "false"})
        with patch("us_watchlist.integrations.smtp_mail.smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value.send_message.return_value = {"x@qq.com": "Rejected"}
            with self.assertRaisesRegex(ValueError, "IWB_SMTP_RECIPIENT_REFUSED"):
                send_mail("x", "x", "x", b"x", "x.html", SMTP)
        with patch("us_watchlist.integrations.smtp_mail.smtplib.SMTP") as smtp:
            smtp.return_value.__enter__.return_value.login.side_effect = smtplib.SMTPAuthenticationError(535, b"No")
            with self.assertRaisesRegex(ValueError, "IWB_SMTP_AUTH_FAILED"):
                send_mail("x", "x", "x", b"x", "x.html", SMTP)

    def test_only_verified_reports_reach_transport(self):
        directory = Path("/fake/archive")
        with (patch("us_watchlist.app.iwb_notifications.verify_completed", return_value=RUN) as verify,
              patch("us_watchlist.app.iwb_notifications.read_artifact", return_value=b"<h1>report</h1>"),
              patch("us_watchlist.app.iwb_notifications.send_mail") as deliver):
            send_iwb_email(directory, TARGET)
        verify.assert_called_once_with(directory, TARGET)
        self.assertIn(b"report", deliver.call_args.args[3])
        with (patch("us_watchlist.app.iwb_notifications.verify_completed", side_effect=ValueError("BAD_REPORT")),
              patch("us_watchlist.app.iwb_notifications.send_mail") as deliver):
            with self.assertRaisesRegex(ValueError, "BAD_REPORT"):
                send_iwb_email(directory, TARGET)
            deliver.assert_not_called()


class WorkflowTests(unittest.TestCase):
    def test_email_only_after_publish_and_bark_only_after_failure(self):
        workflow = (ROOT / ".github/workflows/iwb-daily.yml").read_text(encoding="utf-8")
        self.assertIn("steps.daily.outputs.email_report_dir != ''", workflow)
        self.assertIn("success() && steps.daily.outputs.email_report_dir", workflow)
        self.assertIn("needs.daily.result == 'failure'", workflow)
        self.assertIn("BARK_ENDPOINT: ${{ secrets.BARK_ENDPOINT }}", workflow)
        self.assertIn("SMTP_PASSWORD: ${{ secrets.SMTP_PASSWORD }}", workflow)
        self.assertIn("iwb-email --directory", workflow)

    def test_bark_payload_is_sent_only_through_the_failure_step(self):
        workflow = (ROOT / ".github/workflows/iwb-daily.yml").read_text(encoding="utf-8")
        raw = workflow.split("python3 - <<'PY'\n", 1)[1].split("\n          PY", 1)[0]
        script = "\n".join(line.removeprefix("          ") for line in raw.splitlines())
        compiled = compile(script, "iwb-bark-step", "exec")
        env = {
            "BARK_ENDPOINT": "https://example.test/bark-key", "IWB_TRADE_DATE": "2026-11-18",
            "IWB_REPORT_STATUS": "FAILED", "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "example/project", "GITHUB_RUN_ID": "42",
        }
        with (patch.dict(os.environ, env), patch("urllib.request.urlopen") as send,
              redirect_stdout(io.StringIO()) as captured):
            send.return_value.__enter__.return_value.read.return_value = b'{"code":200}'
            exec(compiled, {"__name__": "__main__"})
        request = send.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(payload["url"], "https://github.com/example/project/actions/runs/42")
        self.assertIn("FAILED", payload["body"])
        self.assertIn("IWB_BARK_SENT", captured.getvalue())


if __name__ == "__main__":
    unittest.main()
