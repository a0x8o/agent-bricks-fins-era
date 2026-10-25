"""Identity resolution: OBO user token or app service principal.

Every data call is explicit about which identity it runs as. In OBO mode the
user's forwarded token is used per-request so UC row filters / column masks apply.
The service principal is used only when AUTH_MODE=service_principal or for
app-internal background work (audit logging).
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request

from .config import Settings, get_settings

USER_TOKEN_HEADER = "x-forwarded-access-token"
USER_EMAIL_HEADER = "x-forwarded-email"
USER_NAME_HEADER = "x-forwarded-preferred-username"


@dataclass
class Identity:
    """Resolved caller identity for one request."""

    mode: str  # "obo" | "service_principal" | "mock"
    user: str  # email/username for display + cache keys
    token: str | None  # OBO user token; None in SP/mock mode


def resolve_identity(request: Request, settings: Settings | None = None) -> Identity:
    settings = settings or get_settings()
    user = (
        request.headers.get(USER_EMAIL_HEADER)
        or request.headers.get(USER_NAME_HEADER)
        or "local-dev"
    )
    if settings.mock:
        return Identity(mode="mock", user=user, token=None)
    if settings.obo:
        token = request.headers.get(USER_TOKEN_HEADER)
        if token:
            return Identity(mode="obo", user=user, token=token)
        # Deployed OBO with no forwarded token = misconfiguration; surface it,
        # never silently fall back to the service principal.
        return Identity(mode="obo", user=user, token=None)
    return Identity(mode="service_principal", user=user, token=None)


def user_workspace_client(identity: Identity):
    """WorkspaceClient bound to the caller's identity."""
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.core import Config

    settings = get_settings()
    if identity.mode == "obo" and identity.token:
        cfg = Config(host=settings.host, token=identity.token)
        return WorkspaceClient(config=cfg)
    return WorkspaceClient()
