"""Server bootstrap for the multi-account Apple Calendar MCP."""

from __future__ import annotations

from dataclasses import replace
import json
import logging
import sys
from uuid import uuid4

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from sse_starlette.sse import EventSourceResponse
import uvicorn

from apple_calendar_multi_mcp.auth.policy import AuthorizationPolicy
from apple_calendar_multi_mcp.config import load_accounts, load_app_config
from apple_calendar_multi_mcp.icloud_api import AppleCalendarClientManager
from apple_calendar_multi_mcp.tools import register_tools

logger = logging.getLogger(__name__)

# OpenAI often opens a standalone GET /mcp SSE stream right after initialize.
# The default 15s SSE ping is too quiet and can trigger client-side timeouts
# before the first frame arrives through Cloudflare. Shorten the heartbeat.
EventSourceResponse.DEFAULT_PING_INTERVAL = 2


SERVER_INSTRUCTIONS = """
This MCP server exposes iCloud Calendar data for multiple pre-configured Apple IDs.
Always call list_accounts first when you are unsure which account_id to use.
Every tool requires an explicit account_id so reads and writes stay scoped to the right Apple account.
Use get_account_status to validate credentials and inspect the resolved default calendar before writing.
""".strip()


async def _oauth_disabled_endpoint(_request) -> JSONResponse:
    """OAuth is disabled - return 404 for all OAuth discovery endpoints."""
    return JSONResponse({"error": "OAuth is disabled for this MCP server."}, status_code=404)


def _wrap_trailing_slash_compat(app, request_path: str):
    normalized_path = request_path if request_path.startswith("/") else f"/{request_path}"
    canonical_path = normalized_path.rstrip("/") or "/"
    alternate_path = canonical_path if normalized_path.endswith("/") else f"{canonical_path}/"

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == alternate_path:
            scope = dict(scope)
            scope["path"] = canonical_path
            root_path = scope.get("root_path", "")
            scope["raw_path"] = f"{root_path}{canonical_path}".encode()
        await app(scope, receive, send)

    return wrapped


def _wrap_octet_stream_compat(app, request_path: str):
    normalized_path = request_path if request_path.startswith("/") else f"/{request_path}"
    canonical_path = normalized_path.rstrip("/") or "/"

    async def wrapped(scope, receive, send):
        if scope["type"] == "http" and scope.get("method") == "POST":
            path = scope.get("path", "")
            if path in {canonical_path, f"{canonical_path}/"}:
                raw_headers = scope.get("headers", [])
                rewritten_headers = []
                changed = False
                saw_accept = False
                for key, value in raw_headers:
                    if key.lower() == b"content-type" and value.split(b";", 1)[0].strip() == b"application/octet-stream":
                        rewritten_headers.append((key, b"application/json"))
                        changed = True
                    elif key.lower() == b"accept":
                        saw_accept = True
                        lowered = value.lower()
                        has_json = b"application/json" in lowered
                        has_sse = b"text/event-stream" in lowered
                        has_wildcard = b"*/*" in lowered
                        if has_wildcard or not (has_json and has_sse):
                            rewritten_headers.append((key, b"application/json, text/event-stream"))
                            changed = True
                        else:
                            rewritten_headers.append((key, value))
                    else:
                        rewritten_headers.append((key, value))
                if not saw_accept:
                    rewritten_headers.append((b"accept", b"application/json, text/event-stream"))
                    changed = True
                if changed:
                    scope = dict(scope)
                    scope["headers"] = rewritten_headers
        await app(scope, receive, send)

    return wrapped


def _redact_headers(headers: list[tuple[bytes, bytes]]) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in headers:
        name = key.decode("latin-1")
        rendered = value.decode("latin-1", errors="replace")
        if name.lower() in {"authorization", "cookie", "set-cookie"}:
            rendered = "<redacted>"
        redacted[name] = rendered
    return redacted


