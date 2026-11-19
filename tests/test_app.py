import json

import pytest

from app import Route, handle
from http_utils import HttpError, json_response
from tests.helpers import event, login


def ok(req, deps, auth):
    return json_response(200, {"user": auth.user_id if auth else None, "params": req.path_params})


def boom(req, deps, auth):
    raise RuntimeError("secret detail")


def denied(req, deps, auth):
    raise HttpError(409, "Conflicto.")


ROUTES = [
    Route("GET", "/open", ok, None),
    Route("GET", "/items/{itemId}", ok, ("admin", "teacher")),
    Route("GET", "/boom", boom, None),
    Route("GET", "/conflict", denied, None),
]


def call(deps, **kwargs):
    result = handle(event(**kwargs), deps, ROUTES)
    return result["statusCode"], json.loads(result["body"] or "null"), result["headers"]


def test_public_route_and_path_params(deps, transport):
    assert call(deps, path="/open", token=None)[:2] == (200, {"user": None, "params": {}})
    login(transport, roles=("teacher",))
    status, body, _ = call(deps, path="/items/42")
    assert (status, body) == (200, {"user": "u1", "params": {"itemId": "42"}})


def test_missing_and_invalid_token(deps, transport):
    status, body, _ = call(deps, path="/items/1", token=None)
    assert status == 401 and "token" in body["error"]
    transport.on("GET", "/auth/v1/user", {"msg": "bad"}, status=401)
    assert call(deps, path="/items/1")[0] == 401


def test_inactive_account_and_wrong_role(deps, transport):
    login(transport, roles=("teacher",), active=False)
    assert call(deps, path="/items/1")[0] == 403
    login(transport, roles=("viewer",))
    status, body, _ = call(deps, path="/items/1")
    assert status == 403 and body["error"] == "No tienes permisos para esta acción."


def test_highest_matching_role_is_enough(deps, transport):
    login(transport, roles=("viewer", "admin"))
    assert call(deps, path="/items/1")[0] == 200


def test_supabase_failure_during_auth_is_502(deps, transport):
    transport.on("GET", "/auth/v1/user", None, status=500)
    assert call(deps, path="/items/1")[0] == 502


def test_404_405_and_error_shapes(deps):
    assert call(deps, path="/nope")[0] == 404
    assert call(deps, method="POST", path="/open")[0] == 405
    assert call(deps, path="/conflict")[:2] == (409, {"error": "Conflicto."})
    status, body, _ = call(deps, path="/boom")
    assert (status, body) == (500, {"error": "Error interno."})


def test_cors_only_for_allowed_origin(deps):
    _, _, allowed = call(deps, path="/open", origin="https://app.test")
    assert allowed["Access-Control-Allow-Origin"] == "https://app.test"
    _, _, other = call(deps, path="/open", origin="https://evil.test")
    assert "Access-Control-Allow-Origin" not in other


def test_preflight_returns_204(deps):
    request = event(method="OPTIONS", path="/items/1", origin="https://app.test")
    result = handle(request, deps, ROUTES)
    assert result["statusCode"] == 204
    assert "GET" in result["headers"]["Access-Control-Allow-Methods"]


def test_invalid_json_body_helper():
    from http_utils import Request

    with pytest.raises(HttpError) as caught:
        Request("POST", "/x", body="[1]").json_body()
    assert caught.value.status == 400
