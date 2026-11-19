"""GET /health: liveness probe, no auth."""

from __future__ import annotations

from typing import TYPE_CHECKING

from http_utils import Request, Response, json_response

if TYPE_CHECKING:
    from app import Deps
    from auth import AuthContext


def handle(req: Request, deps: Deps, auth: AuthContext | None) -> Response:
    return json_response(200, {"status": "ok"})
