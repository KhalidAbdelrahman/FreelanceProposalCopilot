from __future__ import annotations

import os
from typing import Any

import requests


def _post_slack(text: str) -> None:
    url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
    if url:
        r = requests.post(url, json={"text": text}, timeout=20)
        r.raise_for_status()


def _post_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if token and chat_id:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
            timeout=20,
        )
        r.raise_for_status()


def notify_with_errors(text: str) -> tuple[list[str], list[str]]:
    sent: list[str] = []
    errors: list[str] = []
    for name, fn in (("Slack", _post_slack), ("Telegram", _post_telegram)):
        try:
            before = bool(os.getenv("SLACK_WEBHOOK_URL" if name == "Slack" else "TELEGRAM_BOT_TOKEN", ""))
            fn(text)
            if before:
                sent.append(name)
        except Exception as exc:
            errors.append(f"{name} notification failed: {exc}")
    return sent, errors


def notify(text: str) -> list[str]:
    sent, errors = notify_with_errors(text)
    for error in errors:
        print(error)
    return sent


def draft_message(job: dict[str, Any], proposal: str, review_url: str) -> str:
    excerpt = proposal if len(proposal) <= 650 else proposal[:647] + "..."
    return (
        f"New {job['platform']} draft ({job.get('score', 0)}/100)\n"
        f"{job['title']}\n\n{excerpt}\n\nReview and approve: {review_url}\n"
        "Approval does not submit; you must open the platform and click Submit yourself."
    )


def reply_message(platform: str, subject: str, preview: str, url: str) -> str:
    return f"Client-response alert — {platform}\n{subject}\n{preview[:500]}\n{url}".strip()
