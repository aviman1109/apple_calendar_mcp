"""Event tools for Apple Calendar MCP."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult

from apple_calendar_multi_mcp.auth.policy import AuthorizationPolicy
from apple_calendar_multi_mcp.auth.runtime import require_account_access, tool_security_meta
from apple_calendar_multi_mcp.config import OIDCConfig
from apple_calendar_multi_mcp.icloud_api import AppleCalendarError
from apple_calendar_multi_mcp.icloud_api import AppleCalendarClientManager
from apple_calendar_multi_mcp.tools.common import service_error_result


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def register_event_tools(
    app: FastMCP,
    manager: AppleCalendarClientManager,
    auth_config: OIDCConfig,
    authz_policy: AuthorizationPolicy,
) -> FastMCP:
    """Register event read and write tools."""

    @app.tool(
        annotations={
            "title": "List Apple Events",
            "readOnlyHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.calendar_read_scope]),
        structured_output=False,
    )
    async def list_events(
        account_id: str,
        days_ahead: int = 7,
        days_back: int = 0,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
        search: str | None = None,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """List upcoming iCloud calendar events for one configured account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.calendar_read_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            events = [
                event.to_dict()
                for event in manager.list_events(
                    account_id=account_id,
                    days_ahead=days_ahead,
                    days_back=days_back,
                    calendar_name=calendar_name,
                    calendar_url=calendar_url,
                    search=search,
                )
            ]
        except (AppleCalendarError, ValueError) as err:
            return service_error_result(str(err))
        return _json(
            {
                "account_id": account_id,
                "days_back": days_back,
                "days_ahead": days_ahead,
                "calendar_name": calendar_name,
                "calendar_url": calendar_url,
                "search": search,
                "total": len(events),
                "events": events,
            }
        )

    @app.tool(
        annotations={
            "title": "Create Apple Event",
            "readOnlyHint": False,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.calendar_write_scope]),
        structured_output=False,
    )
    async def create_event(
        account_id: str,
        summary: str,
        start_iso: str,
        end_iso: str,
        location: str | None = None,
        description: str | None = None,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
        all_day: bool = False,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Create a new iCloud calendar event for one configured account."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.calendar_write_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            event = manager.create_event(
                account_id=account_id,
                summary=summary,
                start_iso=start_iso,
                end_iso=end_iso,
                location=location,
                description=description,
                calendar_name=calendar_name,
                calendar_url=calendar_url,
                all_day=all_day,
            )
        except (AppleCalendarError, ValueError) as err:
            return service_error_result(str(err))
        return _json(
            {
                "account_id": account_id,
                "event": event.to_dict(),
            }
        )

    @app.tool(
        annotations={
            "title": "Update Apple Event",
            "readOnlyHint": False,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.calendar_write_scope]),
        structured_output=False,
    )
    async def update_event(
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
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Update an existing iCloud calendar event by VEVENT UID."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.calendar_write_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            event = manager.update_event(
                account_id=account_id,
                event_uid=event_uid,
                summary=summary,
                start_iso=start_iso,
                end_iso=end_iso,
                location=location,
                description=description,
                calendar_name=calendar_name,
                calendar_url=calendar_url,
                all_day=all_day,
            )
        except (AppleCalendarError, ValueError) as err:
            return service_error_result(str(err))
        return _json(
            {
                "account_id": account_id,
                "event_uid": event_uid,
                "event": event.to_dict(),
            }
        )

    @app.tool(
        annotations={
            "title": "Delete Apple Event",
            "readOnlyHint": False,
            "openWorldHint": False,
            "destructiveHint": True,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.calendar_write_scope]),
        structured_output=False,
    )
    async def delete_event(
        account_id: str,
        event_uid: str,
        calendar_name: str | None = None,
        calendar_url: str | None = None,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Delete an iCloud calendar event by VEVENT UID."""

        auth_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[auth_config.calendar_write_scope],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        try:
            result = manager.delete_event(
                account_id=account_id,
                event_uid=event_uid,
                calendar_name=calendar_name,
                calendar_url=calendar_url,
            )
        except (AppleCalendarError, ValueError) as err:
            return service_error_result(str(err))
        return _json(
            {
                "account_id": account_id,
                "success": True,
                **result,
            }
        )

    return app
