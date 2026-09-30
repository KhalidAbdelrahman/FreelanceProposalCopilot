from __future__ import annotations

from typing import Any

from .config import Settings

try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 0
except ImportError:
    detect = None


ALLOWED_LANGUAGES = {"en", "ar"}


def _is_allowed_language(text: str) -> bool:
    if detect is None:
        return True
    sample = text.strip()
    if not sample:
        return True
    try:
        lang = detect(sample[:500])
    except Exception:
        return True
    return lang in ALLOWED_LANGUAGES


def score_job(job: dict[str, Any], settings: Settings) -> tuple[int, list[str], str]:
    haystack = f"{job.get('title','')} {job.get('description','')}".lower()
    reasons: list[str] = []
    if not _is_allowed_language(f"{job.get('title','')} {job.get('description','')}"):
        return 0, ["Language not English/Arabic"], "Other"
    if any(term.lower() in haystack for term in settings.exclude_terms):
        return 0, ["Excluded term matched"], "Other"

    best_category = "Other"
    best_hits: list[str] = []
    all_hits: list[str] = []
    for category, terms in settings.categories.items():
        hits = [term for term in terms if term.lower() in haystack]
        all_hits.extend(hits)
        if len(hits) > len(best_hits):
            best_category, best_hits = category, hits

    score = min(70, len(all_hits) * 18)
    if best_hits:
        reasons.append(f"Matched {best_category}: {', '.join(best_hits[:4])}")
    description_len = len(job.get("description", ""))
    if description_len >= 250:
        score += 12
        reasons.append("Detailed brief")
    if job.get("budget_text"):
        score += 10
        reasons.append("Budget supplied")
    if job.get("platform") == "Freelancer.com":
        score += 5
        reasons.append("Official API source")
    return min(score, 100), reasons, best_category
