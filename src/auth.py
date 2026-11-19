"""Authentication and role checks against Supabase (the caller's token, so RLS applies)."""

from __future__ import annotations

import re
from dataclasses import dataclass

from http_utils import HttpError
from services.supabase_client import SupabaseClient, SupabaseError

ROLES = ("admin", "teacher", "viewer")
_BEARER = re.compile(r"^Bearer\s+(\S+)$", re.IGNORECASE)


@dataclass
class AuthContext:
    user_id: str
    token: str
    roles: list[str]


def authenticate(
    headers: dict[str, str], client: SupabaseClient, allowed_roles: tuple[str, ...]
) -> AuthContext:
    """Validate the bearer token, require an active account and one of ``allowed_roles``."""
    match = _BEARER.match(headers.get("authorization", ""))
    if not match:
        raise HttpError(401, "Falta el token de autenticación.")
    token = match.group(1)
    try:
        user = client.get_user(token)
        if not user or not user.get("id"):
            raise HttpError(401, "Token inválido o vencido.")
        user_id = user["id"]
        profile = client.select(
            "profiles", [("select", "is_active"), ("id", f"eq.{user_id}")], token
        )
        rows = client.select(
            "user_roles", [("select", "roles(code)"), ("user_id", f"eq.{user_id}")], token
        )
    except SupabaseError as error:
        raise HttpError(502, "No se pudo verificar tu sesión. Intenta de nuevo.") from error

    # A deactivated account can still read its own user_roles through RLS: check is_active.
    if not profile or profile[0].get("is_active") is not True:
        raise HttpError(403, "Tu cuenta está desactivada.")
    roles = []
    for row in rows:
        embedded = row.get("roles")
        if isinstance(embedded, list):
            embedded = embedded[0] if embedded else None
        code = embedded.get("code") if isinstance(embedded, dict) else None
        if code in ROLES:
            roles.append(code)
    if not set(roles) & set(allowed_roles):
        raise HttpError(403, "No tienes permisos para esta acción.")
    return AuthContext(user_id, token, roles)