def _wrap_http_debug(app, runtime_config):
    async def wrapped(scope, receive, send):
        if scope["type"] != "http" or not runtime_config.debug_http:
            await app(scope, receive, send)
            return

        debug_id = uuid4().hex[:8]
        request_headers = scope.get("headers", [])
        body_parts: list[bytes] = []
        more_body = True

        while more_body:
            message = await receive()
            if message["type"] != "http.request":
                continue
            body_parts.append(message.get("body", b""))
            more_body = bool(message.get("more_body"))

        body = b"".join(body_parts)
        body_preview = body[: runtime_config.debug_http_body_max_bytes].decode(
            "utf-8", errors="replace"
        )
        if len(body) > runtime_config.debug_http_body_max_bytes:
            body_preview += "...<truncated>"

        logger.warning(
            "[http-debug:%s] request method=%s path=%s raw_path=%s headers=%s body=%s",
            debug_id,
            scope.get("method"),
            scope.get("path"),
            scope.get("raw_path", b"").decode("latin-1", errors="replace"),
            json.dumps(_redact_headers(request_headers), ensure_ascii=False, sort_keys=True),
            body_preview,
        )

        replayed = False
        response_body_chunks: list[bytes] = []

        async def replay_receive():
            nonlocal replayed
            if replayed:
                return {"type": "http.request", "body": b"", "more_body": False}
            replayed = True
            return {"type": "http.request", "body": body, "more_body": False}

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                logger.warning(
                    "[http-debug:%s] response status=%s headers=%s",
                    debug_id,
                    message.get("status"),
                    json.dumps(
                        _redact_headers(message.get("headers", [])),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                )
            elif message["type"] == "http.response.body":
                response_body_chunks.append(message.get("body", b""))
                if not message.get("more_body"):
                    response_body = b"".join(response_body_chunks)
                    response_preview = response_body[
                        : runtime_config.debug_http_body_max_bytes
                    ].decode("utf-8", errors="replace")
                    if len(response_body) > runtime_config.debug_http_body_max_bytes:
                        response_preview += "...<truncated>"
                    logger.warning(
                        "[http-debug:%s] response body=%s",
                        debug_id,
                        response_preview,
                    )
            await send(message)

        await app(scope, replay_receive, send_wrapper)

    return wrapped


def _wrap_http_app(http_app, runtime_config) -> Starlette:
    wrapped_app = _wrap_trailing_slash_compat(http_app, runtime_config.path)
    wrapped_app = _wrap_octet_stream_compat(wrapped_app, runtime_config.path)
    wrapped_app = _wrap_http_debug(wrapped_app, runtime_config)

    lifespan = getattr(http_app.router, "lifespan_context", None)
    root_app = Starlette(
        lifespan=lifespan,
        routes=[
            Route(
                "/.well-known/oauth-protected-resource",
                _oauth_disabled_endpoint,
                methods=["GET"],
            ),
            Mount("", app=wrapped_app),
        ]
    )
    root_app.state.runtime_config = runtime_config
    return root_app


def build_app() -> tuple[FastMCP, AppleCalendarClientManager, object]:
    """Build the MCP app and account manager."""

    load_dotenv()
    runtime_config = load_app_config()
    accounts, config_default_account_id, oidc_config = load_accounts(runtime_config.accounts_file)
    runtime_config = replace(runtime_config, oidc=oidc_config)
    manager = AppleCalendarClientManager(
        accounts=accounts,
        app_config=runtime_config,
        default_account_id=runtime_config.default_account_id or config_default_account_id,
    )
    authz_policy = AuthorizationPolicy(runtime_config.oidc, sorted(accounts))

    app = FastMCP(
        name="Apple Calendar Multi Account MCP",
        instructions=SERVER_INSTRUCTIONS,
    )
    app.settings.streamable_http_path = runtime_config.path
    # Prefer stateless streamable HTTP for ChatGPT connector discovery. Recent
    # traces show initialize succeeds, then the client opens GET /mcp and
    # stalls before tools/list. Align with the stateless FastMCP deployment
    # pattern so discovery can proceed without a session-bound long-lived
    # stream.
    app.settings.stateless_http = True
    # ChatGPT discovery has been stalling after initialize when the transport
    # stays open as SSE. Prefer finite JSON responses on the canonical /mcp
    # streamable-HTTP endpoint so the client can complete initialize and then
    # continue with tools/list.
    app.settings.json_response = True
    app.settings.transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=runtime_config.allowed_hosts,
        allowed_origins=runtime_config.allowed_origins,
    )
    register_tools(app, manager, runtime_config.oidc, authz_policy)
    return app, manager, runtime_config


def main() -> None:
    """Run the server in stdio or remote HTTP mode."""

    try:
        app, manager, runtime_config = build_app()
    except Exception as err:
        print(f"Server bootstrap failed: {err}", file=sys.stderr)
        raise

    account_count = len(manager.list_accounts())
    logging.basicConfig(
        level=logging.WARNING if runtime_config.debug_http else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    print(
        f"Loaded {account_count} Apple Calendar account(s). Transport={runtime_config.transport}",
        file=sys.stderr,
    )

    if runtime_config.transport.lower() == "stdio":
        app.run()
        return

    transport = runtime_config.transport.lower()
    if transport in {"http", "streamable-http"}:
        http_app = _wrap_http_app(app.streamable_http_app(), runtime_config)
        uvicorn.run(http_app, host=runtime_config.host, port=runtime_config.port)
        return

    raise ValueError(
        f"Unsupported transport '{runtime_config.transport}'. "
        "Use stdio, http, or streamable-http."
    )


if __name__ == "__main__":
    main()
