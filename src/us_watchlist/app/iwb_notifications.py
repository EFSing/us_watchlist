"""Deliver only a verified B+C daily report, without re-evaluating its rules."""

from datetime import date
from pathlib import Path

from us_watchlist.app.iwb_daily import verify_completed
from us_watchlist.integrations.local_artifacts import read_artifact
from us_watchlist.integrations.report_metadata import read_core_candidates
from us_watchlist.integrations.smtp_mail import send_mail
from us_watchlist.reporting.iwb_email import render_email_summary


def send_iwb_email(directory: Path, target: date) -> None:
    report = verify_completed(directory, target)
    exact_html = read_artifact(directory / "report.html")
    subject, plain_body, html_body = render_email_summary(report, core=read_core_candidates(exact_html))
    send_mail(subject, plain_body, html_body, exact_html, f"美股研究日报_{target}.html")
