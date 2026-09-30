from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any

import requests


class FreelancerDiscovery:
    """Read-only project discovery through Freelancer.com's official API."""

    def __init__(self) -> None:
        self.base = os.getenv("FREELANCER_API_BASE", "https://www.freelancer.com/api").rstrip("/")
        self.token = os.getenv("FREELANCER_OAUTH_TOKEN", "").strip()

    def discover(self, queries: list[str], limit_each: int = 20) -> list[dict[str, Any]]:
        if not self.token:
            raise RuntimeError("Set FREELANCER_OAUTH_TOKEN from the official Freelancer developer portal.")
        jobs: list[dict[str, Any]] = []
        headers = {"freelancer-oauth-v1": self.token}
        for query in queries:
            params = {
                "query": query,
                "limit": min(limit_each, 100),
                "full_description": "true",
                "job_details": "true",
                "sort_field": "submitdate",
                "sort_direction": "desc",
                "compact": "true",
            }
            r = requests.get(
                f"{self.base}/projects/0.1/projects/active/",
                headers=headers,
                params=params,
                timeout=30,
            )
            r.raise_for_status()
            result = r.json().get("result", {})
            for p in result.get("projects", []):
                pid = str(p.get("id") or hashlib.sha256(str(p).encode()).hexdigest()[:20])
                currency = (p.get("currency") or {}).get("code", "")
                budget = p.get("budget") or {}
                if budget:
                    budget_text = f"{budget.get('minimum','')}–{budget.get('maximum','')} {currency}".strip()
                else:
                    budget_text = ""
                jobs.append({
                    "platform": "Freelancer.com",
                    "external_id": pid,
                    "title": p.get("title") or "Untitled project",
                    "description": p.get("description") or p.get("preview_description") or "",
                    "url": f"https://www.freelancer.com/projects/{pid}",
                    "budget_text": budget_text,
                    "source": "official_api",
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                })
        unique: dict[str, dict[str, Any]] = {}
        for job in jobs:
            unique[job["external_id"]] = job
        return list(unique.values())
