from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs

import markdown
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from .config import BASE_DIR, load_settings
from .db import connect, session, utcnow
from .drafting import validate_proposal, word_count
from .services import run_cycle
from .tracker import append_submission

app = FastAPI(title="Freelance Proposal Copilot", version="1.0.0")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))


def render_markdown(value: str) -> Markup:
    rendered = markdown.markdown(value or "", extensions=["extra", "sane_lists", "nl2br"])
    return Markup(rendered)


templates.env.filters["markdown"] = render_markdown
settings = load_settings()
_stop = threading.Event()


def _form(body: bytes) -> dict[str, str]:
    return {k: v[-1] for k, v in parse_qs(body.decode("utf-8"), keep_blank_values=True).items()}


def _clarification_confirmed(data: dict[str, str]) -> bool:
    return data.get("clarification_checked") == "yes"


def _worker() -> None:
    while not _stop.is_set():
        try:
            print("cycle", json.dumps(run_cycle(settings)))
        except Exception as exc:
            print("cycle failed", exc)
        _stop.wait(settings.poll_seconds)


@app.on_event("startup")
def startup() -> None:
    connect(settings.db_path).close()
    if os.getenv("DISABLE_BACKGROUND_WORKER", "false").lower() != "true":
        threading.Thread(target=_worker, name="discovery-worker", daemon=True).start()


@app.on_event("shutdown")
def shutdown() -> None:
    _stop.set()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with session(settings.db_path) as conn:
        opportunities = conn.execute(
            """SELECT j.*,d.id AS draft_id,d.status AS draft_status
               FROM jobs j LEFT JOIN drafts d ON d.job_id=j.id
               ORDER BY j.score DESC,j.discovered_at DESC LIMIT 100"""
        ).fetchall()
        alerts = conn.execute("SELECT * FROM alerts ORDER BY received_at DESC LIMIT 25").fetchall()
    return templates.TemplateResponse(request, "home.html", {"opportunities": opportunities, "alerts": alerts})


@app.get("/review/{draft_id}", response_class=HTMLResponse)
def review(request: Request, draft_id: int):
    with session(settings.db_path) as conn:
        row = conn.execute(
            """SELECT d.*,j.platform,j.title,j.description,j.url,j.score,j.score_reasons,j.budget_text,j.category,j.discovered_at
               FROM drafts d JOIN jobs j ON j.id=d.job_id WHERE d.id=?""", (draft_id,)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Draft not found")
    issues = validate_proposal(row["proposal"], settings.max_proposal_words)
    return templates.TemplateResponse(request, "review.html", {"draft": row, "issues": issues, "word_count": word_count(row["proposal"])})


@app.post("/review/{draft_id}/approve")
async def approve(draft_id: int, request: Request):
    data = _form(await request.body())
    proposal = data.get("proposal", "").strip()
    if data.get("certify") != "yes":
        raise HTTPException(400, "You must certify that you personally reviewed the proposal.")
    issues = validate_proposal(proposal, settings.max_proposal_words)
    if issues:
        raise HTTPException(422, " ".join(issues))
    with session(settings.db_path) as conn:
        cur = conn.execute(
            "UPDATE drafts SET proposal=?,status='APPROVED',reviewer_certified=1,reviewed_at=? WHERE id=? AND status IN ('PENDING_REVIEW','APPROVED')",
            (proposal, utcnow(), draft_id),
        )
        if cur.rowcount != 1:
            raise HTTPException(409, "Draft cannot be approved from its current state.")
    return RedirectResponse(f"/review/{draft_id}", status_code=303)


@app.post("/review/{draft_id}/reject")
async def reject(draft_id: int, request: Request):
    data = _form(await request.body())
    with session(settings.db_path) as conn:
        conn.execute("UPDATE drafts SET status='REJECTED',notes=?,reviewed_at=? WHERE id=?", (data.get("notes", ""), utcnow(), draft_id))
    return RedirectResponse("/", status_code=303)


@app.post("/review/{draft_id}/record-submitted")
async def record_submitted(draft_id: int, request: Request):
    data = _form(await request.body())
    with session(settings.db_path) as conn:
        row = conn.execute(
            """SELECT d.*,j.platform,j.title,j.url,j.category,j.budget_text,j.discovered_at
               FROM drafts d JOIN jobs j ON j.id=d.job_id WHERE d.id=?""", (draft_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Draft not found")
        if row["status"] != "APPROVED" or not row["reviewer_certified"]:
            raise HTTPException(409, "Approve the personally reviewed draft before recording manual submission.")
        if not _clarification_confirmed(data):
            raise HTTPException(400, "Confirm that you reviewed and answered the proposal's clarifying question.")
        tracker_row = None
        if settings.tracker_path:
            tracker_row = append_submission(settings.tracker_path, dict(row), data.get("notes", ""), int(data.get("bid_units", "0") or 0))
        conn.execute(
            "UPDATE drafts SET status='RECORDED_SUBMITTED',submitted_at=?,notes=? WHERE id=?",
            (utcnow(), data.get("notes", ""), draft_id),
        )
    suffix = f"?tracker_row={tracker_row}" if tracker_row else ""
    return RedirectResponse(f"/review/{draft_id}{suffix}", status_code=303)


@app.post("/run")
def run_now():
    return run_cycle(settings)


@app.get("/health")
def health():
    return {"ok": True, "safety": "human-review-required; no platform submit operation exists"}
