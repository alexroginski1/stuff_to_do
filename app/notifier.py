from __future__ import annotations

import logging
import os
import smtplib
import urllib.parse
from datetime import datetime, timedelta
from email.message import EmailMessage

logger = logging.getLogger(__name__)

_JOB_NAME = "stuff-to-do"


def _cloud_logging_link(run_started_at: datetime) -> str:
    """Build a Cloud Console Logs Explorer deep link scoped to this run."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    start = (run_started_at - timedelta(minutes=1)).isoformat()
    end = (run_started_at + timedelta(hours=1)).isoformat()
    query = (
        f'resource.type="cloud_run_job"\n'
        f'resource.labels.job_name="{_JOB_NAME}"\n'
        f'severity>=ERROR'
    )
    return (
        "https://console.cloud.google.com/logs/query;"
        f"query={urllib.parse.quote(query, safe='')};"
        f"timeRange={urllib.parse.quote(f'{start}/{end}', safe='')}"
        f"?project={urllib.parse.quote(project, safe='')}"
    )


def _issue_lines(issues: list[dict]) -> list[str]:
    return [f"- [{issue['calendar']}/{issue['source']}] {issue['message']}" for issue in issues]


def format_parsing_issues_email(issues: list[dict], run_started_at: datetime) -> tuple[str, str]:
    subject = f"Stuff To Do: {len(issues)} event(s) had parsing errors"
    lines = [
        f"{len(issues)} event(s) had errors during the {run_started_at:%Y-%m-%d %I:%M %p %Z} sync run:",
        "",
        *_issue_lines(issues),
        "",
        f"View logs: {_cloud_logging_link(run_started_at)}",
    ]
    return subject, "\n".join(lines)


def format_crash_email(issues: list[dict], traceback_text: str, run_started_at: datetime) -> tuple[str, str]:
    subject = "Stuff To Do: Cloud Run issue"
    lines = [
        f"The sync run starting {run_started_at:%Y-%m-%d %I:%M %p %Z} crashed before finishing:",
        "",
        traceback_text.rstrip(),
    ]
    if issues:
        lines += [
            "",
            f"{len(issues)} event(s) also had errors before the crash:",
            "",
            *_issue_lines(issues),
        ]
    lines += ["", f"View logs: {_cloud_logging_link(run_started_at)}"]
    return subject, "\n".join(lines)


def send_error_email(subject: str, body: str) -> None:
    sender = os.environ.get("GMAIL_SENDER_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("ALERT_EMAIL_TO", "roginskialexr@gmail.com")

    if not sender or not password:
        logger.error(
            f"GMAIL_SENDER_ADDRESS/GMAIL_APP_PASSWORD not configured; skipping alert email ({subject})"
        )
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = recipient
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(sender, password)
            smtp.send_message(msg)
        logger.info(f"Sent alert email: {subject}")
    except Exception as exc:
        logger.error(f"Failed to send alert email: {exc}", exc_info=True)
