"""GET|POST /export-events: CSV export of a classroom's events (admin/teacher).

Parameters come from the query string (GET) or a JSON body (POST): from, to, classroomId.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from http_utils import HttpError, Request, Response
from routes.roster import UUID

if TYPE_CHECKING:
    from app import Deps
    from auth import AuthContext

MAX_RANGE = timedelta(days=31)
PAGE_SIZE = 1000
BOGOTA = timezone(timedelta(hours=-5))  # Colombia has no daylight saving time
ISO_DATETIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d{1,6})?)?(Z|[+-]\d{2}:\d{2})$"
)
# CSV injection (OWASP): a cell that a spreadsheet could read as a formula, even after spaces.
FORMULA = re.compile(r"^\s*[=+\-@]|^[\t\r]")
HEADER = ["estudiante", "direccion", "metodo", "confianza", "fecha_hora_bogota"]


def csv_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    guarded = bool(FORMULA.match(text))
    if guarded:
        text = "'" + text
    if guarded or re.search(r'[",\r\n]', text):
        text = '"' + text.replace('"', '""') + '"'
    return text


def csv_row(values: list[Any]) -> str:
    return ",".join(csv_cell(v) for v in values) + "\r\n"


def format_bogota(iso: str) -> str:
    """'2026-10-13 08:30:00' in America/Bogota."""
    moment = datetime.fromisoformat(iso).astimezone(BOGOTA)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not ISO_DATETIME.match(value):
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC)
    except ValueError:
        return None


def _params(req: Request) -> dict[str, Any]:
    return req.query if req.method == "GET" else req.json_body()


def _iso_utc(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def handle(req: Request, deps: Deps, auth: AuthContext | None) -> Response:
    if req.method not in ("GET", "POST"):
        raise HttpError(405, "Método no permitido.")
    params = _params(req)
    start, end = parse_iso(params.get("from")), parse_iso(params.get("to"))
    classroom_id = params.get("classroomId")
    if start is None or end is None:
        raise HttpError(400, "'from' y 'to' deben ser fechas ISO 8601 con zona horaria.")
    if end <= start:
        raise HttpError(400, "'to' debe ser posterior a 'from'.")
    if end - start > MAX_RANGE:
        raise HttpError(400, "El rango máximo es de 31 días.")
    if not isinstance(classroom_id, str) or not UUID.match(classroom_id):
        raise HttpError(400, "'classroomId' debe ser un UUID.")

    from_iso, to_iso = _iso_utc(start), _iso_utc(end)
    # Audit first: if it cannot be recorded, nothing is exported.
    deps.client.rpc(
        "log_access",
        {
            "p_action": "EXPORT",
            "p_resource": f"events classroom={classroom_id} from={from_iso} to={to_iso}",
        },
        auth.token,
    )

    lines = ["﻿" + csv_row(HEADER)]
    offset = 0
    while True:
        page = deps.client.select(
            "events",
            [
                ("select", "id,occurred_at,direction,method,confidence,students(full_name)"),
                ("classroom_id", f"eq.{classroom_id}"),
                ("occurred_at", f"gte.{from_iso}"),
                ("occurred_at", f"lt.{to_iso}"),
                ("order", "occurred_at.asc,id.asc"),
                ("limit", str(PAGE_SIZE)),
                ("offset", str(offset)),
            ],
            auth.token,
        )
        for row in page:
            student = row.get("students")
            if isinstance(student, list):
                student = student[0] if student else None
            lines.append(
                csv_row(
                    [
                        (student or {}).get("full_name") or "Desconocido",
                        row["direction"],
                        row["method"],
                        row["confidence"],
                        format_bogota(row["occurred_at"]),
                    ]
                )
            )
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE

    return Response(
        200,
        "".join(lines),
        {
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": f'attachment; filename="eventos-{from_iso[:10]}.csv"',
            "Cache-Control": "no-store",
        },
    )
