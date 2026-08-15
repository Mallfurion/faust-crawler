"""GitHub Issues backed alert state and transition handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import re
from typing import Any, Iterable
from urllib.parse import urlencode

from .config import Config
from .models import AvailabilityResult, AvailabilityStatus
from .transport import HttpTransport, TransportError


MONITOR_LABEL = "faust-ticket-monitor"
MONITOR_LABEL_COLOR = "b60205"
MAX_ISSUE_ASSIGNEES = 10
EVENT_MARKER_RE = re.compile(r"<!--\s*faust-monitor:event-id=(\d+)\s*-->")
DATE_MARKER_RE = re.compile(
    r"<!--\s*faust-monitor:performance-date=(\d{4}-\d{2}-\d{2})\s*-->"
)


class GitHubIssueError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MonitorIssue:
    number: int
    title: str
    body: str
    state: str
    assignees: tuple[str, ...] = ()

    @property
    def event_id(self) -> str | None:
        match = EVENT_MARKER_RE.search(self.body)
        return match.group(1) if match else None

    @property
    def performance_date(self) -> date | None:
        match = DATE_MARKER_RE.search(self.body)
        return date.fromisoformat(match.group(1)) if match else None


class GitHubIssuesApi:
    def __init__(
        self,
        transport: HttpTransport,
        *,
        api_url: str,
        repository: str,
        token: str,
    ) -> None:
        if repository.count("/") != 1:
            raise ValueError("GitHub repository must use owner/name format")
        self.transport = transport
        self.base_url = f"{api_url.rstrip('/')}/repos/{repository}"
        self.token = token

    def ensure_monitor_label(self) -> None:
        labels = self._request_json("GET", f"{self.base_url}/labels?per_page=100")
        if not isinstance(labels, list):
            raise GitHubIssueError("GitHub labels response was not a list")
        if any(
            isinstance(item, dict) and item.get("name") == MONITOR_LABEL
            for item in labels
        ):
            return
        self._request_json(
            "POST",
            f"{self.base_url}/labels",
            {"name": MONITOR_LABEL, "color": MONITOR_LABEL_COLOR},
        )

    def list_assignable_users(self) -> tuple[str, ...]:
        """Return every user GitHub says can be assigned in this repository."""
        logins: list[str] = []
        page = 1
        while True:
            payload = self._request_json(
                "GET", f"{self.base_url}/assignees?per_page=100&page={page}"
            )
            if not isinstance(payload, list):
                raise GitHubIssueError("GitHub assignees response was not a list")
            for item in payload:
                if not isinstance(item, dict) or not isinstance(item.get("login"), str):
                    raise GitHubIssueError(
                        "GitHub assignees response omitted a user login"
                    )
                logins.append(item["login"])
            if len(payload) < 100:
                break
            page += 1

        unique_logins = tuple(dict.fromkeys(logins))
        if not unique_logins:
            raise GitHubIssueError("GitHub reported no assignable users")
        if len(unique_logins) > MAX_ISSUE_ASSIGNEES:
            raise GitHubIssueError(
                f"GitHub reported {len(unique_logins)} assignable users, but issues "
                f"support at most {MAX_ISSUE_ASSIGNEES} assignees"
            )
        return unique_logins

    def list_monitor_issues(self) -> list[MonitorIssue]:
        issues: list[MonitorIssue] = []
        page = 1
        while True:
            query = urlencode(
                {
                    "state": "all",
                    "labels": MONITOR_LABEL,
                    "per_page": "100",
                    "page": str(page),
                }
            )
            payload = self._request_json(
                "GET", f"{self.base_url}/issues?{query}"
            )
            if not isinstance(payload, list):
                raise GitHubIssueError("GitHub issues response was not a list")
            for item in payload:
                if not isinstance(item, dict) or "pull_request" in item:
                    continue
                try:
                    issues.append(
                        MonitorIssue(
                            number=int(item["number"]),
                            title=str(item.get("title", "")),
                            body=str(item.get("body") or ""),
                            state=str(item["state"]),
                        )
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise GitHubIssueError(
                        "GitHub issue response omitted required fields"
                    ) from error
            if len(payload) < 100:
                break
            page += 1
        return issues

    def create_issue(
        self,
        *,
        title: str,
        body: str,
        assignees: tuple[str, ...],
    ) -> MonitorIssue:
        request: dict[str, Any] = {
            "title": title,
            "body": body,
            "labels": [MONITOR_LABEL],
        }
        request["assignees"] = list(assignees)
        payload = self._request_json("POST", f"{self.base_url}/issues", request)
        return _issue_from_payload(payload)

    def update_issue(self, number: int, **fields: Any) -> MonitorIssue:
        payload = self._request_json(
            "PATCH", f"{self.base_url}/issues/{number}", fields
        )
        return _issue_from_payload(payload)

    def add_comment(self, number: int, body: str) -> None:
        self._request_json(
            "POST",
            f"{self.base_url}/issues/{number}/comments",
            {"body": body},
        )

    def _request_json(
        self,
        method: str,
        url: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        try:
            response = self.transport.request(
                url,
                method=method,
                body=body,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            return response.json()
        except (TransportError, json.JSONDecodeError, UnicodeError) as error:
            raise GitHubIssueError(f"GitHub API {method} failed for {url}: {error}") from error


class GitHubIssueNotifier:
    def __init__(
        self,
        api: GitHubIssuesApi,
        *,
        today: date | None = None,
    ) -> None:
        self.api = api
        self.today = today or date.today()

    @classmethod
    def from_config(cls, config: Config) -> GitHubIssueNotifier:
        config.require_github()
        assert config.github_repository is not None
        assert config.github_token is not None
        transport = HttpTransport(
            timeout_seconds=config.request_timeout_seconds,
            # Mutating requests are not automatically retried because a lost
            # response could otherwise create duplicate issues or comments.
            retry_limit=0,
            backoff_seconds=config.base_backoff_seconds,
            user_agent=config.user_agent,
        )
        api = GitHubIssuesApi(
            transport,
            api_url=config.github_api_url,
            repository=config.github_repository,
            token=config.github_token,
        )
        return cls(api)

    def reconcile(self, results: Iterable[AvailabilityResult]) -> None:
        result_list = list(results)
        known_results = [
            result
            for result in result_list
            if result.status is not AvailabilityStatus.UNKNOWN
        ]
        if not known_results:
            return

        assignees = (
            self.api.list_assignable_users()
            if any(
                result.status is AvailabilityStatus.AVAILABLE
                for result in known_results
            )
            else ()
        )
        self.api.ensure_monitor_label()
        issues = self.api.list_monitor_issues()
        by_event_id: dict[str, MonitorIssue] = {}
        for issue in issues:
            event_id = issue.event_id
            if not event_id:
                continue
            if event_id in by_event_id:
                raise GitHubIssueError(
                    f"Multiple {MONITOR_LABEL} issues exist for event {event_id}"
                )
            by_event_id[event_id] = issue

        seen_event_ids = {result.performance.event_id for result in result_list}
        for result in known_results:
            event_id = result.performance.event_id
            issue = by_event_id.get(event_id)
            if result.status is AvailabilityStatus.AVAILABLE:
                by_event_id[event_id] = self._ensure_available(
                    result, issue, assignees
                )
            elif issue and issue.state == "open":
                by_event_id[event_id] = self.api.update_issue(
                    issue.number,
                    state="closed",
                    state_reason="completed",
                )

        for event_id, issue in by_event_id.items():
            if event_id in seen_event_ids or issue.state != "open":
                continue
            performance_date = issue.performance_date
            if performance_date and performance_date < self.today:
                self.api.update_issue(
                    issue.number,
                    state="closed",
                    state_reason="completed",
                )

    def _ensure_available(
        self,
        result: AvailabilityResult,
        issue: MonitorIssue | None,
        assignees: tuple[str, ...],
    ) -> MonitorIssue:
        title = _issue_title(result)
        body = _issue_body(result)
        if issue is None:
            return self.api.create_issue(
                title=title,
                body=body,
                assignees=assignees,
            )

        if issue.state == "closed":
            self.api.add_comment(issue.number, _reappearance_comment(result))
            fields: dict[str, Any] = {
                "state": "open",
                "title": title,
                "body": body,
            }
            fields["assignees"] = list(assignees)
            return self.api.update_issue(issue.number, **fields)

        if (
            issue.title != title
            or issue.body != body
            or _normalized_logins(issue.assignees) != _normalized_logins(assignees)
        ):
            fields = {"title": title, "body": body}
            fields["assignees"] = list(assignees)
            return self.api.update_issue(issue.number, **fields)
        return issue


def _issue_title(result: AvailabilityResult) -> str:
    performance = result.performance
    performance_date = (
        performance.performance_date.isoformat()
        if performance.performance_date
        else "date unknown"
    )
    return (
        f"[Faust tickets] {performance_date}: "
        f"{result.available_seats} selectable seat(s)"
    )


def _issue_body(result: AvailabilityResult) -> str:
    performance = result.performance
    performance_date = (
        performance.performance_date.isoformat()
        if performance.performance_date
        else "unknown"
    )
    return "\n".join(
        [
            f"<!-- faust-monitor:event-id={performance.event_id} -->",
            f"<!-- faust-monitor:performance-date={performance_date} -->",
            "## Faust tickets are available",
            "",
            f"- **Performance date:** {performance_date}",
            f"- **Selectable seats:** {result.available_seats}",
            f"- **Total mapped seats:** {result.total_seats}",
            f"- **Entertix event ID:** {performance.event_id}",
            "",
            f"[Open the Entertix ticket-selection page]({performance.ticket_url})",
            "",
            "This issue is managed automatically by the read-only Faust ticket monitor.",
        ]
    )


def _reappearance_comment(result: AvailabilityResult) -> str:
    return "\n".join(
        [
            "## Tickets are available again",
            "",
            f"Selectable seats: **{result.available_seats}**",
            "",
            f"[Open the Entertix ticket-selection page]({result.performance.ticket_url})",
        ]
    )


def _issue_from_payload(payload: Any) -> MonitorIssue:
    if not isinstance(payload, dict):
        raise GitHubIssueError("GitHub issue response was not an object")
    try:
        return MonitorIssue(
            number=int(payload["number"]),
            title=str(payload.get("title", "")),
            body=str(payload.get("body") or ""),
            state=str(payload["state"]),
            assignees=tuple(
                str(item["login"])
                for item in payload.get("assignees", [])
                if isinstance(item, dict) and "login" in item
            ),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise GitHubIssueError("GitHub issue response omitted required fields") from error


def _normalized_logins(logins: Iterable[str]) -> frozenset[str]:
    return frozenset(login.casefold() for login in logins)
