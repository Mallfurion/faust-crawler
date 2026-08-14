"""Entertix discovery and read-only seat-map classification."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from html.parser import HTMLParser
import re
from typing import Any
from urllib.parse import urljoin, urlparse

from .models import AvailabilityResult, AvailabilityStatus, Performance
from .transport import HttpTransport, TransportError


TARGET_TITLE = "FAUST"
TARGET_VENUE = "Fabrica de Cultura (Sala Faust)"
TARGET_CITY = "Sibiu"
ACTIVE_SEAT_CLASS = "seatingseatactive"

EVENT_PATH_RE = re.compile(r"/evenimente/(?P<event_id>\d+)/", re.IGNORECASE)
TICKET_PATH_RE = re.compile(r"/bilete/(?P<event_id>\d+)/", re.IGNORECASE)
TITLE_RE = re.compile(r"\bFAUST\b", re.IGNORECASE)
DATE_RE = re.compile(
    r"\b(?P<day>\d{1,2})\s+"
    r"(?P<month>ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august|"
    r"septembrie|octombrie|noiembrie|decembrie)\s+"
    r"(?P<year>20\d{2})\b",
    re.IGNORECASE,
)
MONTHS = {
    "ianuarie": 1,
    "februarie": 2,
    "martie": 3,
    "aprilie": 4,
    "mai": 5,
    "iunie": 6,
    "iulie": 7,
    "august": 8,
    "septembrie": 9,
    "octombrie": 10,
    "noiembrie": 11,
    "decembrie": 12,
}


class EntertixParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Anchor:
    href: str
    text: str
    classes: tuple[str, ...] = ()


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[Anchor] = []
        self.headings: list[str] = []
        self.title = ""
        self._anchor_href: str | None = None
        self._anchor_parts: list[str] = []
        self._anchor_classes: tuple[str, ...] = ()
        self._heading_tag: str | None = None
        self._heading_parts: list[str] = []
        self._in_title = False
        self._title_parts: list[str] = []
        self._all_text_parts: list[str] = []

    @property
    def text(self) -> str:
        return _normalize(" ".join(self._all_text_parts))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "a" and self._anchor_href is None:
            self._anchor_href = attributes.get("href")
            self._anchor_parts = []
            self._anchor_classes = tuple((attributes.get("class") or "").split())
        if tag in {"h1", "h2"} and self._heading_tag is None:
            self._heading_tag = tag
            self._heading_parts = []
        if tag == "title":
            self._in_title = True
            self._title_parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor_href is not None:
            self.anchors.append(
                Anchor(
                    self._anchor_href,
                    _normalize(" ".join(self._anchor_parts)),
                    self._anchor_classes,
                )
            )
            self._anchor_href = None
            self._anchor_parts = []
            self._anchor_classes = ()
        if tag == self._heading_tag:
            self.headings.append(_normalize(" ".join(self._heading_parts)))
            self._heading_tag = None
            self._heading_parts = []
        if tag == "title" and self._in_title:
            self.title = _normalize(" ".join(self._title_parts))
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if not data.strip():
            return
        self._all_text_parts.append(data)
        if self._anchor_href is not None:
            self._anchor_parts.append(data)
        if self._heading_tag is not None:
            self._heading_parts.append(data)
        if self._in_title:
            self._title_parts.append(data)


class EntertixClient:
    def __init__(self, transport: HttpTransport, search_url: str) -> None:
        self.transport = transport
        self.search_url = search_url

    def discover_performances(self) -> list[Performance]:
        html = self.transport.get_text(self.search_url)
        parser = _parse_page(html, expected_title="Evenimente")
        performances: dict[str, Performance] = {}
        result_anchors = [
            anchor for anchor in parser.anchors if "eventitem" in anchor.classes
        ]
        if not result_anchors:
            no_results = re.search(
                r"\b0\s+rezultate\s+gasite\b", parser.text, re.IGNORECASE
            )
            if no_results:
                return []
            raise EntertixParseError(
                "search page contained neither event result items nor a verified zero-results marker"
            )

        for anchor in result_anchors:
            absolute_url = urljoin(self.search_url, anchor.href)
            match = EVENT_PATH_RE.search(urlparse(absolute_url).path)
            if not match or not _is_target_text(anchor.text):
                continue
            event_id = match.group("event_id")
            performances.setdefault(
                event_id,
                Performance(
                    event_id=event_id,
                    title=TARGET_TITLE,
                    performance_date=_parse_date(anchor.text),
                    event_url=absolute_url,
                    venue=TARGET_VENUE,
                    city=TARGET_CITY,
                ),
            )

        return sorted(
            performances.values(),
            key=lambda item: (item.performance_date or date.max, int(item.event_id)),
        )

    def resolve_ticket_url(self, performance: Performance) -> Performance:
        html = self.transport.get_text(performance.event_url)
        parser = _parse_page(html)
        normalized_headings = {_normalize(heading).upper() for heading in parser.headings}
        if TARGET_TITLE not in normalized_headings:
            raise EntertixParseError(
                f"event {performance.event_id} detail page did not contain the exact FAUST heading"
            )
        if TARGET_VENUE.casefold() not in parser.text.casefold() or TARGET_CITY.casefold() not in parser.text.casefold():
            raise EntertixParseError(
                f"event {performance.event_id} detail page did not match the target venue and city"
            )

        for anchor in parser.anchors:
            absolute_url = urljoin(performance.event_url, anchor.href)
            match = TICKET_PATH_RE.search(urlparse(absolute_url).path)
            if match and match.group("event_id") == performance.event_id:
                parsed_date = _parse_date(parser.text) or performance.performance_date
                return replace(
                    performance,
                    performance_date=parsed_date,
                    ticket_url=absolute_url,
                )

        raise EntertixParseError(
            f"event {performance.event_id} detail page had no matching ticket-selection link"
        )

    def check_availability(self, performance: Performance) -> AvailabilityResult:
        if not performance.ticket_url:
            return AvailabilityResult.unknown(
                performance,
                "ticket-link",
                "No ticket-selection URL was resolved",
            )
        try:
            payload = self.transport.post_form_json(
                performance.ticket_url,
                {"do": "getmapdata"},
            )
            return classify_seat_map(performance, payload)
        except (TransportError, EntertixParseError) as error:
            return AvailabilityResult.unknown(
                performance,
                "seat-map",
                str(error),
                retryable=getattr(error, "retryable", False),
            )

    def monitor(self) -> list[AvailabilityResult]:
        results: list[AvailabilityResult] = []
        for performance in self.discover_performances():
            try:
                resolved = self.resolve_ticket_url(performance)
            except (TransportError, EntertixParseError) as error:
                results.append(
                    AvailabilityResult.unknown(
                        performance,
                        "event-detail",
                        str(error),
                        retryable=getattr(error, "retryable", False),
                    )
                )
                continue
            results.append(self.check_availability(resolved))
        return results


def classify_seat_map(performance: Performance, payload: Any) -> AvailabilityResult:
    if not isinstance(payload, dict):
        raise EntertixParseError("seat-map response was not a JSON object")
    sectors = payload.get("sectors")
    if not isinstance(sectors, list):
        raise EntertixParseError("seat-map response did not contain a sectors list")

    total_seats = 0
    available_seats = 0
    for sector in sectors:
        if not isinstance(sector, dict):
            raise EntertixParseError("seat-map sector was not an object")
        seats = sector.get("seats", [])
        if seats is None:
            seats = []
        if not isinstance(seats, list):
            raise EntertixParseError("seat-map sector seats were not a list")
        for seat in seats:
            if not isinstance(seat, dict):
                raise EntertixParseError("seat-map seat was not an object")
            class_name = seat.get("class")
            if not isinstance(class_name, str):
                raise EntertixParseError("seat-map seat did not contain a class string")
            total_seats += 1
            if ACTIVE_SEAT_CLASS in class_name.split():
                available_seats += 1

    if total_seats == 0:
        raise EntertixParseError("seat-map response contained zero seats")

    legend_value = payload.get("legend", [])
    legend: list[str] = []
    if isinstance(legend_value, list):
        for entry in legend_value:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                legend.append(entry["name"])

    status = (
        AvailabilityStatus.AVAILABLE
        if available_seats > 0
        else AvailabilityStatus.SOLD_OUT
    )
    return AvailabilityResult(
        performance=performance,
        status=status,
        total_seats=total_seats,
        available_seats=available_seats,
        legend=tuple(legend),
    )


def _parse_page(html: str, *, expected_title: str | None = None) -> PageParser:
    if "<html" not in html.casefold():
        raise EntertixParseError("response did not look like an HTML document")
    parser = PageParser()
    parser.feed(html)
    parser.close()
    if expected_title and expected_title.casefold() not in parser.title.casefold():
        raise EntertixParseError(
            f"expected page title containing {expected_title!r}, got {parser.title!r}"
        )
    return parser


def _is_target_text(text: str) -> bool:
    normalized = _normalize(text)
    return bool(
        TITLE_RE.search(normalized)
        and TARGET_VENUE.casefold() in normalized.casefold()
        and TARGET_CITY.casefold() in normalized.casefold()
    )


def _parse_date(text: str) -> date | None:
    match = DATE_RE.search(_normalize(text))
    if not match:
        return None
    return date(
        int(match.group("year")),
        MONTHS[match.group("month").casefold()],
        int(match.group("day")),
    )


def _normalize(value: str) -> str:
    return " ".join(value.split())
