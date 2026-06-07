from __future__ import annotations

import html
import smtplib
from email.message import EmailMessage
from typing import Any

from backend.config import get_settings


SESSION_LABELS = {
    "pre_market": "盤前分析選股",
    "market_hours": "盤中模擬交易",
    "post_market": "盤後結算",
}


def _recipients(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]


def _markdown_to_html(markdown: str, title: str) -> str:
    parts: list[str] = []
    in_list = False
    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()
        escaped = html.escape(line)
        if escaped.startswith("- "):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{escaped[2:]}</li>")
            continue
        if in_list:
            parts.append("</ul>")
            in_list = False
        if escaped.startswith("# "):
            parts.append(f"<h1>{escaped[2:]}</h1>")
        elif escaped.startswith("## "):
            parts.append(f"<h2>{escaped[3:]}</h2>")
        elif escaped.startswith("### "):
            parts.append(f"<h3>{escaped[4:]}</h3>")
        elif not escaped:
            parts.append("<br>")
        else:
            parts.append(f"<p>{escaped}</p>")
    if in_list:
        parts.append("</ul>")
    body = "\n".join(parts)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <style>
    body {{ font-family: "Noto Sans TC", "Microsoft JhengHei", Arial, sans-serif; line-height: 1.65; color: #172026; }}
    h1 {{ font-size: 24px; }}
    h2 {{ font-size: 18px; border-left: 4px solid #0f766e; padding-left: 10px; margin-top: 22px; }}
    h3 {{ font-size: 16px; color: #0f766e; }}
    p, li {{ font-size: 14px; }}
  </style>
  <title>{html.escape(title)}</title>
</head>
<body>
{body}
</body>
</html>"""


def _email_configured() -> tuple[bool, str, int, str, str, str, list[str]]:
    settings = get_settings()
    sender = settings.report_email_from or settings.smtp_user
    recipients = _recipients(settings.report_email_to)
    configured = bool(settings.smtp_host and sender and recipients)
    return configured, settings.smtp_host, settings.smtp_port, settings.smtp_user, settings.smtp_password, sender, recipients


def send_potential_stock_report_email(report_session: str, report: Any) -> dict[str, Any]:
    settings = get_settings()
    configured, smtp_host, smtp_port, smtp_user, smtp_password, sender, recipients = _email_configured()
    if not settings.send_cron_email:
        return {"sent": False, "reason": "SEND_CRON_EMAIL is disabled."}
    if not configured:
        return {"sent": False, "reason": "SMTP_HOST, sender, or REPORT_EMAIL_TO is not configured."}

    label = SESSION_LABELS.get(report_session, report_session)
    stance = getattr(report, "market_stance", "") or "無市場結論"
    total_value = getattr(getattr(report, "portfolio", None), "total_value", None)
    subject = f"潛力股工具｜{label}｜{stance}"
    if total_value is not None:
        subject += f"｜淨值 NT${total_value:,.0f}"

    markdown = getattr(report, "markdown", "") or ""
    if not markdown:
        markdown = f"# {label}\n\n本次排程已完成，但沒有產生 Markdown 報告。"
    html_body = _markdown_to_html(markdown, subject)

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg.set_content(markdown)
    msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.ehlo()
            if settings.smtp_starttls:
                smtp.starttls()
                smtp.ehlo()
            if smtp_user and smtp_password:
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        return {"sent": False, "reason": f"Email delivery failed: {exc}"}

    return {"sent": True, "recipients": recipients, "subject": subject}
