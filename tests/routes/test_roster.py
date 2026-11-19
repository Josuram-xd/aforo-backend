import json

from app import handle
from routes.roster import name_key
from tests.helpers import event, login

COURSE = "11111111-1111-4111-8111-111111111111"


def row(i, name, presence="OUT", enrollment="enrolled"):
    return {
        "students": {
            "id": i,
            "full_name": name,
            "student_code": f"C{i}",
            "presence": presence,
            "enrollment_status": enrollment,
        }
    }


def roster(deps, transport, query=None, path=None):
    login(transport)
    transport.on(
        "GET",
        "/rest/v1/course_students",
        [
            row("1", "Zoe Díaz"),
            row("2", "ángela Ruiz", "IN"),
            row("3", "Andres Lopez", enrollment="pending"),
            row("4", "angela Mora"),
        ],
    )
    result = handle(event(path=path or f"/courses/{COURSE}/roster", query=query), deps)
    return result["statusCode"], json.loads(result["body"])


def test_name_key_ignores_case_and_accents():
    assert name_key("  ÁNGELA   Ruiz ") == "angela ruiz"


def test_roster_is_sorted_by_normalised_name(deps, transport):
    status, body = roster(deps, transport)
    assert status == 200
    assert body["structure"] == "binary_search_tree"
    assert body["size"] == 4 and body["height"] >= 3
    assert [s["fullName"] for s in body["students"]] == [
        "Andres Lopez",
        "angela Mora",
        "ángela Ruiz",
        "Zoe Díaz",
    ]
    assert body["students"][0]["enrollmentStatus"] == "pending"
    assert body["students"][2]["presence"] == "IN"


def test_prefix_search(deps, transport):
    _, body = roster(deps, transport, query={"q": "Ang"})
    assert [s["id"] for s in body["students"]] == ["4", "2"]
    assert body["size"] == 4  # size is the whole roster, not the filtered list
    _, empty = roster(deps, transport, query={"q": "xyz"})
    assert empty["students"] == []


def test_uses_user_token_and_course_filter(deps, transport):
    roster(deps, transport)
    call = transport.calls[-1]
    assert call["headers"]["Authorization"] == "Bearer tok"
    assert f"course_id=eq.{COURSE}" in call["url"]


def test_bad_course_id_and_long_query(deps, transport):
    assert roster(deps, transport, path="/courses/abc/roster")[0] == 400
    assert roster(deps, transport, query={"q": "a" * 500})[0] == 400
