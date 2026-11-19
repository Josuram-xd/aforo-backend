"""GET /courses/{courseId}/roster?q=<name prefix>: course roster sorted through a BST."""

from __future__ import annotations

import re
import unicodedata
from typing import TYPE_CHECKING

from http_utils import HttpError, Request, Response, json_response
from structures.binary_search_tree import BinarySearchTree

if TYPE_CHECKING:
    from app import Deps
    from auth import AuthContext

UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)
Q_MAX = 120


def name_key(name: str) -> str:
    """Case- and accent-insensitive sort key: 'Ángela' sorts and matches like 'angela'."""
    decomposed = unicodedata.normalize("NFKD", name.strip())
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


def build_roster(rows: list[dict], prefix: str | None) -> tuple[list[dict], int, int]:
    """Insert students into a BST by name key; return (students, height, size)."""
    tree = BinarySearchTree()
    for row in rows:
        student = row.get("students")
        if isinstance(student, list):
            student = student[0] if student else None
        if not student:
            continue
        tree.insert(
            name_key(student["full_name"]),
            {
                "id": student["id"],
                "fullName": student["full_name"],
                "studentCode": student.get("student_code"),
                "presence": student.get("presence", "OUT"),
                "enrollmentStatus": "active" if student.get("is_active", True) else "inactive",
            },
        )
    found = tree.prefix_range(name_key(prefix)) if prefix else tree.in_order()
    return list(found), tree.height(), len(tree)


def handle(req: Request, deps: Deps, auth: AuthContext | None) -> Response:
    course_id = req.path_params["courseId"]
    if not UUID.match(course_id):
        raise HttpError(400, "'courseId' debe ser un UUID.")
    prefix = req.query.get("q", "")
    if len(prefix) > Q_MAX:
        raise HttpError(400, "El parámetro 'q' es demasiado largo.")

    rows = deps.client.select(
        "course_students",
        [
            ("select", "students(id,full_name,student_code,presence,is_active)"),
            ("course_id", f"eq.{course_id}"),
            ("order", "student_id.asc"),
            ("limit", "5000"),
        ],
        auth.token,
    )
    students, height, size = build_roster(rows, prefix)
    return json_response(
        200,
        {
            "courseId": course_id,
            "structure": "binary_search_tree",
            "height": height,
            "size": size,
            "students": students,
        },
    )
