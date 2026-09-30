from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from .style import build_style_prompt


BANNED_CLAIMS = (
    "guarantee", "guaranteed", "100%", "best in the world", "top rated",
)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", text))


def trim_to_words(text: str, maximum: int) -> str:
    words = text.strip().split()
    if len(words) <= maximum:
        return text.strip()
    return " ".join(words[:maximum]).strip()


def validate_proposal(text: str, maximum: int = 150) -> list[str]:
    issues: list[str] = []
    if word_count(text) > maximum:
        issues.append(f"Proposal is {word_count(text)} words; maximum is {maximum}.")
    question_count = text.count("?")
    if question_count == 0:
        issues.append("Proposal needs one clarifying question.")
    elif question_count > 1:
        issues.append("Proposal should contain exactly one clarifying question.")
    if any(term in text.lower() for term in BANNED_CLAIMS):
        issues.append("Proposal contains an unapproved absolute/promotional claim.")
    if "hardworking professional" in text.lower() or "looking forward to hearing" in text.lower():
        issues.append("Proposal contains playbook-prohibited filler.")
    return issues


def _job_detail(job: dict[str, Any]) -> str:
    title = re.sub(r"\s+", " ", str(job.get("title") or "your project")).strip()
    description = re.sub(r"\s+", " ", str(job.get("description") or "")).strip()
    if not description:
        return title
    first_sentence = re.split(r"(?<=[.!?])\s+", description, maxsplit=1)[0]
    detail = first_sentence[:180].rsplit(" ", 1)[0].strip(" ,.;:")
    return detail or title


def _question_for(category: str, description: str) -> str:
    lower = description.lower()
    if any(term in lower for term in ("website", "app", "figma", "wordpress", "shopify")):
        return "Which platform, existing assets, and single outcome should guide the first milestone?"
    if any(term in lower for term in ("video", "reel", "social media", "content")):
        return "Which audience and channel should the first deliverable be optimized for?"
    if any(term in lower for term in ("logo", "brand", "packaging", "interior", "design")):
        return "Which existing brand assets, dimensions, or references should I use as the starting point?"
    return f"What is the most important outcome for the first {category.lower() or 'project'} milestone?"


def _fallback(job: dict[str, Any], profile: dict[str, Any], maximum: int) -> str:
    detail = _job_detail(job)
    category = str(job.get("category") or "project").lower()
    description = re.sub(r"\s+", " ", str(job.get("description") or "")).strip()
    budget = str(job.get("budget_text") or "").strip()
    budget_line = f" I’ll keep the plan aligned with the announced {budget} budget." if budget else ""
    text = (
        f"Your brief highlights {detail}, so the first priority is to turn that requirement into a clear, usable result.\n\n"
        f"I would begin by confirming the current assets and success criteria, then break the {category} work into reviewable milestones with practical deliverables and a focused revision round.{budget_line}\n\n"
        f"Before I shape the first milestone, I’d confirm this: {_question_for(str(job.get('category') or 'project'), description)}"
    )
    return trim_to_words(text, maximum)


def draft_proposal(job: dict[str, Any], profile: dict[str, Any], samples: list[str], maximum: int = 150) -> str:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return _fallback(job, profile, maximum)

    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
    style = build_style_prompt(profile, samples)
    prompt = f"""Draft one freelance proposal in the writer's personal style.
    Hard requirements:
- Maximum {maximum} words.
- Use a specific detail from the job in the opening sentence, not a biography.
- Use only approved proof points from the style profile. If none fits, omit proof rather than inventing it.
- Structure the proposal as four short parts: observation, approach, deliverables/scope, and exactly one useful question.
- Mention the announced budget only as a constraint; do not invent a quote, timeline, portfolio result, or capability.
- Return plain text with short paragraphs, no subject line, markdown headings, placeholders, or unsupported claims.

STYLE PROFILE
{style}

JOB
Platform: {job.get('platform')}
Title: {job.get('title')}
Category: {job.get('category')}
Budget: {job.get('budget_text')}
Description:
{job.get('description','')[:7000]}
"""
    response = requests.post(
        f"{base}/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": model, "input": prompt},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload.get("output_text", "")
    if not text:
        chunks = []
        for item in payload.get("output", []):
            for part in item.get("content", []):
                if part.get("type") in ("output_text", "text"):
                    chunks.append(part.get("text", ""))
        text = "\n".join(chunks)
    text = text.strip().strip('"')
    if not text:
        return _fallback(job, profile, maximum)
    text = trim_to_words(text, maximum)
    return text if not validate_proposal(text, maximum) else _fallback(job, profile, maximum)
