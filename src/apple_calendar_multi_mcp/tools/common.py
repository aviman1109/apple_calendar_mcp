"""Shared tool-layer helpers."""

from __future__ import annotations

from mcp.types import CallToolResult, TextContent


def service_error_result(message: str) -> CallToolResult:
    """Return a stable MCP tool error for backend/service failures."""

    return CallToolResult(
        content=[TextContent(type="text", text=message)],
        isError=True,
    )
