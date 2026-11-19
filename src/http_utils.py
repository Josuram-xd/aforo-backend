"""Request/response value objects, JSON helpers and CORS for the HTTP API v2 payload."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any

JSON_TYPE = "application/json; charset=utf-8"
ALLOW_HEADERS = "authorization, x-client-info, apikey, content-type"


class HttpError(Exception):
    """Raise from any route to stop with a JSON error. ``message`` is user-facing (Spanish)."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Request:
    method: str
    path: str
    headers: dict[str, str] = field(default_factory=dict)  # lower-case names
    query: dict[str, str] = field(default_factory=dict)
    body: str = ""
    path_params: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> Request:
        http = event.get("requestContext", {}).get("http", {})
        body = event.get("body") or ""
        if event.get("isBase64Encoded") and body:
            body = base64.b64decode(body).decode("utf-8", errors="replace")
        return cls(
            method=(http.get("method") or "GET").upper(),
            path=http.get("path") or event.get("rawPath") or "/",
            headers={k.lower(): v for k, v in (event.get("headers") or {}).items()},
            query=dict(event.get("queryStringParameters") or {}),
            body=body,
        )

    def json_body(self) -> dict[str, Any]:
        """Parse the body as a JSON object or raise a 400."""
        try:
            data = json.loads(self.body)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise HttpError(400, "El cuerpo no es JSON válido.")
        return data


@dataclass
class Response:
    status: int
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def to_lambda(self, extra_headers: dict[str, str]) -> dict[str, Any]:
        return {
            "statusCode": self.status,
            "headers": {**extra_headers, **self.headers},
            "body": self.body,
        }


def json_response(status: int, payload: Any) -> Response:
    return Response(status, json.dumps(payload, ensure_ascii=False), {"Content-Type": JSON_TYPE})


def error_response(status: int, message: str) -> Response:
    return json_response(status, {"error": message})


def cors_headers(origin: str | None, allowed_origins: list[str]) -> dict[str, str]:
    """Echo the Origin only when it is explicitly allowed; otherwise no CORS headers."""
    headers = {"Vary": "Origin"}
    if origin and origin in allowed_origins:
        headers.update(
            {
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Headers": ALLOW_HEADERS,
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Expose-Headers": "Content-Disposition",
                "Access-Control-Max-Age": "86400",
            }
        )
    return headers
