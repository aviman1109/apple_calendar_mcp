"""Shared data models used by the Apple Calendar MCP service layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
from typing import Any


def isoformat_utc(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        value = datetime.combine(value, time.min).replace(tzinfo=timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class CalendarSummary:
    name: str
    url: str
    readonly: bool
    is_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EventSummary:
    uid: str
    summary: str
    calendar_name: str
    calendar_url: str
    event_url: str | None
    start: str | None
    end: str | None
    start_iso: str | None
    end_iso: str | None
    day_of_week: str | None
    readable_date: str | None
    location: str | None
    description: str | None
    all_day: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AccountVerification:
    authenticated: bool
    account_label: str
    calendar_count: int
    default_calendar_name: str | None
    default_calendar_url: str | None
    readonly: bool
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
