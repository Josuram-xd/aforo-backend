import json

from app import Deps, handle
from services.supabase_client import SupabaseClient
from tests.helpers import event, login


def script(transport, existing=None, invite=(200, {"id": "new-user"}), upsert_status=200):
    login(transport, roles=("admin",), user_id="admin-1")
    transport.on("GET", "/rest/v1/roles", [{"id": "role-teacher"}])
    transport.on(
        "GET", "/rest/v1/profiles", [{"is_active": True}] if existing is None else existing
    )
    transport.on("POST", "/auth/v1/invite", invite[1], status=invite[0])
    transport.on("POST", "/rest/v1/user_roles", None, status=upsert_status)
    transport.on("DELETE", "/rest/v1/user_roles", None)
    transport.on("DELETE", "/auth/v1/admin/users/new-user", None)


def profile_lookup_returns(transport, rows_by_email):
    """The auth step and the duplicate check both read profiles; answer by query."""

    def answer(url, body):
        return (200, rows_by_email if "email=eq." in url else [{"is_active": True}])

    transport.on("GET", "/rest/v1/profiles", answer)


def test_invite_success_normalises_email_and_assigns_role(deps, transport):
    script(transport)
    profile_lookup_returns(transport, [])
    status, body = invite_raw(deps, transport)
    assert (status, body) == (
        200,
        {"userId": "new-user", "email": "new@example.com", "role": "teacher"},
    )
    upsert = next(
        c for c in transport.calls if c["method"] == "POST" and c["path"].endswith("user_roles")
    )
    assert upsert["body"] == {
        "user_id": "new-user",
        "role_id": "role-teacher",
        "granted_by": "admin-1",
    }
    cleanup = next(c for c in transport.calls if c["method"] == "DELETE")
    assert "role_id=neq.role-teacher" in cleanup["url"]
    assert cleanup["headers"]["Authorization"] == "Bearer svc"


def invite_raw(deps, transport, body=None, origin=None):
    payload = {"email": "  New@Example.COM ", "role": "teacher"} if body is None else body
    result = handle(
        event(method="POST", path="/invite-user", body=json.dumps(payload), origin=origin), deps
    )
    return result["statusCode"], json.loads(result["body"])


def test_existing_profile_is_409_and_nothing_is_invited(deps, transport):
    script(transport)
    profile_lookup_returns(transport, [{"id": "x"}])
    assert invite_raw(deps, transport)[0] == 409
    assert not any(c["path"] == "/auth/v1/invite" for c in transport.calls)


def test_auth_conflict_is_409(deps, transport):
    script(transport, invite=(422, {"error_code": "email_exists"}))
    profile_lookup_returns(transport, [])
    assert invite_raw(deps, transport)[0] == 409


def test_role_failure_rolls_back_the_new_account(deps, transport):
    script(transport, upsert_status=500)
    profile_lookup_returns(transport, [])
    status, body = invite_raw(deps, transport)
    assert status == 500 and body["error"].startswith("No se pudo invitar")
    assert any(
        c["method"] == "DELETE" and c["path"] == "/auth/v1/admin/users/new-user"
        for c in transport.calls
    )


def test_validation(deps, transport):
    script(transport)
    profile_lookup_returns(transport, [])
    assert invite_raw(deps, transport, {"email": "nope", "role": "admin"})[0] == 400
    assert invite_raw(deps, transport, {"email": "a@b.co", "role": "root"})[0] == 400
    assert invite_raw(deps, transport, {"email": 5, "role": "admin"})[0] == 400


def test_only_admins_and_service_key_required(deps, transport):
    login(transport, roles=("teacher",))
    result = handle(event(method="POST", path="/invite-user", body="{}"), deps)
    assert result["statusCode"] == 403
    no_key = Deps(SupabaseClient("https://supabase.test", "pub", "", transport), [], "")
    login(transport, roles=("admin",))
    result = handle(event(method="POST", path="/invite-user", body="{}"), no_key)
    assert result["statusCode"] == 503


def test_redirect_uses_allowed_origin_only(deps, transport):
    script(transport)
    profile_lookup_returns(transport, [])
    invite_raw(deps, transport, origin="https://evil.test")
    call = next(c for c in transport.calls if c["path"] == "/auth/v1/invite")
    assert "redirect_to=https%3A%2F%2Fapp.test%2Fauth%2Fcallback" in call["url"]
    transport.calls.clear()
    script(transport)
    profile_lookup_returns(transport, [])
    invite_raw(deps, transport, origin="https://app.test")
    assert any("app.test%2Fauth%2Fcallback" in c["url"] for c in transport.calls)
