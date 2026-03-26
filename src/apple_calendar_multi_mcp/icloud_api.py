"""iCloud CalDAV account registry and calendar service helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import logging
from typing import Any
from uuid import uuid4

from caldav import DAVClient
from caldav.elements import dav
from icalendar import Calendar as ICal
from icalendar import Event as ICalEvent

from apple_calendar_multi_mcp.config import AppConfig, AppleCalendarAccount, resolve_value
from apple_calendar_multi_mcp.models import AccountVerification, CalendarSummary, EventSummary, isoformat_utc

logger = logging.getLogger(__name__)


class AppleCalendarError(RuntimeError):
    """Base Apple Calendar service error."""


class ReadOnlyAccountError(AppleCalendarError):
    """Raised when attempting to mutate a readonly account."""


@dataclass
class _AccountSession:
    client: Any
    principal: Any
    calendars: list[Any]


def _to_datetime(value: Any) -> tuple[datetime | None, bool]:
    if value is None:
        return None, False
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc), False
        return value, False
    if isinstance(value, date):
        return datetime.combine(value, time.min).replace(tzinfo=timezone.utc), True
    return None, False


def _calendar_display_name(calendar: Any) -> str:
    props = calendar.get_properties([dav.DisplayName()])
    return str(props.get("{DAV:}displayname", "Unnamed")) if props else "Unnamed"


def _event_component_from_raw(raw_event: Any) -> tuple[Any, Any]:
    ics = ICal.from_ical(raw_event.data)
    for component in ics.walk("VEVENT"):
        return ics, component
    raise AppleCalendarError("Event data did not contain a VEVENT component")


def _normalize_raw_event(raw_event: Any, calendar: Any) -> EventSummary:
    _, component = _event_component_from_raw(raw_event)
    start_dt, all_day = _to_datetime(component.decoded("dtstart"))
    end_raw = component.decoded("dtend") if component.get("dtend") else None
    end_dt, _ = _to_datetime(end_raw)

    readable_date = (
        start_dt.strftime("%B %d, %Y (%A)") if start_dt is not None else None
    )
    day_of_week = start_dt.strftime("%A") if start_dt is not None else None
    start_str = start_dt.strftime("%Y-%m-%d %H:%M") if start_dt is not None else None
    end_str = end_dt.strftime("%Y-%m-%d %H:%M") if end_dt is not None else None

    return EventSummary(
        uid=str(component.get("uid")),
        summary=str(component.get("summary", "")),
        calendar_name=_calendar_display_name(calendar),
        calendar_url=str(calendar.url),
        event_url=str(getattr(raw_event, "url", "")) or None,
        start=start_str,
        end=end_str,
        start_iso=isoformat_utc(start_dt),
        end_iso=isoformat_utc(end_dt),
        day_of_week=day_of_week,
        readable_date=readable_date,
        location=str(component.get("location")) if component.get("location") else None,
        description=str(component.get("description")) if component.get("description") else None,
        all_day=all_day,
    )


class AppleCalendarClientManager:
    """Small in-memory cache of authenticated iCloud CalDAV sessions."""

    def __init__(
        self,
        accounts: dict[str, AppleCalendarAccount],
        app_config: AppConfig,
        default_account_id: str | None = None,
    ) -> None:
        self._accounts = accounts
        self._app_config = app_config
        self._default_account_id = default_account_id
        self._sessions: dict[str, _AccountSession] = {}

    def list_accounts(self) -> list[dict[str, object]]:
        return [
            {
                "account_id": account.account_id,
                "label": account.label,
                "readonly": account.readonly,
                "default_calendar_name": account.default_calendar_name,
                "default_calendar_url": account.default_calendar_url,
            }
            for account in self._accounts.values()
        ]

    def get_account(self, account_id: str | None = None) -> AppleCalendarAccount:
        resolved_id = account_id or self._default_account_id
        if not resolved_id:
            raise ValueError("account_id is required because no default account is configured")
        try:
            return self._accounts[resolved_id]
        except KeyError as err:
            available = ", ".join(sorted(self._accounts))
            raise ValueError(f"Unknown account_id '{resolved_id}'. Available: {available}") from err

    def get_session(self, account_id: str | None = None, refresh: bool = False) -> _AccountSession:
        account = self.get_account(account_id)
        if refresh:
            self._sessions.pop(account.account_id, None)
        if account.account_id not in self._sessions:
            self._sessions[account.account_id] = self._connect(account)
        return self._sessions[account.account_id]

    def account_status(self, account_id: str | None = None, refresh: bool = False) -> dict[str, object]:
        account = self.get_account(account_id)
        session = self.get_session(account.account_id, refresh=refresh)
        default_calendar = self.resolve_calendar(account.account_id)
        verification = AccountVerification(
            authenticated=True,
            account_label=account.label,
            calendar_count=len(session.calendars),
            default_calendar_name=_calendar_display_name(default_calendar) if default_calendar else None,
            default_calendar_url=str(default_calendar.url) if default_calendar else None,
            readonly=account.readonly,
            warning="iCloud CalDAV capabilities may differ from macOS native EventKit."
            if account.readonly
            else "This account can write through CalDAV if the app-specific password remains valid.",
        )
        return {
            **asdict(account),
            "verification": verification.to_dict(),
        }

    def resolve_calendar(
        self,
        account_id: str | None = None,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
    ) -> Any:
        account = self.get_account(account_id)
        session = self.get_session(account.account_id)

        if calendar_url:
            for calendar in session.calendars:
                if str(calendar.url) == str(calendar_url):
                    return calendar
            raise AppleCalendarError(
                f"Calendar URL '{calendar_url}' was not found for account '{account.account_id}'"
            )

        if calendar_name:
            for calendar in session.calendars:
                if _calendar_display_name(calendar) == calendar_name:
                    return calendar
            raise AppleCalendarError(
                f"Calendar '{calendar_name}' was not found for account '{account.account_id}'"
            )

        if account.default_calendar_url:
            return self.resolve_calendar(account.account_id, calendar_url=account.default_calendar_url)

        if account.default_calendar_name:
            return self.resolve_calendar(account.account_id, calendar_name=account.default_calendar_name)

        if session.calendars:
            return session.calendars[0]
        raise AppleCalendarError(f"No calendars available for account '{account.account_id}'")

    def list_calendars(self, account_id: str | None = None) -> list[CalendarSummary]:
        account = self.get_account(account_id)
        session = self.get_session(account.account_id)
        default_calendar = self.resolve_calendar(account.account_id)
        results: list[CalendarSummary] = []
        for calendar in session.calendars:
            results.append(
                CalendarSummary(
                    name=_calendar_display_name(calendar),
                    url=str(calendar.url),
                    readonly=account.readonly,
                    is_default=str(calendar.url) == str(default_calendar.url),
                )
            )
        return results

    def list_events(
        self,
        account_id: str,
        days_ahead: int = 7,
        days_back: int = 0,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
        search: str | None = None,
    ) -> list[EventSummary]:
        session = self.get_session(account_id)
        calendars = (
            [self.resolve_calendar(account_id, calendar_name=calendar_name, calendar_url=calendar_url)]
            if (calendar_name or calendar_url)
            else session.calendars
        )
        now = datetime.now(timezone.utc) - timedelta(days=days_back)
        end = datetime.now(timezone.utc) + timedelta(days=days_ahead)
        events: list[EventSummary] = []
        search_terms = [term for term in (search or "").lower().split() if term]

        for calendar in calendars:
            try:
                raw_events = calendar.date_search(start=now, end=end)
            except Exception as err:
                if calendar_name or calendar_url:
                    raise AppleCalendarError(
                        f"Failed to list events from calendar '{_calendar_display_name(calendar)}': {err}"
                    ) from err
                logger.warning(
                    "Skipping calendar %s during date_search for account %s: %s",
                    _calendar_display_name(calendar),
                    account_id,
                    err,
                )
                continue
            for raw_event in raw_events:
                try:
                    normalized = _normalize_raw_event(raw_event, calendar)
                except Exception as err:
                    logger.warning(
                        "Skipping unreadable event in calendar %s for account %s: %s",
                        _calendar_display_name(calendar),
                        account_id,
                        err,
                    )
                    continue
                if search_terms:
                    haystack = " ".join(
                        [
                            normalized.summary or "",
                            normalized.location or "",
                            normalized.description or "",
                        ]
                    ).lower()
                    if not all(term in haystack for term in search_terms):
                        continue
                events.append(normalized)

        events.sort(key=lambda item: item.start_iso or "")
        return events

    def create_event(
        self,
        account_id: str,
        summary: str,
        start_iso: str,
        end_iso: str,
        location: str | None = None,
        description: str | None = None,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
        all_day: bool = False,
    ) -> EventSummary:
        account = self.get_account(account_id)
        if account.readonly:
            raise ReadOnlyAccountError(f"Account '{account_id}' is readonly and cannot create events")

        calendar = self.resolve_calendar(account_id, calendar_name=calendar_name, calendar_url=calendar_url)
        start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))

        cal = ICal()
        cal.add("prodid", "-//Apple Calendar Multi MCP//EN")
        cal.add("version", "2.0")
        event = ICalEvent()
        event_uid = uuid4().hex
        event.add("uid", event_uid)
        event.add("summary", summary)
        event.add("dtstart", start_dt.date() if all_day else start_dt)
        event.add("dtend", end_dt.date() if all_day else end_dt)
        event.add("dtstamp", datetime.now(timezone.utc))
        if description:
            event.add("description", description)
        if location:
            event.add("location", location)
        cal.add_component(event)

        raw_event = calendar.add_event(cal.to_ical())
        if raw_event is None:  # pragma: no cover - depends on caldav backend behavior
            _, raw_event = self._find_event(
                account_id=account_id,
                event_uid=event_uid,
                calendar_url=str(calendar.url),
            )
        return _normalize_raw_event(raw_event, calendar)

    def update_event(
        self,
        account_id: str,
        event_uid: str,
        summary: str | None = None,
        start_iso: str | None = None,
        end_iso: str | None = None,
        location: str | None = None,
        description: str | None = None,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
        all_day: bool | None = None,
    ) -> EventSummary:
        account = self.get_account(account_id)
        if account.readonly:
            raise ReadOnlyAccountError(f"Account '{account_id}' is readonly and cannot update events")

        calendar, raw_event = self._find_event(
            account_id,
            event_uid,
            calendar_name=calendar_name,
            calendar_url=calendar_url,
        )
        ics, component = _event_component_from_raw(raw_event)

        if summary is not None:
            component["SUMMARY"] = summary
        if start_iso is not None:
            start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            component["DTSTART"] = start_dt.date() if all_day else start_dt
        if end_iso is not None:
            end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            component["DTEND"] = end_dt.date() if all_day else end_dt
        if all_day is not None and start_iso is None and component.get("DTSTART"):
            current_start, _ = _to_datetime(component.decoded("dtstart"))
            if current_start is not None:
                component["DTSTART"] = current_start.date() if all_day else current_start
        if all_day is not None and end_iso is None and component.get("DTEND"):
            current_end, _ = _to_datetime(component.decoded("dtend"))
            if current_end is not None:
                component["DTEND"] = current_end.date() if all_day else current_end
        if location is not None:
            component["LOCATION"] = location
        if description is not None:
            component["DESCRIPTION"] = description

        raw_event.data = ics.to_ical()
        if hasattr(raw_event, "save"):
            raw_event.save()
        else:  # pragma: no cover - defensive fallback
            raise AppleCalendarError("Underlying CalDAV event object does not support save()")

        return _normalize_raw_event(raw_event, calendar)

    def delete_event(
        self,
        account_id: str,
        event_uid: str,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
    ) -> dict[str, str]:
        account = self.get_account(account_id)
        if account.readonly:
            raise ReadOnlyAccountError(f"Account '{account_id}' is readonly and cannot delete events")

        calendar, raw_event = self._find_event(
            account_id,
            event_uid,
            calendar_name=calendar_name,
            calendar_url=calendar_url,
        )
        if hasattr(raw_event, "delete"):
            raw_event.delete()
        else:  # pragma: no cover - defensive fallback
            raise AppleCalendarError("Underlying CalDAV event object does not support delete()")
        return {
            "event_uid": event_uid,
            "calendar_name": _calendar_display_name(calendar),
            "calendar_url": str(calendar.url),
        }

    def _find_event(
        self,
        account_id: str,
        event_uid: str,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
    ) -> tuple[Any, Any]:
        session = self.get_session(account_id)
        calendars = (
            [self.resolve_calendar(account_id, calendar_name=calendar_name, calendar_url=calendar_url)]
            if (calendar_name or calendar_url)
            else session.calendars
        )

        start = datetime.now(timezone.utc) - timedelta(days=365)
        end = datetime.now(timezone.utc) + timedelta(days=3650)
        for calendar in calendars:
            for raw_event in calendar.date_search(start=start, end=end):
                try:
                    normalized = _normalize_raw_event(raw_event, calendar)
                except Exception:
                    continue
                if normalized.uid == event_uid:
                    return calendar, raw_event
        raise AppleCalendarError(f"Event UID '{event_uid}' was not found")

    def _connect(self, account: AppleCalendarAccount) -> _AccountSession:
        apple_id = resolve_value(account.apple_id, account.apple_id_file)
        app_password = resolve_value(account.app_password, account.app_password_file)
        if not apple_id or not app_password:
            raise AppleCalendarError(
                f"Account '{account.account_id}' must define apple_id/apple_id_file and "
                "app_password/app_password_file"
            )

        client = DAVClient(
            url=self._app_config.caldav_url,
            username=apple_id,
            password=app_password,
        )
        principal = client.principal()
        calendars = principal.calendars()
        if not calendars:
            raise AppleCalendarError(f"No calendars returned for account '{account.account_id}'")
        return _AccountSession(client=client, principal=principal, calendars=calendars)
