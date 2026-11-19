"""GET /sessions/{sessionId}/report: entry/exit report of one class session.

Events are replayed in chronological order through the course data structures:
Queue (arrival order), per-student Stack (inside / anomalies), global Stack (last entries)
and DoublyLinkedList (cursor-paged timeline).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from http_utils import HttpError, Request, Response, json_response
from routes.roster import UUID
from structures.doubly_linked_list import DoublyLinkedList
from structures.queue import Queue
from structures.stack import Stack

if TYPE_CHECKING:
    from app import Deps
    from auth import AuthContext

PAGE = 1000  # PostgREST rows per request
MAX_EVENTS = 20000
LAST_ENTRIES = 5
DEFAULT_LIMIT, MAX_LIMIT = 10, 100


def _name(row: dict[str, Any]) -> str | None:
    student = row.get("students")
    if isinstance(student, list):
        student = student[0] if student else None
    return student.get("full_name") if student else None


def build_report(
    events: list[dict[str, Any]], cursor: str | None, direction: str, limit: int
) -> dict[str, Any]:
    """Pure function: ``events`` must be sorted by (occurred_at, id)."""
    timeline = DoublyLinkedList()
    arrivals = Queue()  # first ENTRY per student, FIFO
    seen: set[str] = set()
    names: dict[str, str | None] = {}
    stacks: dict[str, Stack] = {}  # per-student ENTRY stack
    last_entries = Stack()
    anomalies: list[dict[str, Any]] = []
    occupancy = peak = 0
    peak_at: str | None = None

    for event in events:
        student_id, at = event["student_id"], event["occurred_at"]
        name = _name(event)
        timeline.append(
            {
                "id": event["id"],
                "direction": event["direction"],
                "method": event["method"],
                "studentId": student_id,
                "fullName": name,
                "occurredAt": at,
            }
        )
        entering = event["direction"] == "ENTRY"
        if entering:
            occupancy += 1
            last_entries.push({"studentId": student_id, "fullName": name, "at": at})
            if occupancy > peak:
                peak, peak_at = occupancy, at
        else:
            occupancy = max(0, occupancy - 1)
        if student_id is None:
            continue  # unknown people only count towards occupancy and the timeline
        names[student_id] = name
        stack = stacks.setdefault(student_id, Stack())
        if entering:
            if student_id not in seen:
                seen.add(student_id)
                arrivals.enqueue({"studentId": student_id, "fullName": name, "firstEntryAt": at})
            stack.push(at)
        elif stack.is_empty():
            anomalies.append(_anomaly(student_id, name, "EXIT_WITHOUT_ENTRY", at))
        else:
            stack.pop()

    inside_now = []
    for arrival in arrivals:
        stack = stacks[arrival["studentId"]]
        if stack.is_empty():
            continue
        entries = list(stack)  # newest first
        inside_now.append(
            {
                "studentId": arrival["studentId"],
                "fullName": arrival["fullName"],
                "since": entries[0],
            }
        )
        # A second ENTRY without an EXIT in between: the older ones were never closed.
        for stale in entries[1:]:
            anomalies.append(
                _anomaly(arrival["studentId"], arrival["fullName"], "ENTRY_WITHOUT_EXIT", stale)
            )
    anomalies.sort(key=lambda item: item["at"])

    try:
        window = timeline.window(cursor, direction, limit, key=lambda item: item["id"])
    except KeyError:
        raise HttpError(400, "El cursor no corresponde a un evento de esta sesión.") from None
    items = window.items
    return {
        "arrivalOrder": list(arrivals),
        "insideNow": inside_now,
        "anomalies": anomalies,
        "lastEntries": [entry for _, entry in zip(range(LAST_ENTRIES), last_entries, strict=False)],
        "peak": {"count": peak, "at": peak_at},
        "timeline": {
            "items": items,
            "prevCursor": items[0]["id"] if items and window.has_prev else None,
            "nextCursor": items[-1]["id"] if items and window.has_next else None,
        },
    }


def _anomaly(student_id: str, name: str | None, kind: str, at: str) -> dict[str, Any]:
    return {"studentId": student_id, "fullName": name, "kind": kind, "at": at}


def _parse_query(query: dict[str, str]) -> tuple[str | None, str, int]:
    cursor = query.get("cursor") or None
    if cursor is not None and not UUID.match(cursor):
        raise HttpError(400, "'cursor' debe ser un UUID.")
    direction = query.get("dir", "next")
    if direction not in ("next", "prev"):
        raise HttpError(400, "'dir' debe ser next o prev.")
    try:
        limit = int(query.get("limit", DEFAULT_LIMIT))
    except ValueError:
        limit = 0
    if not 1 <= limit <= MAX_LIMIT:
        raise HttpError(400, f"'limit' debe estar entre 1 y {MAX_LIMIT}.")
    return cursor, direction, limit


def _fetch_events(deps: Deps, token: str, session_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    while len(rows) < MAX_EVENTS:
        page = deps.client.select(
            "events",
            [
                ("select", "id,direction,method,student_id,occurred_at,students(full_name)"),
                ("session_id", f"eq.{session_id}"),
                ("order", "occurred_at.asc,id.asc"),
                ("limit", str(PAGE)),
                ("offset", str(len(rows))),
            ],
            token,
        )
        rows.extend(page)
        if len(page) < PAGE:
            break
    return rows


def handle(req: Request, deps: Deps, auth: AuthContext | None) -> Response:
    session_id = req.path_params["sessionId"]
    if not UUID.match(session_id):
        raise HttpError(400, "'sessionId' debe ser un UUID.")
    cursor, direction, limit = _parse_query(req.query)

    sessions = deps.client.select(
        "class_sessions",
        [
            ("select", "id,title,starts_at,ends_at,course_id,classroom_id"),
            ("id", f"eq.{session_id}"),
        ],
        auth.token,
    )
    if not sessions:
        raise HttpError(404, "Sesión no encontrada.")
    session = sessions[0]
    report = build_report(_fetch_events(deps, auth.token, session_id), cursor, direction, limit)
    return json_response(
        200,
        {
            "session": {
                "id": session["id"],
                "title": session["title"],
                "startsAt": session["starts_at"],
                "endsAt": session["ends_at"],
                "courseId": session["course_id"],
                "classroomId": session["classroom_id"],
            },
            **report,
        },
    )
