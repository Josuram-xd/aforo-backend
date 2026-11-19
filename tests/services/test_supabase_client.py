import json
import urllib.parse

import pytest

from services.supabase_client import SupabaseClient, SupabaseError


class FakeTransport:
    def __init__(self, status=200, body=b"[]"):
        self.status, self.body, self.calls = status, body, []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        return self.status, self.body


def make(transport):
    return SupabaseClient("https://x.supabase.co/", "pub", "svc", transport)


def test_select_uses_user_token_and_publishable_key():
    transport = FakeTransport(body=b'[{"id": 1}]')
    rows = make(transport).select("students", [("select", "id"), ("id", "eq.1")], "tok")
    method, url, headers, _ = transport.calls[0]
    assert rows == [{"id": 1}]
    assert method == "GET"
    assert url == "https://x.supabase.co/rest/v1/students?select=id&id=eq.1"
    assert headers["Authorization"] == "Bearer tok"
    assert headers["apikey"] == "pub"


def test_service_requests_use_service_key():
    transport = FakeTransport(body=b"")
    make(transport).delete("user_roles", [("user_id", "eq.u")])
    _, _, headers, _ = transport.calls[0]
    assert headers["Authorization"] == "Bearer svc"
    assert headers["apikey"] == "svc"


def test_get_user_returns_none_when_rejected():
    assert make(FakeTransport(401, b'{"msg":"bad"}')).get_user("t") is None
    assert make(FakeTransport(200, b'{"id":"u"}')).get_user("t") == {"id": "u"}


def test_get_user_propagates_server_errors():
    with pytest.raises(SupabaseError):
        make(FakeTransport(500, b"")).get_user("t")


def test_errors_carry_status_and_body():
    with pytest.raises(SupabaseError) as caught:
        make(FakeTransport(422, b'{"code":"email_exists"}')).invite_user("a@b.co", "https://r")
    assert caught.value.status == 422
    assert caught.value.body == {"code": "email_exists"}


def test_invite_sends_email_and_redirect():
    transport = FakeTransport(body=b'{"id": "u1"}')
    user = make(transport).invite_user("a@b.co", "https://app/auth/callback")
    _, url, _, body = transport.calls[0]
    assert user == {"id": "u1"}
    assert urllib.parse.urlparse(url).path == "/auth/v1/invite"
    assert "redirect_to=https%3A%2F%2Fapp%2Fauth%2Fcallback" in url
    assert json.loads(body) == {"email": "a@b.co"}


def test_upsert_sets_conflict_target():
    transport = FakeTransport(body=b"")
    make(transport).upsert("user_roles", {"user_id": "u"}, "user_id,role_id")
    _, url, headers, _ = transport.calls[0]
    assert "on_conflict=user_id%2Crole_id" in url
    assert "merge-duplicates" in headers["Prefer"]


def test_rpc_posts_payload():
    transport = FakeTransport(body=b"null")
    make(transport).rpc("log_access", {"p_action": "EXPORT"}, "tok")
    method, url, _, body = transport.calls[0]
    assert (method, url.endswith("/rest/v1/rpc/log_access")) == ("POST", True)
    assert json.loads(body) == {"p_action": "EXPORT"}
