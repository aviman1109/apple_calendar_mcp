"""Protected resource stub - OAuth metadata response when disabled."""

from __future__ import annotations

from starlette.responses import JSONResponse


def protected_resource_metadata_response(config: object) -> JSONResponse:
    """OAuth disabled - return 404."""
    return JSONResponse({"error": "OAuth is disabled for this MCP server."}, status_code=404)
