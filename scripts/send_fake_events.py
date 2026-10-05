"""Send fake aforo events to a deployed API to test without cameras.

Uses only the standard library. Examples:

    python scripts/send_fake_events.py https://abc123.execute-api.us-east-1.amazonaws.com
    python scripts/send_fake_events.py <api-url> --count 20 --interval 2 --person-id <uuid>
    python scripts/send_fake_events.py <api-url> --dry-run

Events follow the contract in ARCHITECTURE.md section 4. Directions are chosen so the room
never goes below 0 people (an EXIT is only sent while someone is "inside").
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from uuid import uuid4


def build_event(direction: str, person_id: str | None = None, person_name: str | None = None):
    """Return a valid event payload; identified (FACE) when person_id is given, else BODY_ONLY."""
    return {
        "eventId": str(uuid4()),
        "personId": person_id,
        "personName": person_name if person_id else None,
        "direction": direction,
        "cameraOutsideId": "camera-outside",
        "cameraInsideId": "camera-inside",
        "confidence": round(random.uniform(0.6, 0.99), 2),
        "method": "FACE" if person_id else "BODY_ONLY",
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def request(method: str, url: str, headers: dict[str, str], payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except urllib.error.URLError as e:
        return None, str(e.reason)


def parse_headers(values: list[str]) -> dict[str, str]:
    headers = {}
    for value in values:
        name, sep, content = value.partition(":")
        if not sep or not name.strip():
            raise SystemExit(f"Header inválido '{value}': usa el formato 'Nombre: valor'.")
        headers[name.strip()] = content.strip()
    return headers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Envía eventos de prueba a POST /events.")
    parser.add_argument("api_url", help="URL base del API, sin barra final")
    parser.add_argument("--count", type=int, default=10, help="cantidad de eventos (default 10)")
    parser.add_argument("--interval", type=float, default=1.0, help="segundos entre eventos")
    parser.add_argument("--person-id", help="personId existente en el roster (opcional)")
    parser.add_argument("--person-name", default="Persona de prueba")
    parser.add_argument(
        "--header",
        action="append",
        default=[],
        metavar="'Nombre: valor'",
        help="header extra en POST /events (repetible)",
    )
    parser.add_argument(
        "--read-header",
        action="append",
        default=[],
        metavar="'Nombre: valor'",
        help="header extra en GET /aforo (por ejemplo 'Authorization: Bearer <token>')",
    )
    parser.add_argument("--dry-run", action="store_true", help="solo imprime los eventos")
    args = parser.parse_args(argv)

    base_url = args.api_url.rstrip("/")
    post_headers = parse_headers(args.header)
    read_headers = parse_headers(args.read_header)

    inside = 0
    failures = 0
    for i in range(1, args.count + 1):
        # Favor entries a bit so the room fills up, but never exit from an empty room.
        direction = "EXIT" if inside > 0 and random.random() < 0.4 else "ENTRY"
        payload = build_event(direction, args.person_id, args.person_name)

        if args.dry_run:
            print(json.dumps(payload))
            continue

        status, body = request("POST", f"{base_url}/events", post_headers, payload)
        ok = status in (200, 201)
        failures += not ok
        if ok:
            inside += 1 if direction == "ENTRY" else -1
        print(f"[{i}/{args.count}] {direction:5} -> {status} {body}")
        if i < args.count:
            time.sleep(args.interval)

    if not args.dry_run:
        status, body = request("GET", f"{base_url}/aforo", read_headers)
        print(f"GET /aforo -> {status} {body}")
        print(f"Aforo esperado de esta tanda: {inside} (sumado al que hubiera antes).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
