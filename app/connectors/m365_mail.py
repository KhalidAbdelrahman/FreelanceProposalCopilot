from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

PLATFORM_DOMAINS = {
    "Upwork": ("upwork.com", "upwork"),
    "Freelancer.com": ("freelancer.com", "freelancer"),
}
JOB_WORDS = ("job alert", "new job", "opportunity", "brief", "matches your", "project posted")
REPLY_WORDS = ("replied", "new message", "sent you a message", "response", "interview", "offer received", "client message")
URL_RE = re.compile(r"https?://[^\s<>\"']+")
TAG_RE = re.compile(r"<[^>]+>")


def _plain(body: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", body or ""))).strip()


def _platform(sender: str, body: str) -> str | None:
    h = f"{sender} {body}".lower()
    for platform, needles in PLATFORM_DOMAINS.items():
        if any(n in h for n in needles):
            return platform
    return None


def _platform_url(body: str, platform: str, fallback: str) -> str:
    host = PLATFORM_DOMAINS[platform][0]
    for raw in URL_RE.findall(body or ""):
        url = raw.rstrip(".,);]")
        if host in urlparse(url).netloc.lower():
            return url
    return fallback


class M365MailReader:
    """Delegated, read-only Microsoft Graph Mail.Read client."""

    def __init__(self) -> None:
        self.client_id = os.getenv("M365_CLIENT_ID", "").strip()
        self.tenant_id = os.getenv("M365_TENANT_ID", "common").strip()
        self.cache_path = Path(os.getenv("M365_TOKEN_CACHE", "data/msal_cache.json"))

    def _token(self, interactive: bool = False) -> str:
        direct = os.getenv("M365_ACCESS_TOKEN", "").strip()
        if direct:
            return direct
        if not self.client_id:
            return ""
        try:
            import msal
        except ImportError as exc:
            raise RuntimeError("Install requirements to use Microsoft 365 authentication.") from exc
        cache = msal.SerializableTokenCache()
        if self.cache_path.exists():
            cache.deserialize(self.cache_path.read_text(encoding="utf-8"))
        app = msal.PublicClientApplication(
            self.client_id,
            authority=f"https://login.microsoftonline.com/{self.tenant_id}",
            token_cache=cache,
        )
        result = None
        accounts = app.get_accounts()
        if accounts:
            result = app.acquire_token_silent(["Mail.Read"], account=accounts[0])
        if not result and interactive:
            flow = app.initiate_device_flow(scopes=["Mail.Read"])
            if "user_code" not in flow:
                raise RuntimeError(json.dumps(flow, indent=2))
            print(flow["message"])
            result = app.acquire_token_by_device_flow(flow)
        if cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(cache.serialize(), encoding="utf-8")
        return (result or {}).get("access_token", "")

    def authenticate(self) -> bool:
        return bool(self._token(interactive=True))

    def messages_since(self, since_iso: str | None = None) -> list[dict[str, Any]]:
        token = self._token(interactive=False)
        if not token:
            return []
        if not since_iso:
            since_iso = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        params = {
            "$filter": f"receivedDateTime ge {since_iso}",
            "$select": "id,subject,from,receivedDateTime,body,bodyPreview,webLink",
            "$orderby": "receivedDateTime desc",
            "$top": "100",
        }
        url = "https://graph.microsoft.com/v1.0/me/messages"
        headers = {"Authorization": f"Bearer {token}"}
        messages: list[dict[str, Any]] = []
        while url:
            r = requests.get(url, headers=headers, params=params if not messages else None, timeout=30)
            r.raise_for_status()
            payload = r.json()
            messages.extend(payload.get("value", []))
            url = payload.get("@odata.nextLink", "")
        return messages

    def classify(self, message: dict[str, Any]) -> dict[str, Any] | None:
        sender = (((message.get("from") or {}).get("emailAddress") or {}).get("address") or "")
        subject = message.get("subject") or ""
        html_body = ((message.get("body") or {}).get("content") or "")
        text = _plain(f"{subject} {html_body} {message.get('bodyPreview','')}")
        platform = _platform(sender, text)
        if not platform:
            return None
        lower = text.lower()
        kind = "reply" if any(w in lower for w in REPLY_WORDS) else "job" if any(w in lower for w in JOB_WORDS) else None
        if not kind:
            return None
        url = _platform_url(html_body, platform, message.get("webLink", ""))
        return {
            "kind": kind, "platform": platform, "external_id": message["id"],
            "title": subject or f"{platform} notification", "description": text[:5000],
            "subject": subject, "preview": message.get("bodyPreview", ""), "url": url,
            "source": "platform_email", "discovered_at": message.get("receivedDateTime"),
        }
