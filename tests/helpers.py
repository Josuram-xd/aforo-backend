"""Test helpers: a scripted fake Supabase transport and event builders."""

import json


class FakeTransport:
    """Answers by (method, path) with queued/static JSON; records every call."""

    def __init__(self):
        self.routes = {}  # (method, path) -> (status, payload) or callable(url, body)
        self.calls = []

    def on(self, method, path, payload, status=200):
        self.routes[(method, path)] = payload if callable(payload) else (status, payload)

    def __call__(self, method, url, headers, body):
        path = url.split("supabase.test", 1)[1].split("?")[0]
        self.calls.append(
            {
                "method": method,
                "url": url,
                "path": path,
                "headers": headers,
                "body": json.loads(body) if body else None,
            }
        )
        handler = self.routes.get((method, path))
        if handler is None:
            return 404, b'{"message":"no route in fake"}'
        status, payload = handler(url, body) if callable(handler) else handler
        return status, json.dumps(payload).encode() if payload is not None else b""


def login(transport, roles=("viewer",), active=True, user_id="u1"):
    """Script the three calls made by authenticate()."""
    transport.on("GET", "/auth/v1/user", {"id": user_id})
    transport.on("GET", "/rest/v1/profiles", [{"is_active": active}])
    transport.on("GET", "/rest/v1/user_roles", [{"roles": {"code": r}} for r in roles])


def event(method="GET", path="/health", query=None, body=None, token="tok", origin=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    return {
        "requestContext": {"http": {"method": method, "path": path}},
        "headers": headers,
        "queryStringParameters": query,
        "body": body,
    }
