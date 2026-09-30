from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_RULES = {
    "name": "Amgad",
    "positioning": "AI-powered web and brand systems for local service businesses",
    "max_words": 150,
    "rules": [
        "Open with one concrete detail from the client's project, never a biography.",
        "Use one relevant, truthful proof point only; never invent metrics or clients.",
        "Give a short two- or three-sentence approach.",
        "End with one smart clarifying question.",
        "Avoid filler, generic enthusiasm, and 'I am a hardworking professional'.",
        "Use a concise, consultative, confident tone.",
    ],
    "approved_proof_points": [],
}


def load_profile(path: Path, samples_dir: Path) -> tuple[dict[str, Any], list[str]]:
    profile = DEFAULT_RULES.copy()
    if path.exists():
        profile.update(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    samples: list[str] = []
    if samples_dir.exists():
        for p in sorted(samples_dir.glob("*.txt")):
            text = p.read_text(encoding="utf-8").strip()
            if text:
                samples.append(text[:5000])
    return profile, samples


def build_style_prompt(profile: dict[str, Any], samples: list[str]) -> str:
    rules = "\n".join(f"- {r}" for r in profile.get("rules", []))
    proofs = "\n".join(f"- {p}" for p in profile.get("approved_proof_points", [])) or "- None supplied; do not invent proof."
    examples = "\n\n---\n\n".join(samples[-8:]) or "No past submitted proposal samples have been imported yet."
    return f"""Writer: {profile.get('name', 'Amgad')}
Positioning: {profile.get('positioning', '')}
Rules:
{rules}
Approved proof points (only these may be stated as facts):
{proofs}
Past submitted proposal samples:
{examples}
"""
