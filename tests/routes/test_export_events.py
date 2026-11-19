import json

import pytest

from app import handle
from routes.export_events import csv_cell, format_bogota
from tests.helpers import event, login

CLASSROOM = "33333333-3333-4333-8333-333333333333"
QUERY = {"from": "2026-11-19T00:00:00Z", "to": "2026-11-20T00:00:00Z", "classroomId": CLASSROOM}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ana", "Ana"),
        ("=1+1", '"\'=1+1"'),
        ("  =cmd", '"\'  =cmd"'),
        ("+57", '"\'+57"'),
        ("-x", '"\'-x"'),
        ("@sum", '"\'@sum"'),
        ("\tx", '"\'\tx"'),
        ('a "b", c', '"a ""b"", c"'),
        (None, ""),
        (0.95, "0.95"),
    ],
)
def test_csv_cell(raw, expected):
    assert csv_cell(raw) == expected


def test_format_bogota():
    assert format_bogota("2026-10-13T13:30:00+00:00") == "2026-10-13 08:30:00"


def export(deps, transport, query=QUERY, method="GET", body=None, rows=None, roles=("teacher",)):
    login(transport, roles=roles)
    transport.on("POST", "/rest/v1/rpc/log_access", None)
    transport.on("GET", "/rest/v1/events", rows if rows is not None else [])
    ev = event(
        method=method, path="/export-events", query=query if method == "GET" else None, body=body
    )
    return handle(ev, deps)


def test_csv_output_and_audit(deps, transport):
    rows = [
        {
            "id": "1",
            "occurred_at": "2026-11-19T15:00:00+00:00",
            "direction": "ENTRY",
            "method": "FACE",
            "confidence": 0.95,
            "students": {"full_name": "=Ana"},
        },
        {
            "id": "2",
            "occurred_at": "2026-11-19T15:05:00+00:00",
            "direction": "EXIT",
            "method": "BODY_ONLY",
            "confidence": 0.5,
            "students": None,
        },
    ]
    result = export(deps, transport, rows=rows)
    assert result["statusCode"] == 200
    assert result["headers"]["Content-Type"] == "text/csv; charset=utf-8"
    assert 'filename="eventos-2026-11-19.csv"' in result["headers"]["Content-Disposition"]
    assert result["body"] == (
        "﻿estudiante,direccion,metodo,confianza,fecha_hora_bogota\r\n"
        '"\'=Ana",ENTRY,FACE,0.95,2026-11-19 10:00:00\r\n'
        "Desconocido,EXIT,BODY_ONLY,0.5,2026-11-19 10:05:00\r\n"
    )
    audit = next(c for c in transport.calls if c["path"].endswith("log_access"))
    assert audit["body"]["p_action"] == "EXPORT"
    assert CLASSROOM in audit["body"]["p_resource"]


def test_post_body_and_pagination(deps, transport):
    full = [
        {
            "id": str(i),
            "occurred_at": "2026-11-19T15:00:00Z",
            "direction": "ENTRY",
            "method": "FACE",
            "confidence": 1,
            "students": None,
        }
        for i in range(1000)
    ]
    pages = [full, full[:2]]
    login(transport, roles=("admin",))
    transport.on("POST", "/rest/v1/rpc/log_access", None)
    transport.on("GET", "/rest/v1/events", lambda url, body: (200, pages.pop(0)))
    result = handle(event(method="POST", path="/export-events", body=json.dumps(QUERY)), deps)
    assert result["statusCode"] == 200
    assert result["body"].count("\r\n") == 1 + 1002


@pytest.mark.parametrize(
    "patch",
    [
        {"from": "2026-11-19"},
        {"to": "2026-11-18T00:00:00Z"},
        {"to": "2026-12-25T00:00:00Z"},
        {"classroomId": "x"},
    ],
)
def test_validation_errors(deps, transport, patch):
    result = export(deps, transport, query={**QUERY, **patch})
    assert result["statusCode"] == 400


def test_bad_post_body_and_roles(deps, transport):
    assert export(deps, transport, method="POST", body="nope")["statusCode"] == 400
    assert export(deps, transport, roles=("viewer",))["statusCode"] == 403


def test_nothing_is_exported_when_audit_fails(deps, transport):
    login(transport, roles=("teacher",))
    transport.on("POST", "/rest/v1/rpc/log_access", None, status=500)
    result = handle(event(path="/export-events", query=QUERY), deps)
    assert result["statusCode"] == 502
    assert not any(c["path"] == "/rest/v1/events" for c in transport.calls)
