from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse


class ReadOnlyBrowserDiscovery:
    """Opt-in, foreground-only discovery. It never clicks Apply/Submit or fills forms.

    This adapter is deliberately not used by the scheduler. Upwork explicitly warns that
    unapproved page-reading/monitoring tools can trigger enforcement. Use only where the
    relevant platform has approved the behavior in writing.
    """

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.profile_dir = Path(os.getenv("BROWSER_PROFILE_DIR", "data/browser-profile"))

    def discover_foreground(self, platform: str, urls: list[str]) -> list[dict[str, Any]]:
        if not self.enabled:
            raise RuntimeError("Experimental browser discovery is disabled by default.")
        from playwright.sync_api import sync_playwright

        if platform != "upwork":
            raise ValueError("Initial build supports only the Upwork browser-reader experiment.")
        host, paths = "upwork.com", ["/jobs/~", "/freelance-jobs/apply/"]
        jobs: list[dict[str, Any]] = []
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(str(self.profile_dir), headless=False)
            page = context.pages[0] if context.pages else context.new_page()
            for search_url in urls:
                if host not in urlparse(search_url).netloc.lower():
                    continue
                page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(3000)
                for a in page.locator("a[href]").all():
                    href = a.get_attribute("href") or ""
                    if not any(path in href for path in paths):
                        continue
                    full = urljoin(search_url, href)
                    title = (a.inner_text(timeout=1000) or "").strip()
                    if len(title) < 8:
                        continue
                    jobs.append({
                        "platform": "Upwork",
                        "external_id": hashlib.sha256(full.encode()).hexdigest()[:24],
                        "title": title[:300], "description": title, "url": full,
                        "budget_text": "", "source": "experimental_read_only_browser",
                    })
                time.sleep(8)
            context.close()
        return list({j["external_id"]: j for j in jobs}.values())
