#!/usr/bin/env python3
"""Smoke-test TomTom Matrix Routing v2 against the school bus-lane stop.

Reads TOMTOM_API_KEY from the environment or a local .env file.
Does not print the key.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from busroutes.config import ConfigError, load_key

SCHOOL = {"latitude": 50.77815986077964, "longitude": 4.8959997390197705}
HOEGAARDEN_CENTRE = {"latitude": 50.7756, "longitude": 4.8894}
MATRIX_URL = "https://api.tomtom.com/routing/matrix/2"


def next_weekday_morning(hour: int, minute: int) -> str:
    brussels = ZoneInfo("Europe/Brussels")
    now = datetime.now(brussels)
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.isoformat(timespec="seconds")


def main() -> int:
    try:
        key = load_key()
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1
    depart_at = next_weekday_morning(7, 15)
    body = {
        "origins": [{"point": SCHOOL}],
        "destinations": [{"point": HOEGAARDEN_CENTRE}],
        "options": {
            "departAt": depart_at,
            "traffic": "live",
            "travelMode": "car",
            "routeType": "fastest",
        },
    }
    request = urllib.request.Request(
        f"{MATRIX_URL}?key={key}",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = json.loads(response.read().decode())
            status = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        print(f"FAIL HTTP {exc.code}", file=sys.stderr)
        print(raw[:2000], file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"FAIL network: {exc.reason}", file=sys.stderr)
        return 1

    cell = (payload.get("data") or [{}])[0]
    summary = cell.get("routeSummary") or {}
    stats = payload.get("statistics") or {}
    print("OK Matrix Routing v2")
    print(f"http_status={status}")
    print(f"departAt={depart_at}")
    print(
        "cell="
        f"{summary.get('lengthInMeters')}m "
        f"{summary.get('travelTimeInSeconds')}s "
        f"delay={summary.get('trafficDelayInSeconds')}s"
    )
    print(f"times={summary.get('departureTime')} -> {summary.get('arrivalTime')}")
    print(
        f"statistics=total:{stats.get('totalCount')} "
        f"ok:{stats.get('successes')} fail:{stats.get('failures')}"
    )
    return 0 if status == 200 and stats.get("successes") else 1


if __name__ == "__main__":
    sys.exit(main())
