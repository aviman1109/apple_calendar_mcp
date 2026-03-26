"""OIDC stub - provides get_current_principal for auth-disabled mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class SimplePrincipal:
    """Anonymous principal when auth is disabled."""

    id: str = "anonymous"


def get_current_principal(ctx: Any | None = None) -> SimplePrincipal:
    """Return anonymous principal when auth is disabled."""
    return SimplePrincipal()
