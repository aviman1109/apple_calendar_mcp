"""Tool registration for the Apple Calendar multi-account MCP server."""

from mcp.server.fastmcp import FastMCP

from apple_calendar_multi_mcp.auth.policy import AuthorizationPolicy
from apple_calendar_multi_mcp.config import OIDCConfig
from apple_calendar_multi_mcp.icloud_api import AppleCalendarClientManager
from apple_calendar_multi_mcp.tools.accounts import register_account_tools
from apple_calendar_multi_mcp.tools.calendars import register_calendar_tools
from apple_calendar_multi_mcp.tools.events import register_event_tools


def register_tools(
    app: FastMCP,
    manager: AppleCalendarClientManager,
    auth_config: OIDCConfig,
    authz_policy: AuthorizationPolicy,
) -> FastMCP:
    """Register the initial set of multi-account Apple Calendar tools."""

    register_account_tools(app, manager, auth_config, authz_policy)
    register_calendar_tools(app, manager, auth_config, authz_policy)
    register_event_tools(app, manager, auth_config, authz_policy)
    return app
