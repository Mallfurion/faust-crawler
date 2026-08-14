from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import unittest

from faust_monitor.entertix import (
    EntertixClient,
    EntertixParseError,
    classify_seat_map,
)
from faust_monitor.models import AvailabilityResult, AvailabilityStatus, Performance
from faust_monitor.reporting import render_markdown, report_document


FIXTURES = Path(__file__).parent / "fixtures"
SEARCH_URL = "https://www.entertix.ro/evenimente?s=faust"
EVENT_URL = (
    "https://www.entertix.ro/evenimente/40017/"
    "faust-4-septembrie-2026-fabrica-de-cultura-sala-faust-sibiu.html"
)


class FakeTransport:
    def __init__(self, pages=None, payloads=None):
        self.pages = pages or {}
        self.payloads = payloads or {}
        self.get_calls = []
        self.post_calls = []

    def get_text(self, url):
        self.get_calls.append(url)
        return self.pages[url]

    def post_form_json(self, url, fields):
        self.post_calls.append((url, fields))
        return self.payloads[url]


def fixture_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def fixture_json(name: str):
    return json.loads(fixture_text(name))


def performance(*, ticket_url="https://www.entertix.ro/bilete/40017/published.html"):
    return Performance(
        event_id="40017",
        title="FAUST",
        performance_date=date(2026, 9, 4),
        event_url=EVENT_URL,
        ticket_url=ticket_url,
        venue="Fabrica de Cultura (Sala Faust)",
        city="Sibiu",
    )


class DiscoveryTests(unittest.TestCase):
    def test_discovers_new_events_deduplicates_and_filters_strictly(self):
        transport = FakeTransport(pages={SEARCH_URL: fixture_text("search.html")})
        client = EntertixClient(transport, SEARCH_URL)

        events = client.discover_performances()

        self.assertEqual([item.event_id for item in events], ["40017", "40025"])
        self.assertEqual(events[0].performance_date, date(2026, 9, 4))
        self.assertEqual(events[1].performance_date, date(2026, 11, 8))
        self.assertTrue(all(item.city == "Sibiu" for item in events))

    def test_rejects_non_html_search_response(self):
        transport = FakeTransport(pages={SEARCH_URL: "temporarily unavailable"})
        client = EntertixClient(transport, SEARCH_URL)

        with self.assertRaises(EntertixParseError):
            client.discover_performances()

    def test_verified_zero_results_page_is_valid(self):
        html = """
        <!doctype html><html><head><title>Evenimente</title></head>
        <body><h1>0 rezultate gasite</h1></body></html>
        """
        transport = FakeTransport(pages={SEARCH_URL: html})

        self.assertEqual(EntertixClient(transport, SEARCH_URL).discover_performances(), [])

    def test_missing_result_structure_fails_instead_of_silently_returning_empty(self):
        html = """
        <!doctype html><html><head><title>Evenimente</title></head>
        <body><div>Page layout changed</div></body></html>
        """
        transport = FakeTransport(pages={SEARCH_URL: html})

        with self.assertRaisesRegex(EntertixParseError, "neither event result"):
            EntertixClient(transport, SEARCH_URL).discover_performances()

    def test_resolves_published_ticket_link_for_same_event_id(self):
        transport = FakeTransport(pages={EVENT_URL: fixture_text("event_detail.html")})
        client = EntertixClient(transport, SEARCH_URL)

        resolved = client.resolve_ticket_url(performance(ticket_url=None))

        self.assertEqual(
            resolved.ticket_url,
            "https://www.entertix.ro/bilete/40017/published-ticket-selection.html",
        )

    def test_missing_ticket_link_is_unknown_during_monitoring(self):
        missing = fixture_text("event_detail.html").replace(
            "/bilete/40017/published-ticket-selection.html", "/no-ticket-link"
        )
        search = fixture_text("search.html").replace(
            "<a class=\"eventitem\" href=\"/evenimente/40025/faust-8-noiembrie-2026.html\">",
            "<a href=\"/not-an-event\">",
        )
        transport = FakeTransport(
            pages={SEARCH_URL: search, EVENT_URL: missing}
        )
        client = EntertixClient(transport, SEARCH_URL)

        result = client.monitor()[0]

        self.assertEqual(result.status, AvailabilityStatus.UNKNOWN)
        self.assertEqual(result.diagnostic.stage, "event-detail")


class AvailabilityTests(unittest.TestCase):
    def test_sold_out_map_has_zero_selectable_seats(self):
        result = classify_seat_map(performance(), fixture_json("sold_out.json"))

        self.assertEqual(result.status, AvailabilityStatus.SOLD_OUT)
        self.assertEqual(result.total_seats, 3)
        self.assertEqual(result.available_seats, 0)
        self.assertEqual(result.legend, ("Indisponibil",))

    def test_only_exact_active_class_token_is_counted(self):
        result = classify_seat_map(performance(), fixture_json("available.json"))

        self.assertEqual(result.status, AvailabilityStatus.AVAILABLE)
        self.assertEqual(result.total_seats, 4)
        self.assertEqual(result.available_seats, 1)

    def test_zero_seat_map_is_rejected(self):
        with self.assertRaisesRegex(EntertixParseError, "zero seats"):
            classify_seat_map(performance(), fixture_json("malformed.json"))

    def test_non_string_seat_class_is_rejected(self):
        payload = {"sectors": [{"seats": [{"id": 1, "class": None}]}]}
        with self.assertRaisesRegex(EntertixParseError, "class string"):
            classify_seat_map(performance(), payload)


class ReportingTests(unittest.TestCase):
    def test_structured_and_markdown_outputs_are_traceable(self):
        result = AvailabilityResult(
            performance(), AvailabilityStatus.AVAILABLE, 440, 2
        )

        document = report_document([result], search_url=SEARCH_URL)
        markdown = render_markdown([result], dry_run=True)

        self.assertEqual(document["status"], "ok")
        self.assertEqual(document["performances"][0]["event_id"], "40017")
        self.assertEqual(document["performances"][0]["available_seats"], 2)
        self.assertIn("Dry run", markdown)
        self.assertIn("40017", markdown)
        self.assertIn("available", markdown)


if __name__ == "__main__":
    unittest.main()
