"""JSON and GitHub-flavored Markdown run reports."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Iterable

from .models import AvailabilityResult, AvailabilityStatus, Diagnostic


def report_document(
    results: Iterable[AvailabilityResult],
    *,
    search_url: str,
    global_diagnostic: Diagnostic | None = None,
) -> dict[str, Any]:
    result_list = list(results)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "search_url": search_url,
        "status": (
            "unknown"
            if global_diagnostic
            or any(item.status is AvailabilityStatus.UNKNOWN for item in result_list)
            else "ok"
        ),
        "diagnostic": global_diagnostic.to_dict() if global_diagnostic else None,
        "performances": [item.to_dict() for item in result_list],
    }


def write_json_report(document: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def render_markdown(
    results: Iterable[AvailabilityResult],
    *,
    global_diagnostic: Diagnostic | None = None,
    dry_run: bool = False,
) -> str:
    result_list = list(results)
    lines = ["## Faust ticket monitor", ""]
    if dry_run:
        lines.extend(["> Dry run: GitHub Issues were not changed.", ""])
    if global_diagnostic:
        lines.extend(
            [
                f"**Discovery failed:** {_escape(global_diagnostic.message)}",
                "",
            ]
        )
    if not result_list:
        lines.extend(["No matching performances were discovered.", ""])
        return "\n".join(lines)

    lines.extend(
        [
            "| Date | Event | Status | Available | Total | Ticket page | Diagnostic |",
            "|---|---:|---|---:|---:|---|---|",
        ]
    )
    for result in result_list:
        performance = result.performance
        event_link = f"[{performance.event_id}]({performance.event_url})"
        ticket_link = (
            f"[Open]({performance.ticket_url})" if performance.ticket_url else "—"
        )
        diagnostic = _escape(result.diagnostic.message) if result.diagnostic else ""
        lines.append(
            "| "
            + " | ".join(
                [
                    performance.performance_date.isoformat()
                    if performance.performance_date
                    else "unknown",
                    event_link,
                    result.status.value,
                    str(result.available_seats),
                    str(result.total_seats),
                    ticket_link,
                    diagnostic,
                ]
            )
            + " |"
        )
    lines.append("")
    return "\n".join(lines)


def _escape(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())

