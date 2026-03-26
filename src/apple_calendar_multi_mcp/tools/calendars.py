"""Calendar tools for Apple Calendar MCP."""

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


def register_calendar_tools(
    app: FastMCP,
    manager: AppleCalendarClientManager,
    auth_config: OIDCConfig,
    authz_policy: AuthorizationPolicy,
) -> FastMCP:
    """Register calendar listing tools."""

    @app.tool(
        annotations={
            "title": "List Apple Calendars",
            "readOnlyHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[auth_config.calendar_read_scope]),
        structured_output=False,
    )
    async def list_calendars(account_id: str, ctx: Context | None = None) -> str | CallToolResult:
        """List all calendars for one configured Apple ID."""

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
            calendars = [calendar.to_dict() for calendar in manager.list_calendars(account_id)]
        except (AppleCalendarError, ValueError) as err:
            return service_error_result(str(err))
        return _json(
            {
                "account_id": account_id,
                "total": len(calendars),
                "calendars": calendars,
            }
        )

    return app
