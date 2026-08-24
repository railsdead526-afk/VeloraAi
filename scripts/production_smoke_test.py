#!/usr/bin/env python3
"""Run non-destructive checks against a deployed VeloraAi instance."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def fetch(base_url: str, path: str, timeout: float) -> tuple[int, dict]:
    request = Request(f"{base_url.rstrip('/')}{path}", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return response.status, payload
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} returned HTTP {exc.code}: {body[:300]}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach {path}: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", help="Deployed VeloraAi API base URL")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    checks = {
        "/api/v1/health": "ok",
        "/api/v1/ready": "ready",
    }
    failures: list[str] = []
    for path, expected_status in checks.items():
        try:
            status_code, payload = fetch(args.base_url, path, args.timeout)
            actual_status = payload.get("status")
            if status_code != 200 or actual_status != expected_status:
                failures.append(f"{path}: expected HTTP 200/status={expected_status}, got HTTP {status_code}/status={actual_status}")
            else:
                print(f"PASS {path} status={actual_status}")
        except RuntimeError as exc:
            failures.append(str(exc))

    if failures:
        for failure in failures:
            print(f"FAIL {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
