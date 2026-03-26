"""Account tools for Apple Calendar MCP."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult

from apple_calendar_multi_mcp.auth.oidc import get_current_principal
from apple_calendar_multi_mcp.auth.policy import AuthorizationPolicy
from apple_calendar_multi_mcp.auth.runtime import (
    require_account_access,
    require_scope,
    tool_security_meta,
)
from apple_calendar_multi_mcp.config import OIDCConfig
from apple_calendar_multi_mcp.icloud_api import AppleCalendarError
from apple_calendar_multi_mcp.icloud_api import AppleCalendarClientManager
from apple_calendar_multi_mcp.tools.common import service_error_result


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


def register_account_tools(
    app: FastMCP,
    manager: AppleCalendarClientManager,
    auth_config: OIDCConfig,
    authz_policy: AuthorizationPolicy,
) -> FastMCP:
    """Register account discovery and verification tools."""

    @app.tool(
        annotations={
            "title": "List Apple Accounts",
            "readOnlyHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[]),
        structured_output=False,
    )
    async def list_accounts(ctx: Context | None = None) -> str | CallToolResult:
        """List account IDs available to this Apple Calendar MCP server."""

        auth_error = require_scope(
            auth_config,
            authz_policy,
            [],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        principal = get_current_principal(ctx)
        allowed = set(authz_policy.get_allowed_account_ids(principal))
        accounts = [
            account for account in manager.list_accounts() if account["account_id"] in allowed
        ]
        return _json({"accounts": accounts})

    @app.tool(
        annotations={
            "title": "Check Apple Account Status",
            "readOnlyHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
            "destructiveHint": False,
        },
        meta=tool_security_meta(auth_config, required_scopes=[]),
        structured_output=False,
    )
    async def get_account_status(
        account_id: str,
        refresh: bool = False,
        ctx: Context | None = None,
    ) -> str | CallToolResult:
        """Validate one configured Apple Calendar account and show default calendar resolution."""

        auth_error = require_scope(
            auth_config,
            authz_policy,
            [],
            ctx=ctx,
        )
        if auth_error:
            return auth_error

        account_access_error = require_account_access(
            auth_config,
            authz_policy,
            account_id=account_id,
            required_scopes=[],
            ctx=ctx,
        )
        if account_access_error:
            return account_access_error

        try:
            return _json(manager.account_status(account_id, refresh=refresh))
        except (AppleCalendarError, ValueError) as err:
            return service_error_result(str(err))

    return app
