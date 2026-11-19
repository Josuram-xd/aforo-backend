import json

import pytest

from app import handle
from http_utils import HttpError
from routes.session_report import build_report
from tests.helpers import event, login

SESSION = "22222222-2222-4222-8222-222222222222"


def ev(n, direction, student, minute, name=None):
    return {
        "id": f"00000000-0000-4000-8000-{n:012d}",
        "direction": direction,
        "method": "FACE",
        "student_id": student,
        "occurred_at": f"2026-11-19T10:{minute:02d}:00Z",
        "students": {"full_name": name} if name else None,
    }


EVENTS = [
    ev(1, "ENTRY", "a", 0, "Ana"),
    ev(2, "ENTRY", "b", 1, "Beto"),
    ev(3, "ENTRY", None, 2),  # unknown person
    ev(4, "EXIT", "a", 3, "Ana"),
    ev(5, "EXIT", "c", 4, "Carla"),  # exit without entry
    ev(6, "ENTRY", "b", 5, "Beto"),  # second entry without exit
    ev(7, "ENTRY", "a", 6, "Ana"),
    ev(8, "ENTRY", "d", 7, "Dani"),
    ev(9, "ENTRY", "e", 8, "Eli"),
    ev(10, "ENTRY", "f", 9, "Fer"),
]


def test_arrival_order_is_first_entry_fifo():
    report = build_report(EVENTS, None, "next", 50)
    assert [a["studentId"] for a in report["arrivalOrder"]] == ["a", "b", "d", "e", "f"]
    assert report["arrivalOrder"][0]["firstEntryAt"] == "2026-11-19T10:00:00Z"


def test_inside_now_and_anomalies():
    report = build_report(EVENTS, None, "next", 50)
    assert [s["studentId"] for s in report["insideNow"]] == ["a", "b", "d", "e", "f"]
    beto = report["insideNow"][1]
    assert beto["since"] == "2026-11-19T10:05:00Z"  # latest entry
    assert report["anomalies"] == [
        {
            "studentId": "b",
            "fullName": "Beto",
            "kind": "ENTRY_WITHOUT_EXIT",
            "at": "2026-11-19T10:01:00Z",
        },
        {
            "studentId": "c",
            "fullName": "Carla",
            "kind": "EXIT_WITHOUT_ENTRY",
            "at": "2026-11-19T10:04:00Z",
        },
    ]


def test_last_entries_top_five_lifo():
    report = build_report(EVENTS, None, "next", 50)
    assert [e["fullName"] for e in report["lastEntries"]] == ["Fer", "Eli", "Dani", "Ana", "Beto"]


def test_peak_counts_unknown_people_and_never_goes_negative():
    report = build_report(EVENTS, None, "next", 50)
    # occupancy: 1,2,3,2,1(exit c),2,3,4,5,6 -> peak 6 at the last event
    assert report["peak"] == {"count": 6, "at": "2026-11-19T10:09:00Z"}
    assert build_report([ev(1, "EXIT", "a", 0)], None, "next", 5)["peak"] == {
        "count": 0,
        "at": None,
    }


def test_timeline_pages_both_ways():
    first = build_report(EVENTS, None, "next", 4)["timeline"]
    assert len(first["items"]) == 4
    assert first["prevCursor"] is None and first["nextCursor"] == first["items"][-1]["id"]
    assert first["items"][2]["fullName"] is None  # unknown student
    second = build_report(EVENTS, first["nextCursor"], "next", 4)["timeline"]
    assert [i["id"][-2:] for i in second["items"]] == ["05", "06", "07", "08"]
    assert second["prevCursor"] is not None
    back = build_report(EVENTS, second["prevCursor"], "prev", 4)["timeline"]
    assert back["items"] == first["items"]
    assert back["prevCursor"] is None


def test_unknown_cursor_is_400():
    with pytest.raises(HttpError) as caught:
        build_report(EVENTS, "00000000-0000-4000-8000-999999999999", "next", 5)
    assert caught.value.status == 400


def call(deps, transport, query=None, sessions=None, events=None, path=None):
    login(transport)
    transport.on(
        "GET",
        "/rest/v1/class_sessions",
        [
            {
                "id": SESSION,
                "title": "Clase",
                "starts_at": "s",
                "ends_at": "e",
                "course_id": "c",
                "classroom_id": "r",
            }
        ]
        if sessions is None
        else sessions,
    )
    transport.on("GET", "/rest/v1/events", EVENTS if events is None else events)
    result = handle(event(path=path or f"/sessions/{SESSION}/report", query=query), deps)
    return result["statusCode"], json.loads(result["body"])


def test_route_returns_contract_shape(deps, transport):
    status, body = call(deps, transport, {"limit": "3"})
    assert status == 200
    assert body["session"] == {
        "id": SESSION,
        "title": "Clase",
        "startsAt": "s",
        "endsAt": "e",
        "courseId": "c",
        "classroomId": "r",
    }
    assert set(body) == {
        "session",
        "arrivalOrder",
        "insideNow",
        "anomalies",
        "lastEntries",
        "peak",
        "timeline",
    }
    assert len(body["timeline"]["items"]) == 3


def test_route_validation_and_not_found(deps, transport):
    assert call(deps, transport, sessions=[])[0] == 404
    assert call(deps, transport, {"dir": "up"})[0] == 400
    assert call(deps, transport, {"limit": "0"})[0] == 400
    assert call(deps, transport, {"limit": "x"})[0] == 400
    assert call(deps, transport, {"cursor": "nope"})[0] == 400
    assert call(deps, transport, path="/sessions/zzz/report")[0] == 400
