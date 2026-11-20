"""SMTP transport for the private US research report."""

import os
import smtplib
from email.message import EmailMessage
from typing import Mapping


def send_mail(
    subject: str, plain_body: str, html_body: str, report_html: bytes,
    attachment_filename: str, environ: Mapping[str, str] | None = None,
) -> None:
    """Deliver one message with the same SMTP_* settings as the existing daily report."""

    values = os.environ if environ is None else environ
    required = ("SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_TO")
    missing = [name for name in required if not values.get(name, "").strip()]
    if missing:
        raise ValueError(f"IWB_SMTP_NOT_CONFIGURED {','.join(missing)}")
    try:
        port = int(values.get("SMTP_PORT", "").strip() or "587")
    except ValueError:
        raise ValueError("IWB_SMTP_INVALID_PORT") from None
    if not 1 <= port <= 65535:
        raise ValueError("IWB_SMTP_INVALID_PORT")
    use_tls = values.get("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no"}
    if not use_tls:
        raise ValueError("IWB_SMTP_REQUIRES_STARTTLS")

    recipients = [address.strip() for address in values["SMTP_TO"].split(",") if address.strip()]
    if not recipients:
        raise ValueError("IWB_SMTP_NOT_CONFIGURED SMTP_TO")
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = values["SMTP_FROM"].strip()
    message["To"] = ", ".join(recipients)
    message.set_content(plain_body)
    message.add_alternative(html_body, subtype="html")
    message.add_attachment(report_html, maintype="text", subtype="html",
                           filename=attachment_filename, params={"charset": "utf-8"})

    try:
        with smtplib.SMTP(values["SMTP_HOST"], port, timeout=20) as server:
            server.starttls()
            server.login(values["SMTP_USERNAME"], values["SMTP_PASSWORD"])
            refused = server.send_message(message)
            if refused:
                raise ValueError("IWB_SMTP_RECIPIENT_REFUSED")
    except smtplib.SMTPAuthenticationError:
        raise ValueError("IWB_SMTP_AUTH_FAILED") from None
    except (smtplib.SMTPException, OSError) as error:
        raise ValueError(f"IWB_SMTP_DELIVERY_FAILED {type(error).__name__}") from None
