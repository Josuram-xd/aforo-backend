import json

from app import handle
from tests.helpers import event


def test_health_is_public(deps):
    result = handle(event(path="/health", token=None), deps)
    assert result["statusCode"] == 200
    assert json.loads(result["body"]) == {"status": "ok"}
