"""Auth runtime stub - no-op when auth is disabled."""

from __future__ import annotations

from typing import Any

from mcp.types import CallToolResult


def require_scope(
    auth_config: object,
    authz_policy: object,
    required_scopes: list[str],
    *,
    ctx: Any | None = None,
) -> CallToolResult | None:
    """No-op when auth is disabled - always allows."""
    return None


def require_account_access(
    auth_config: object,
    authz_policy: object,
    *,
    account_id: str = "",
    required_scopes: list[str] | None = None,
    ctx: Any | None = None,
) -> CallToolResult | None:
    """No-op when auth is disabled - always allows."""
    return None


def tool_security_meta(
    auth_config: object,
    required_scopes: list[str] | None = None,
) -> dict[str, Any]:
    """Return empty meta when auth is disabled."""
    return {}
