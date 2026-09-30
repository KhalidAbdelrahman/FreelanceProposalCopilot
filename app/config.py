from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


BASE_DIR = Path(__file__).resolve().parents[1]


def _load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


@dataclass
class Settings:
    db_path: Path
    public_base_url: str
    poll_seconds: int
    min_score: int
    max_proposal_words: int
    tracker_path: Path | None
    tone_profile_path: Path
    proposal_samples_dir: Path
    categories: dict[str, list[str]] = field(default_factory=dict)
    exclude_terms: list[str] = field(default_factory=list)
    freelancer_queries: list[str] = field(default_factory=list)
    browser_saved_searches: dict[str, list[str]] = field(default_factory=dict)
    enable_experimental_browser: bool = False


def load_settings(path: str | Path | None = None) -> Settings:
    config_path = Path(path or _env("FPC_CONFIG", str(BASE_DIR / "config.yaml")))
    if not config_path.exists():
        config_path = BASE_DIR / "config.example.yaml"
    raw: dict[str, Any] = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    tracker = _env("TRACKER_PATH", raw.get("tracker_path", ""))
    return Settings(
        db_path=_project_path(_env("DATABASE_PATH", raw.get("database_path", "data/copilot.db"))),
        public_base_url=_env("PUBLIC_BASE_URL", raw.get("public_base_url", "http://127.0.0.1:8765")).rstrip("/"),
        poll_seconds=int(_env("POLL_SECONDS", str(raw.get("poll_seconds", 60)))),
        min_score=int(_env("MIN_SCORE", str(raw.get("min_score", 55)))),
        max_proposal_words=int(raw.get("max_proposal_words", 150)),
        tracker_path=_project_path(tracker) if tracker else None,
        tone_profile_path=_project_path(raw.get("tone_profile_path", "tone_profile.yaml")),
        proposal_samples_dir=_project_path(raw.get("proposal_samples_dir", "data/past_proposals")),
        categories=raw.get("categories", {}),
        exclude_terms=raw.get("exclude_terms", []),
        freelancer_queries=raw.get("freelancer_queries", []),
        browser_saved_searches=raw.get("browser_saved_searches", {}),
        enable_experimental_browser=str(_env("ENABLE_EXPERIMENTAL_BROWSER", str(raw.get("enable_experimental_browser", False)))).lower() == "true",
    )
