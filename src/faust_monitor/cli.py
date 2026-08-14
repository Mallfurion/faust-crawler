"""Command-line orchestration for monitoring and reporting."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Sequence

from .config import Config
from .entertix import EntertixClient, EntertixParseError
from .models import AvailabilityResult, AvailabilityStatus, Diagnostic
from .reporting import render_markdown, report_document, write_json_report
from .transport import HttpTransport, TransportError


@dataclass(frozen=True, slots=True)
class RunOutcome:
    results: tuple[AvailabilityResult, ...]
    global_diagnostic: Diagnostic | None = None

    @property
    def failed(self) -> bool:
        return self.global_diagnostic is not None or any(
            result.status is AvailabilityStatus.UNKNOWN for result in self.results
        )


def build_transport(config: Config) -> HttpTransport:
    return HttpTransport(
        timeout_seconds=config.request_timeout_seconds,
        retry_limit=config.retry_limit,
        backoff_seconds=config.base_backoff_seconds,
        user_agent=config.user_agent,
    )


def run_monitor(config: Config, *, client: EntertixClient | None = None) -> RunOutcome:
    active_client = client or EntertixClient(build_transport(config), config.search_url)
    try:
        return RunOutcome(tuple(active_client.monitor()))
    except (TransportError, EntertixParseError) as error:
        return RunOutcome(
            (),
            Diagnostic(
                stage="discovery",
                message=str(error),
                retryable=getattr(error, "retryable", False),
            ),
        )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check availability without creating or updating GitHub Issues",
    )
    parser.add_argument(
        "--search-url",
        help="override the Entertix Faust search URL",
    )
    parser.add_argument(
        "--json-output",
        default="monitor-report.json",
        help="path for the structured JSON report, or '-' for stdout",
    )
    parser.add_argument(
        "--markdown-output",
        help="append Markdown to this path; defaults to GITHUB_STEP_SUMMARY when set",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        config = Config.from_env(search_url=args.search_url)
    except (TypeError, ValueError) as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    outcome = run_monitor(config)

    notification_error: str | None = None
    if not args.dry_run and not outcome.global_diagnostic:
        try:
            config.require_github()
            from .github_issues import GitHubIssueError, GitHubIssueNotifier

            notifier = GitHubIssueNotifier.from_config(config)
            notifier.reconcile(outcome.results)
        except (GitHubIssueError, TransportError, ValueError) as error:
            notification_error = str(error)

    document = report_document(
        outcome.results,
        search_url=config.search_url,
        global_diagnostic=outcome.global_diagnostic,
    )
    if notification_error:
        document["status"] = "unknown"
        document["notification_error"] = notification_error

    if args.json_output == "-":
        print(json.dumps(document, ensure_ascii=False, indent=2))
    else:
        write_json_report(document, args.json_output)

    markdown = render_markdown(
        outcome.results,
        global_diagnostic=outcome.global_diagnostic,
        dry_run=args.dry_run,
    )
    if notification_error:
        markdown += f"\n**Notification failure:** {notification_error}\n"
    print(markdown)

    markdown_path = args.markdown_output or os.getenv("GITHUB_STEP_SUMMARY")
    if markdown_path:
        with Path(markdown_path).open("a", encoding="utf-8") as summary:
            summary.write(markdown)
            if not markdown.endswith("\n"):
                summary.write("\n")

    return 1 if outcome.failed or notification_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
