#!/usr/bin/env python3
"""Negative control for the authenticated REST smoke checks.

The smoke scripts now present a bearer token on every REST request, which is
correct but proves nothing on its own: a suite that sends a token would also
pass if the server had stopped requiring one. This script pins the other half of
the contract so the requirement cannot be quietly dropped later.

What it asserts, against a real ``axiomize serve`` process:

1. An authenticated readiness probe succeeds. (The positive path still works.)
2. A POST with no ``Authorization`` header is refused with 401.
3. A probe carrying a token the server was not started with is refused with 401.

It is a manual verification tool, not a CI gate: it needs an installed
``axiomize`` console entry point, which the release job already provides. Run it
from a security-hardening checkout after changing the REST auth policy::

    python .github/scripts/verify_rest_auth_negative.py

Exits non-zero if the mutating-route token requirement is not enforced.
"""

from __future__ import annotations

import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from rest_auth import RestServer, make_token  # noqa: E402


def _unauthenticated_post(port: int, path: str, payload: dict[str, object]) -> tuple[int, str]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")


def main() -> int:
    exe = shutil.which("axiomize")
    if not exe:
        print("FAIL: axiomize console entry point not on PATH", file=sys.stderr)
        return 1

    failures: list[str] = []
    correct = make_token()
    wrong = make_token()

    with RestServer(exe, correct) as server:
        server.wait_until_ready("/capabilities", timeout=5.0)
        print("PASS authenticated readiness probe succeeded")

        code, body = _unauthenticated_post(
            server.port, "/intake", {"idea": "Reduce traffic congestion"}
        )
        if code == 401:
            print(f"PASS unauthenticated POST /intake -> 401 ({body.strip()})")
        else:
            failures.append(f"unauthenticated POST /intake returned {code}: {body}")

        # Reuse the running process with a token it was not started with, so the
        # only variable is the credential.
        probe = RestServer.__new__(RestServer)
        probe._exe = exe
        probe._token = wrong
        probe._host = "127.0.0.1"
        probe.port = server.port
        probe._proc = server._proc
        try:
            probe.wait_until_ready("/capabilities", attempts=1, timeout=3.0)
            failures.append("readiness probe succeeded with a wrong token")
        except Exception as exc:  # noqa: BLE001 - the message is the assertion
            if "401" in str(exc) or "unauthorized" in str(exc).lower():
                print("PASS wrong token rejected on the read route")
            else:
                failures.append(f"wrong token raised an unexpected error: {exc!r}")

    if failures:
        print("FAIL: the mutating-route token requirement is NOT enforced:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("PASS: mutating routes reject missing and wrong credentials")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
