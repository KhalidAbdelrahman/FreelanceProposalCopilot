from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any

from .config import Settings
from .connectors.freelancer import FreelancerDiscovery
from .connectors.m365_mail import M365MailReader
from .db import create_draft, get_state, session, set_state, upsert_job, utcnow
from .drafting import draft_proposal
from .notifier import draft_message, notify_with_errors, reply_message
from .scoring import score_job
from .style import load_profile


def _process_job(settings: Settings, conn, raw: dict[str, Any], errors: list[str]) -> tuple[int | None, bool]:
    score, reasons, category = score_job(raw, settings)
    raw.update(score=score, score_reasons=reasons, category=category)
    job_id, created = upsert_job(conn, raw)
    if not created or score < settings.min_score:
        return None, created
    profile, samples = load_profile(settings.tone_profile_path, settings.proposal_samples_dir)
    proposal = draft_proposal(raw, profile, samples, settings.max_proposal_words)
    draft_id = create_draft(conn, job_id, proposal)
    review_url = f"{settings.public_base_url}/review/{draft_id}"
    _, notification_errors = notify_with_errors(draft_message(raw, proposal, review_url))
    errors.extend(notification_errors)
    return draft_id, True


def run_cycle(settings: Settings) -> dict[str, Any]:
    summary: dict[str, Any] = {"new_jobs": 0, "drafts": 0, "reply_alerts": 0, "errors": []}
    raw_jobs: list[dict[str, Any]] = []

    if settings.freelancer_queries:
        try:
            raw_jobs.extend(FreelancerDiscovery().discover(settings.freelancer_queries))
        except Exception as exc:
            summary["errors"].append(f"Freelancer API: {exc}")

    mail = M365MailReader()
    try:
        with session(settings.db_path) as conn:
            since = get_state(conn, "mail_since", "")
        messages = mail.messages_since(since or None)
        newest = since
        for message in messages:
            received = message.get("receivedDateTime") or ""
            if received > newest:
                newest = received
            item = mail.classify(message)
            if not item:
                continue
            if item["kind"] == "job":
                item["external_id"] = "mail-" + hashlib.sha256(item["external_id"].encode()).hexdigest()[:24]
                raw_jobs.append(item)
            else:
                with session(settings.db_path) as conn:
                    exists = conn.execute("SELECT 1 FROM alerts WHERE external_id=?", (item["external_id"],)).fetchone()
                    if not exists:
                        conn.execute(
                            "INSERT INTO alerts(external_id,platform,subject,preview,url,received_at,notified_at) VALUES(?,?,?,?,?,?,?)",
                            (item["external_id"], item["platform"], item["subject"], item["preview"], item["url"], item.get("discovered_at") or utcnow(), utcnow()),
                        )
                        _, notification_errors = notify_with_errors(
                            reply_message(item["platform"], item["subject"], item["preview"], item["url"])
                        )
                        summary["errors"].extend(notification_errors)
                        summary["reply_alerts"] += 1
        if newest:
            with session(settings.db_path) as conn:
                set_state(conn, "mail_since", newest)
    except Exception as exc:
        summary["errors"].append(f"Microsoft 365 mail: {exc}")

    with session(settings.db_path) as conn:
        for raw in raw_jobs:
            try:
                draft_id, created = _process_job(settings, conn, raw, summary["errors"])
                summary["new_jobs"] += int(created)
                summary["drafts"] += int(draft_id is not None)
            except Exception as exc:
                summary["errors"].append(f"{raw.get('platform')} / {raw.get('title')}: {exc}")
    return summary
