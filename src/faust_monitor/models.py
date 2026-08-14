"""Domain models shared across monitoring, reporting, and notifications."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import date
from enum import StrEnum
from typing import Any


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class Diagnostic:
    stage: str
    message: str
    retryable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Performance:
    event_id: str
    title: str
    performance_date: date | None
    event_url: str
    venue: str
    city: str
    ticket_url: str | None = None

    def with_ticket_url(self, ticket_url: str) -> Performance:
        return replace(self, ticket_url=ticket_url)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "title": self.title,
            "performance_date": (
                self.performance_date.isoformat() if self.performance_date else None
            ),
            "event_url": self.event_url,
            "ticket_url": self.ticket_url,
            "venue": self.venue,
            "city": self.city,
        }


@dataclass(frozen=True, slots=True)
class AvailabilityResult:
    performance: Performance
    status: AvailabilityStatus
    total_seats: int = 0
    available_seats: int = 0
    legend: tuple[str, ...] = ()
    diagnostic: Diagnostic | None = None

    @classmethod
    def unknown(
        cls,
        performance: Performance,
        stage: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> AvailabilityResult:
        return cls(
            performance=performance,
            status=AvailabilityStatus.UNKNOWN,
            diagnostic=Diagnostic(stage, message, retryable),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.performance.to_dict(),
            "status": self.status.value,
            "total_seats": self.total_seats,
            "available_seats": self.available_seats,
            "legend": list(self.legend),
            "diagnostic": self.diagnostic.to_dict() if self.diagnostic else None,
        }

