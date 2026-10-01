import json

from handlers.health import handler


def test_health_returns_ok():
    response = handler({}, None)

    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
    assert json.loads(response["body"]) == {"status": "ok"}
