"""Authorization policy stub - allows all accounts when auth is disabled."""

from __future__ import annotations


class AuthorizationPolicy:
    """Stub policy that allows all accounts when auth is disabled."""

    def __init__(self, oidc_config: object, account_ids: list[str]) -> None:
        self._account_ids = set(account_ids)

    def get_allowed_account_ids(self, principal: object) -> set[str]:
        """Return all configured account IDs when auth is disabled."""
        return self._account_ids.copy()
