"""Configuration helpers for the multi-account Apple Calendar MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml


AuthMode = Literal["disabled", "mixed", "oauth_required"]


@dataclass(frozen=True)
class AppleCalendarAccount:
    """Static account configuration loaded from YAML."""

    account_id: str
    label: str
    apple_id: str | None = None
    apple_id_file: str | None = None
    app_password: str | None = None
    app_password_file: str | None = None
    default_calendar_name: str | None = None
    default_calendar_url: str | None = None
    readonly: bool = False


@dataclass(frozen=True)
class AccountAccessRule:
    """Map an authenticated OIDC principal to allowed Apple account IDs."""

    subjects: list[str]
    emails: list[str]
    groups: list[str]
    account_ids: list[str]
    default_account_id: str | None = None


@dataclass(frozen=True)
class OIDCConfig:
    """OIDC/OAuth configuration for protecting the MCP resource server."""

    mode: AuthMode
    issuer: str | None
    discovery_url: str | None
    jwks_url: str | None
    audience: str | None
    resource_url: str | None
    accounts_read_scope: str
    calendar_read_scope: str
    calendar_write_scope: str
    access_rules: list[AccountAccessRule]

    @property
    def enabled(self) -> bool:
        return self.mode != "disabled"

    @property
    def scopes_supported(self) -> list[str]:
        scopes = [
            self.accounts_read_scope,
            self.calendar_read_scope,
            self.calendar_write_scope,
        ]
        return [scope for scope in dict.fromkeys(scope for scope in scopes if scope)]

    @property
    def connector_auth_scopes(self) -> list[str]:
        """Scopes advertised to MCP clients for stable ChatGPT auth behavior."""

        scopes = ["openid", "email", *self.scopes_supported]
        return [scope for scope in dict.fromkeys(scope for scope in scopes if scope)]

    @property
    def resource_metadata_url(self) -> str | None:
        if not self.resource_url:
            return None
        return f"{self.resource_url.rstrip('/')}/.well-known/oauth-protected-resource"


@dataclass(frozen=True)
class AppConfig:
    """Application runtime configuration."""

    accounts_file: str
    default_account_id: str | None
    transport: str
    host: str
    port: int
    path: str
    allowed_hosts: list[str]
    allowed_origins: list[str]
    caldav_url: str
    debug_http: bool
    debug_http_body_max_bytes: int
    oidc: OIDCConfig


def resolve_value(raw: str | None, file_path: str | None) -> str | None:
    """Resolve a value directly or from a file path."""

    if raw and file_path:
        raise ValueError("Only one of direct value and file path may be provided")
    if file_path:
        return Path(os.path.expanduser(file_path)).read_text().rstrip()
    return raw


def _parse_csv_env(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_bool_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError(f"Expected string or list value, got: {type(value)!r}")


def _normalize_account(raw: dict[str, Any]) -> AppleCalendarAccount:
    account_id = str(raw["account_id"]).strip()
    if not account_id:
        raise ValueError("Account configuration contains an empty account_id")

    label = str(raw.get("label") or account_id).strip()
    return AppleCalendarAccount(
        account_id=account_id,
        label=label,
        apple_id=raw.get("apple_id"),
        apple_id_file=raw.get("apple_id_file"),
        app_password=raw.get("app_password"),
        app_password_file=raw.get("app_password_file"),
        default_calendar_name=raw.get("default_calendar_name"),
        default_calendar_url=raw.get("default_calendar_url"),
        readonly=bool(raw.get("readonly", False)),
    )


def _normalize_access_rule(raw: dict[str, Any]) -> AccountAccessRule:
    account_ids = _parse_list(raw.get("account_ids"))
    if not account_ids:
        raise ValueError("Auth access rule must define at least one account_id")

    return AccountAccessRule(
        subjects=_parse_list(raw.get("subjects") or raw.get("subject")),
        emails=_parse_list(raw.get("emails") or raw.get("email")),
        groups=_parse_list(raw.get("groups") or raw.get("group")),
        account_ids=account_ids,
        default_account_id=str(raw["default_account_id"])
        if raw.get("default_account_id") is not None
        else None,
    )


def _load_oidc_config(data: dict[str, Any]) -> OIDCConfig:
    raw_auth = data.get("auth") or {}

    mode = str(os.getenv("APPLE_CALENDAR_AUTH_MODE") or raw_auth.get("mode") or "disabled").lower()
    if mode not in {"disabled", "mixed", "oauth_required"}:
        raise ValueError(
            f"Unsupported APPLE_CALENDAR_AUTH_MODE '{mode}'. "
            "Use disabled, mixed, or oauth_required."
        )

    issuer = os.getenv("APPLE_CALENDAR_OIDC_ISSUER") or raw_auth.get("issuer")
    discovery_url = os.getenv("APPLE_CALENDAR_OIDC_DISCOVERY_URL") or raw_auth.get("discovery_url")
    jwks_url = os.getenv("APPLE_CALENDAR_OIDC_JWKS_URL") or raw_auth.get("jwks_url")
    audience = os.getenv("APPLE_CALENDAR_OIDC_AUDIENCE") or raw_auth.get("audience")
    resource_url = os.getenv("APPLE_CALENDAR_RESOURCE_URL") or raw_auth.get("resource_url")
    accounts_read_scope = (
        os.getenv("APPLE_CALENDAR_OIDC_ACCOUNTS_READ_SCOPE")
        or raw_auth.get("accounts_read_scope")
        or "accounts.read"
    )
    calendar_read_scope = (
        os.getenv("APPLE_CALENDAR_OIDC_CALENDAR_READ_SCOPE")
        or raw_auth.get("calendar_read_scope")
        or "calendar.read"
    )
    calendar_write_scope = (
        os.getenv("APPLE_CALENDAR_OIDC_CALENDAR_WRITE_SCOPE")
        or raw_auth.get("calendar_write_scope")
        or "calendar.write"
    )
    access_rules = [
        _normalize_access_rule(rule)
        for rule in (raw_auth.get("access_rules") or [])
    ]

    oidc = OIDCConfig(
        mode=mode,  # type: ignore[arg-type]
        issuer=str(issuer) if issuer else None,
        discovery_url=str(discovery_url) if discovery_url else None,
        jwks_url=str(jwks_url) if jwks_url else None,
        audience=str(audience) if audience else None,
        resource_url=str(resource_url).rstrip("/") if resource_url else None,
        accounts_read_scope=str(accounts_read_scope),
        calendar_read_scope=str(calendar_read_scope),
        calendar_write_scope=str(calendar_write_scope),
        access_rules=access_rules,
    )

    if oidc.enabled and not oidc.resource_url:
        raise ValueError("OAuth mode requires APPLE_CALENDAR_RESOURCE_URL or auth.resource_url")
    if oidc.enabled and not oidc.issuer and not oidc.discovery_url:
        raise ValueError("OAuth mode requires APPLE_CALENDAR_OIDC_ISSUER or discovery_url")

    return oidc


def load_accounts(accounts_file: str) -> tuple[dict[str, AppleCalendarAccount], str | None, OIDCConfig]:
    """Load multi-account registry and auth settings from YAML."""

    config_path = Path(os.path.expanduser(accounts_file))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Accounts configuration not found: {config_path}. "
            "Create it from config/accounts.example.yaml."
        )

    data = yaml.safe_load(config_path.read_text()) or {}
    raw_accounts = data.get("accounts") or []
    if not raw_accounts:
        raise ValueError(f"No accounts configured in {config_path}")

    accounts: dict[str, AppleCalendarAccount] = {}
    for raw in raw_accounts:
        account = _normalize_account(raw)
        if account.account_id in accounts:
            raise ValueError(f"Duplicate account_id '{account.account_id}' in {config_path}")
        accounts[account.account_id] = account

    default_account_id = data.get("default_account_id")
    if default_account_id and default_account_id not in accounts:
        raise ValueError(
            f"default_account_id '{default_account_id}' is not present in accounts list"
        )

    oidc = _load_oidc_config(data)
    for rule in oidc.access_rules:
        for account_id in rule.account_ids:
            if account_id != "*" and account_id not in accounts:
                raise ValueError(f"Auth rule references unknown account_id '{account_id}'")
        if rule.default_account_id and rule.default_account_id not in accounts:
            raise ValueError(
                f"Auth rule default_account_id '{rule.default_account_id}' is not in accounts list"
            )

    return accounts, default_account_id, oidc


def load_app_config() -> AppConfig:
    """Load runtime configuration from environment."""

    default_allowed_hosts = [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]
    default_allowed_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]

    return AppConfig(
        accounts_file=os.getenv("APPLE_CALENDAR_ACCOUNTS_FILE", "config/accounts.yaml"),
        default_account_id=os.getenv("APPLE_CALENDAR_DEFAULT_ACCOUNT_ID") or None,
        transport=os.getenv("MCP_TRANSPORT", "stdio"),
        host=os.getenv("MCP_HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8080")),
        path=os.getenv("MCP_PATH", "/mcp"),
        allowed_hosts=default_allowed_hosts + _parse_csv_env(os.getenv("MCP_ALLOWED_HOSTS")),
        allowed_origins=default_allowed_origins + _parse_csv_env(
            os.getenv("MCP_ALLOWED_ORIGINS")
        ),
        caldav_url=os.getenv("APPLE_CALENDAR_CALDAV_URL", "https://caldav.icloud.com/"),
        debug_http=_parse_bool_env(os.getenv("APPLE_CALENDAR_DEBUG_HTTP")),
        debug_http_body_max_bytes=int(os.getenv("APPLE_CALENDAR_DEBUG_HTTP_BODY_MAX_BYTES", "8192")),
        oidc=OIDCConfig(
            mode="disabled",
            issuer=None,
            discovery_url=None,
            jwks_url=None,
            audience=None,
            resource_url=None,
            accounts_read_scope="accounts.read",
            calendar_read_scope="calendar.read",
            calendar_write_scope="calendar.write",
            access_rules=[],
        ),
    )
