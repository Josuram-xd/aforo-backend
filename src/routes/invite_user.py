"""POST /invite-user: invite a new account by e-mail and assign its role (admin only).

Port of the former Supabase Edge Function. Uses the service-role key, so it is the only
route that bypasses RLS.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from auth import ROLES
from http_utils import HttpError, Request, Response, json_response
from services.supabase_client import SupabaseError

if TYPE_CHECKING:
    from app import Deps
    from auth import AuthContext

logger = logging.getLogger()
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CALLBACK_PATH = "/auth/callback"
FAILED = "No se pudo invitar al usuario. Intenta de nuevo."
EXISTS = "Ya existe un usuario con ese correo."


def redirect_to(req: Request, deps: Deps) -> str:
    """INVITE_REDIRECT_TO if set, else the caller's origin when allowed, else the first one.

    Never an arbitrary caller-supplied URL. It must be listed in Supabase Auth > URL
    Configuration > Redirect URLs.
    """
    if deps.invite_redirect_to:
        return deps.invite_redirect_to
    origin = req.headers.get("origin")
    if origin in deps.allowed_origins:
        return origin + CALLBACK_PATH
    return deps.allowed_origins[0] + CALLBACK_PATH if deps.allowed_origins else ""


def handle(req: Request, deps: Deps, auth: AuthContext | None) -> Response:
    client = deps.client
    if not client.service_role_key:
        raise HttpError(503, "La invitación de usuarios no está configurada en el servidor.")
    body = req.json_body()
    raw_email = body.get("email")
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
    if not email or len(email) > 254 or not EMAIL.match(email):
        raise HttpError(400, "Correo inválido.")
    role = body.get("role")
    if not isinstance(role, str) or role not in ROLES:
        raise HttpError(400, "El rol debe ser admin, teacher o viewer.")

    user_id: str | None = None
    try:
        role_rows = client.select(
            "roles", [("select", "id"), ("code", f"eq.{role}")], "", service=True
        )
        if not role_rows:
            raise RuntimeError("role lookup")
        # Only brand-new accounts: re-inviting an unconfirmed account could let whoever
        # registered that e-mail first in once the real owner accepts.
        if client.select(
            "profiles", [("select", "id"), ("email", f"eq.{email}")], "", service=True
        ):
            raise HttpError(409, EXISTS)
        try:
            invited = client.invite_user(email, redirect_to(req, deps))
        except SupabaseError as error:
            code = error.body.get("error_code") if isinstance(error.body, dict) else None
            if code == "email_exists" or error.status == 422:
                raise HttpError(409, EXISTS) from error
            raise
        user_id = (invited or {}).get("id")
        if not user_id:
            raise RuntimeError("invite without user")

        # The signup trigger gives every new user the 'viewer' role; replace it.
        role_id = role_rows[0]["id"]
        client.upsert(
            "user_roles",
            {"user_id": user_id, "role_id": role_id, "granted_by": auth.user_id},
            "user_id,role_id",
        )
        client.delete("user_roles", [("user_id", f"eq.{user_id}"), ("role_id", f"neq.{role_id}")])
    except HttpError:
        raise
    except (SupabaseError, RuntimeError) as error:
        logger.error("invite-user failed: %s", type(error).__name__)
        if user_id:
            _roll_back(deps, user_id)
        raise HttpError(500, FAILED) from error
    return json_response(200, {"userId": user_id, "email": email, "role": role})


def _roll_back(deps: Deps, user_id: str) -> None:
    """Delete the half-created account so the admin can retry (otherwise: 409 forever)."""
    try:
        deps.client.delete_auth_user(user_id)
    except SupabaseError:
        logger.error("invite-user rollback failed")
