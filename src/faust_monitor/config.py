"""Runtime configuration loaded from CLI defaults and environment variables."""

from __future__ import annotations

from dataclasses import dataclass
import os


DEFAULT_SEARCH_URL = "https://www.entertix.ro/evenimente?s=faust"


@dataclass(frozen=True, slots=True)
class Config:
    search_url: str = DEFAULT_SEARCH_URL
    request_timeout_seconds: float = 15.0
    retry_limit: int = 3
    base_backoff_seconds: float = 1.0
    user_agent: str = "faust-ticket-monitor/0.1 (read-only hourly availability check)"
    github_repository: str | None = None
    github_token: str | None = None
    alert_assignee: str | None = None
    github_api_url: str = "https://api.github.com"

    @classmethod
    def from_env(cls, *, search_url: str | None = None) -> Config:
        repository = os.getenv("GITHUB_REPOSITORY") or None
        owner = repository.split("/", 1)[0] if repository and "/" in repository else None
        return cls(
            search_url=search_url or os.getenv("FAUST_SEARCH_URL", DEFAULT_SEARCH_URL),
            request_timeout_seconds=_env_float("REQUEST_TIMEOUT_SECONDS", 15.0),
            retry_limit=_env_int("REQUEST_RETRY_LIMIT", 3),
            base_backoff_seconds=_env_float("REQUEST_BACKOFF_SECONDS", 1.0),
            user_agent=os.getenv(
                "FAUST_MONITOR_USER_AGENT",
                "faust-ticket-monitor/0.1 (read-only hourly availability check)",
            ),
            github_repository=repository,
            github_token=os.getenv("GITHUB_TOKEN") or None,
            alert_assignee=os.getenv("ALERT_ASSIGNEE") or owner,
            github_api_url=os.getenv("GITHUB_API_URL", "https://api.github.com").rstrip("/"),
        )

    def require_github(self) -> None:
        if not self.github_repository:
            raise ValueError("GITHUB_REPOSITORY is required when notifications are enabled")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN is required when notifications are enabled")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = int(raw)
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = float(raw)
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value
