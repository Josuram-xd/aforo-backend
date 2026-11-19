"""Lambda entry point: one function behind an API Gateway HTTP API (payload v2).

``handler`` wires configuration from the environment; ``handle`` is pure enough to be
tested with an injected Supabase client.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from auth import AuthContext, authenticate
from http_utils import HttpError, Request, Response, cors_headers, error_response
from routes import health
from services.supabase_client import SupabaseClient, SupabaseError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


@dataclass
class Deps:
    client: SupabaseClient
    allowed_origins: list[str] = field(default_factory=list)
    invite_redirect_to: str = ""


RouteFn = Callable[[Request, Deps, "AuthContext | None"], Response]


@dataclass
class Route:
    method: str
    pattern: str  # e.g. /courses/{courseId}/roster
    fn: RouteFn
    roles: tuple[str, ...] | None  # None = public

    def match(self, method: str, path: str) -> dict[str, str] | None:
        if method != self.method:
            return None
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", self.pattern)
        found = re.fullmatch(regex, path.rstrip("/") or "/")
        return found.groupdict() if found else None


ROUTES: list[Route] = [
    Route("GET", "/health", health.handle, None),
]


def dispatch(req: Request, deps: Deps, routes: list[Route]) -> Response:
    for route in routes:
        params = route.match(req.method, req.path)
        if params is None:
            continue
        req.path_params = params
        auth = None
        if route.roles is not None:
            auth = authenticate(req.headers, deps.client, route.roles)
        return route.fn(req, deps, auth)
    if any(r.match(r.method, req.path) is not None for r in routes):
        raise HttpError(405, "Método no permitido.")
    raise HttpError(404, "Ruta no encontrada.")


def handle(event: dict[str, Any], deps: Deps, routes: list[Route] | None = None) -> dict[str, Any]:
    req = Request.from_event(event)
    cors = cors_headers(req.headers.get("origin"), deps.allowed_origins)
    if req.method == "OPTIONS":
        return Response(204).to_lambda(cors)
    try:
        response = dispatch(req, deps, ROUTES if routes is None else routes)
    except HttpError as error:
        response = error_response(error.status, error.message)
    except SupabaseError as error:
        logger.error("supabase error status=%s", error.status)
        response = error_response(502, "Error al consultar la base de datos.")
    except Exception as error:  # noqa: BLE001 - last resort, never leak details
        logger.error("unhandled %s", type(error).__name__)
        response = error_response(500, "Error interno.")
    return response.to_lambda(cors)


_deps: Deps | None = None


def _load_deps() -> Deps:
    global _deps
    if _deps is None:
        origins = [o.strip() for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
        _deps = Deps(
            client=SupabaseClient(
                os.environ["SUPABASE_URL"],
                os.environ["SUPABASE_PUBLISHABLE_KEY"],
                os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""),
            ),
            allowed_origins=origins,
            invite_redirect_to=os.environ.get("INVITE_REDIRECT_TO", ""),
        )
    return _deps


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return handle(event, _load_deps())
