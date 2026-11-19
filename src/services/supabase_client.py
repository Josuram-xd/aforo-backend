"""Minimal Supabase REST / Auth client built on the standard library (urllib).

The transport is injected (``http``), so tests never touch the network.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Sequence
from typing import Any

# (method, url, headers, body) -> (status, response body)
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, bytes]]


class SupabaseError(Exception):
    """Supabase answered with an error status (or could not be reached: status 502)."""

    def __init__(self, status: int, body: Any = None) -> None:
        super().__init__(f"supabase error {status}")
        self.status = status
        self.body = body


def urllib_transport(
    method: str, url: str, headers: dict[str, str], body: bytes | None
) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise SupabaseError(502, str(error)) from error


class SupabaseClient:
    def __init__(
        self,
        url: str,
        publishable_key: str,
        service_role_key: str = "",
        transport: Transport = urllib_transport,
    ) -> None:
        self.url = url.rstrip("/")
        self.publishable_key = publishable_key
        self.service_role_key = service_role_key
        self._transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        token: str | None = None,
        service: bool = False,
        query: Sequence[tuple[str, str]] = (),
        payload: Any = None,
        prefer: str | None = None,
    ) -> Any:
        """Call Supabase and return the parsed JSON (None for empty bodies).

        With ``service=True`` the service-role key is used as credential; otherwise the
        caller's ``token`` (so RLS applies) and the publishable key as ``apikey``.
        """
        if service:
            key = self.service_role_key
            headers = {"apikey": key, "Authorization": f"Bearer {key}"}
        else:
            headers = {
                "apikey": self.publishable_key,
                "Authorization": f"Bearer {token or self.publishable_key}",
            }
        headers["Accept"] = "application/json"
        body = None
        if payload is not None:
            body = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if prefer:
            headers["Prefer"] = prefer
        url = self.url + path + ("?" + urllib.parse.urlencode(list(query)) if query else "")
        status, raw = self._transport(method, url, headers, body)
        try:
            data = json.loads(raw) if raw else None
        except ValueError:
            data = None
        if status >= 400:
            raise SupabaseError(status, data)
        return data

    def get_user(self, token: str) -> dict[str, Any] | None:
        """Validate an access token. Returns the auth user, or None when rejected."""
        try:
            return self.request("GET", "/auth/v1/user", token=token)
        except SupabaseError as error:
            if error.status in (401, 403):
                return None
            raise

    def select(
        self, table: str, query: Sequence[tuple[str, str]], token: str, *, service: bool = False
    ) -> list[dict[str, Any]]:
        """PostgREST GET. ``query`` holds select/filter/order/limit/offset pairs."""
        return self.request(
            "GET", f"/rest/v1/{table}", token=token, service=service, query=query
        ) or []

    def rpc(self, name: str, payload: dict[str, Any], token: str) -> Any:
        return self.request("POST", f"/rest/v1/rpc/{name}", token=token, payload=payload)

    def invite_user(self, email: str, redirect_to: str) -> dict[str, Any]:
        """Send an invite e-mail (service role). Returns the created auth user."""
        query = [("redirect_to", redirect_to)]
        return self.request(
            "POST", "/auth/v1/invite", service=True, query=query, payload={"email": email}
        )

    def upsert(self, table: str, row: dict[str, Any], on_conflict: str) -> None:
        """Insert or update one row as service role."""
        self.request(
            "POST",
            f"/rest/v1/{table}",
            service=True,
            query=[("on_conflict", on_conflict)],
            payload=row,
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def delete(self, table: str, query: Sequence[tuple[str, str]]) -> None:
        """Delete rows matching the PostgREST filters as service role."""
        self.request(
            "DELETE", f"/rest/v1/{table}", service=True, query=query, prefer="return=minimal"
        )
