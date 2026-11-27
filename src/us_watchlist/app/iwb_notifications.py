"""Deliver only a verified B+C daily report, without re-evaluating its rules."""

from datetime import date
from pathlib import Path

from us_watchlist.app.iwb_daily import verify_completed
from us_watchlist.integrations.local_artifacts import read_artifact
from us_watchlist.integrations.paper_bundle import verify_bundle
from us_watchlist.integrations.report_metadata import read_core_candidates
from us_watchlist.integrations.smtp_mail import send_mail
from us_watchlist.reporting.iwb_email import render_email_summary


def send_iwb_email(directory: Path, target: date, *, paper_bundle: Path | None = None) -> None:
    report = verify_completed(directory, target)
    exact_html = read_artifact(directory / "report.html")
    core = read_core_candidates(exact_html)
    summary = ""
    filename = f"美股研究日报_{target}.html"
    if paper_bundle is not None:
        _, _, exact_html, summary_bytes = verify_bundle(paper_bundle, target, report_sha256=report["report_sha256"])
        summary = summary_bytes.decode("utf-8")
        filename = f"美股研究日报_模拟持仓_{target}.html"
    subject, plain_body, html_body = render_email_summary(report, core=core, paper_summary=summary)
    send_mail(subject, plain_body, html_body, exact_html, filename)
