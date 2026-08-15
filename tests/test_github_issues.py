from __future__ import annotations

from dataclasses import replace
from datetime import date
import unittest

from faust_monitor.github_issues import (
    GitHubIssueError,
    GitHubIssueNotifier,
    MonitorIssue,
)
from faust_monitor.models import AvailabilityResult, AvailabilityStatus, Performance


class FakeApi:
    def __init__(self, issues=None, *, fail_on=None, assignees=("florin",)):
        self.issues = list(issues or [])
        self.fail_on = fail_on
        self.assignees = tuple(assignees)
        self.calls = []
        self.next_number = max((issue.number for issue in self.issues), default=0) + 1

    def _record(self, name, *args):
        self.calls.append((name, *args))
        if self.fail_on == name:
            raise GitHubIssueError(f"forced {name} failure")

    def ensure_monitor_label(self):
        self._record("label")

    def list_assignable_users(self):
        self._record("assignees")
        return self.assignees

    def list_monitor_issues(self):
        self._record("list")
        return list(self.issues)

    def create_issue(self, *, title, body, assignees):
        self._record("create", title, body, assignees)
        issue = MonitorIssue(self.next_number, title, body, "open", assignees)
        self.next_number += 1
        self.issues.append(issue)
        return issue

    def update_issue(self, number, **fields):
        self._record("update", number, fields)
        current = next(issue for issue in self.issues if issue.number == number)
        updated = replace(
            current,
            title=fields.get("title", current.title),
            body=fields.get("body", current.body),
            state=fields.get("state", current.state),
            assignees=tuple(fields.get("assignees", current.assignees)),
        )
        self.issues[self.issues.index(current)] = updated
        return updated

    def add_comment(self, number, body):
        self._record("comment", number, body)


def performance(event_id="40017", day=4):
    return Performance(
        event_id=event_id,
        title="FAUST",
        performance_date=date(2026, 9, day),
        event_url=f"https://example.test/events/{event_id}",
        ticket_url=f"https://example.test/tickets/{event_id}",
        venue="Fabrica de Cultura (Sala Faust)",
        city="Sibiu",
    )


def available(event_id="40017", day=4, count=2):
    return AvailabilityResult(
        performance(event_id, day), AvailabilityStatus.AVAILABLE, 440, count
    )


def sold_out(event_id="40017", day=4):
    return AvailabilityResult(
        performance(event_id, day), AvailabilityStatus.SOLD_OUT, 440, 0
    )


def unknown(event_id="40017", day=4):
    return AvailabilityResult.unknown(
        performance(event_id, day), "seat-map", "invalid response"
    )


class NotificationTests(unittest.TestCase):
    def test_first_availability_creates_assigned_actionable_issue(self):
        api = FakeApi()

        GitHubIssueNotifier(api).reconcile([available()])

        create = next(call for call in api.calls if call[0] == "create")
        self.assertEqual(create[3], ("florin",))
        self.assertIn("40017", create[2])
        self.assertIn("2", create[2])
        self.assertIn("https://example.test/tickets/40017", create[2])
        self.assertEqual(api.issues[0].event_id, "40017")

    def test_multiple_available_events_create_independent_issues(self):
        api = FakeApi()

        GitHubIssueNotifier(api).reconcile(
            [available("40017", 4), available("40018", 5)]
        )

        self.assertEqual([issue.event_id for issue in api.issues], ["40017", "40018"])

    def test_persistent_availability_does_not_alert_twice(self):
        api = FakeApi()
        notifier = GitHubIssueNotifier(api)
        notifier.reconcile([available()])
        api.calls.clear()

        notifier.reconcile([available()])

        self.assertEqual(
            [call[0] for call in api.calls], ["assignees", "label", "list"]
        )

    def test_confirmed_sell_out_closes_open_issue(self):
        api = FakeApi()
        notifier = GitHubIssueNotifier(api)
        notifier.reconcile([available()])
        api.calls.clear()

        notifier.reconcile([sold_out()])

        update = next(call for call in api.calls if call[0] == "update")
        self.assertEqual(update[2]["state"], "closed")
        self.assertEqual(api.issues[0].state, "closed")

    def test_reappearance_comments_then_reopens_existing_issue(self):
        api = FakeApi()
        notifier = GitHubIssueNotifier(api)
        notifier.reconcile([available()])
        notifier.reconcile([sold_out()])
        api.calls.clear()

        notifier.reconcile([available(count=3)])

        mutation_names = [
            call[0] for call in api.calls if call[0] in {"create", "comment", "update"}
        ]
        self.assertEqual(mutation_names, ["comment", "update"])
        self.assertEqual(api.issues[0].state, "open")
        self.assertEqual(len(api.issues), 1)

    def test_unknown_only_result_performs_no_github_calls(self):
        api = FakeApi()

        GitHubIssueNotifier(api).reconcile([unknown()])

        self.assertEqual(api.calls, [])

    def test_unknown_event_is_not_closed_by_expiry_cleanup(self):
        api = FakeApi()
        initial = GitHubIssueNotifier(api, today=date(2026, 8, 1))
        initial.reconcile([available()])
        api.calls.clear()

        later = GitHubIssueNotifier(api, today=date(2026, 10, 1))
        later.reconcile([unknown()])

        self.assertEqual(api.calls, [])
        self.assertEqual(api.issues[0].state, "open")

    def test_expired_missing_event_is_closed(self):
        api = FakeApi()
        initial = GitHubIssueNotifier(api, today=date(2026, 8, 1))
        initial.reconcile([available()])
        api.calls.clear()

        later = GitHubIssueNotifier(api, today=date(2026, 10, 1))
        later.reconcile([sold_out("40018", 5)])

        self.assertEqual(api.issues[0].state, "closed")

    def test_issue_mutation_failure_is_raised(self):
        api = FakeApi(fail_on="create")

        with self.assertRaisesRegex(GitHubIssueError, "forced create failure"):
            GitHubIssueNotifier(api).reconcile([available()])

    def test_duplicate_event_markers_fail_safely(self):
        body = "<!-- faust-monitor:event-id=40017 -->"
        api = FakeApi(
            [
                MonitorIssue(1, "one", body, "open"),
                MonitorIssue(2, "two", body, "closed"),
            ]
        )

        with self.assertRaisesRegex(GitHubIssueError, "Multiple"):
            GitHubIssueNotifier(api).reconcile([available()])

    def test_all_assignable_users_are_assigned(self):
        api = FakeApi(assignees=("florin", "friend"))

        GitHubIssueNotifier(api).reconcile([available()])

        self.assertEqual(api.issues[0].assignees, ("florin", "friend"))

    def test_existing_available_issue_syncs_changed_assignees(self):
        api = FakeApi(assignees=("florin",))
        notifier = GitHubIssueNotifier(api)
        notifier.reconcile([available()])
        api.assignees = ("florin", "friend")
        api.calls.clear()

        notifier.reconcile([available()])

        update = next(call for call in api.calls if call[0] == "update")
        self.assertEqual(update[2]["assignees"], ["florin", "friend"])


if __name__ == "__main__":
    unittest.main()
