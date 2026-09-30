from pathlib import Path

import pytest

from app.config import BASE_DIR, Settings, _project_path
from app.db import connect, session, upsert_job, create_draft
from app.drafting import draft_proposal, validate_proposal, word_count
from app.connectors.m365_mail import PLATFORM_DOMAINS
from app.main import _clarification_confirmed
from app.notifier import notify_with_errors
from app.scoring import score_job
from app.tracker import HEADERS


def test_proposal_guardrails():
    good = "Your Shopify migration needs URL mapping before design starts. I would inventory redirects, validate product data, and test the checkout path in milestones. Which SEO pages must retain their current rankings at launch?"
    assert word_count(good) < 150
    assert validate_proposal(good) == []
    assert validate_proposal("I am a hardworking professional.")


def test_fallback_draft_adapts_question_to_job_type(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    proposal = draft_proposal(
        {
            "title": "Modern E-Commerce Candle Website",
            "description": "Finish the Shopify product pages and improve the mobile checkout experience.",
            "category": "Web Development",
            "budget_text": "250–750 USD",
        },
        {},
        [],
    )
    assert "Shopify product pages" in proposal
    assert "announced 250–750 USD budget" in proposal
    assert "\n\n" in proposal
    assert proposal.count("?") == 1
    assert validate_proposal(proposal) == []


def test_database_review_states(tmp_path: Path):
    db = tmp_path / "test.db"
    connect(db).close()
    with session(db) as conn:
        job_id, created = upsert_job(conn, {"platform":"Upwork","external_id":"1","title":"Test","description":"Detailed job","url":"https://example.com","source":"test"})
        assert created
        draft_id = create_draft(conn, job_id, "What outcome matters most?")
        row = conn.execute("SELECT status,reviewer_certified FROM drafts WHERE id=?", (draft_id,)).fetchone()
        assert row["status"] == "PENDING_REVIEW"
        assert row["reviewer_certified"] == 0


def test_initial_platform_scope():
    assert set(PLATFORM_DOMAINS) == {"Upwork", "Freelancer.com"}


def test_project_paths_are_stable_from_any_working_directory():
    assert _project_path("data/copilot.db") == BASE_DIR / "data/copilot.db"
    assert _project_path("/tmp/copilot.db") == Path("/tmp/copilot.db")


def test_score_counts_relevant_terms_across_categories():
    settings = Settings(
        db_path=Path("data/test.db"),
        public_base_url="http://127.0.0.1:8765",
        poll_seconds=60,
        min_score=55,
        max_proposal_words=150,
        tracker_path=None,
        tone_profile_path=Path("tone_profile.yaml"),
        proposal_samples_dir=Path("data/past_proposals"),
        categories={"Branding": ["brand identity"], "Content": ["product video", "social media campaign"]},
        exclude_terms=[],
    )
    score, reasons, category = score_job(
        {
            "platform": "Freelancer.com",
            "title": "Brand identity and product video",
            "description": "Need a brand identity and product video for a social media campaign with clear goals.",
            "budget_text": "$500-$900",
        },
        settings,
    )
    assert score >= settings.min_score
    assert category == "Content"
    assert any("Matched Content" in reason for reason in reasons)


def test_manual_submission_requires_clarification_confirmation():
    assert _clarification_confirmed({"clarification_checked": "yes"})
    assert not _clarification_confirmed({})


def test_notification_errors_are_reported(monkeypatch):
    monkeypatch.setenv("SLACK_WEBHOOK_URL", "https://example.test/webhook")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)

    def fail(_text):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("app.notifier._post_slack", fail)
    sent, errors = notify_with_errors("test")
    assert sent == []
    assert errors == ["Slack notification failed: network unavailable"]


def test_no_platform_submit_implementation():
    root = Path(__file__).parents[1] / "app"
    code = "\n".join(p.read_text(encoding="utf-8") for p in root.rglob("*.py"))
    forbidden = ["place_project_bid(", "submit_proposal(", "click('submit')", 'click("submit")']
    assert not any(token in code.lower() for token in forbidden)
