#!/usr/bin/env python3
"""Shared helper for the release smoke scripts' authenticated REST checks.

Why this exists
---------------
``axiomize.server.rest_server`` authenticates every mutating request, including
on a loopback bind: a loopback socket is not a private channel, and a web page
in the user's browser can send a "simple" cross-origin POST to
``http://127.0.0.1:<port>`` without a preflight and without an
``Authorization`` header. ``start_server`` therefore always ends up with a token
-- one the operator supplied, or a 256-bit one it minted and exposed as
``server.generated_token``.

The release smoke scripts start the real ``axiomize serve`` console entry point
as a subprocess, so they cannot read ``server.generated_token`` from memory.
They supply their own token instead, through the documented
``AXIOMIZE_REST_TOKEN`` environment variable that ``axiomize serve`` already
reads (``--auth-token-env``), and send it back as a bearer credential.

Two consequences of supplying the token rather than letting the server mint
one, both of which this module handles and the callers get for free:

* ``require_token_for_reads`` defaults to True for an operator-supplied token,
  so the readiness probes on ``GET /capabilities`` are authenticated too. Every
  request made through :class:`RestServer` carries the header, GET and POST
  alike.
* A wrong or missing credential is a hard failure, so a smoke run that reports
  success has demonstrably presented the token.

This is not a bypass and adds no permissive flag: there is no code path here
that starts an unauthenticated server or suppresses a 401. If the security
requirement is broken, these scripts fail.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

#: The environment variable ``axiomize serve`` reads its bearer token from.
#: Matches the default of the ``--auth-token-env`` CLI flag.
TOKEN_ENV_VAR = "AXIOMIZE_REST_TOKEN"

#: ``start_server`` rejects a token shorter than this for a non-loopback bind.
#: 32 urlsafe base64 bytes is ~43 characters, comfortably clear of the bound.
_TOKEN_BYTES = 32


class RestAuthFailure(RuntimeError):
    """The server refused a request, or never became reachable."""


def make_token() -> str:
    """Return a fresh bearer token for one smoke run.

    Generated per run rather than hard-coded so a leaked log cannot be replayed
    against a live server, and so nothing in this repository becomes a
    long-lived credential.
    """
    return secrets.token_urlsafe(_TOKEN_BYTES)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class RestServer:
    """A running ``axiomize serve`` process, started with a known token.

    Use as a context manager; the server is always terminated, including when
    the body raises, so a failing smoke run cannot leave a listener behind on a
    CI runner.
    """

    def __init__(self, exe: str, token: str, *, host: str = "127.0.0.1") -> None:
        self._exe = exe
        self._token = token
        self._host = host
        self.port: int = 0
        self._proc: subprocess.Popen[str] | None = None

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self.port}/v1"

    def __enter__(self) -> RestServer:
        self.port = _free_port()
        # The token is passed through the environment rather than argv so it does
        # not appear in the process list of a shared CI runner.
        env = dict(os.environ)
        env[TOKEN_ENV_VAR] = self._token
        self._proc = subprocess.Popen(
            [self._exe, "serve", "--host", self._host, "--port", str(self.port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        return self

    def __exit__(self, *exc_info: object) -> None:
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def _stderr(self) -> str:
        """Return captured stderr, or "" while the server is still running.

        A blocking ``read()`` on the live pipe would deadlock: the server writes
        nothing more and never exits, so the read waits forever. Only drained
        after the process has terminated.
        """
        proc = self._proc
        if proc is None or proc.stderr is None:
            return ""
        if proc.poll() is None:
            return "<server still running; stderr not drained>"
        return proc.stderr.read() or ""

    def request_json(
        self,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float = 10.0,
    ) -> dict[str, Any]:
        """GET or POST ``path`` with the bearer credential attached.

        ``payload`` present means POST. The ``Authorization`` header is sent on
        every request, including the GET readiness probes, because an
        operator-supplied token gates reads as well.
        """
        headers = {"Authorization": f"Bearer {self._token}"}
        data: bytes | None = None
        method = "GET"
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            # The server also rejects CORS-"simple" content types on writes; the
            # smoke contract is JSON, so say so explicitly.
            headers["Content-Type"] = "application/json"
            method = "POST"

        url = f"{self.base_url}{path}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        if not isinstance(body, dict):
            raise RestAuthFailure(f"{method} {path} returned non-object JSON: {body!r}")
        return body

    def wait_until_ready(
        self,
        path: str = "/capabilities",
        *,
        attempts: int = 50,
        delay: float = 0.1,
        timeout: float = 5.0,
    ) -> dict[str, Any]:
        """Poll ``path`` until the authenticated server answers.

        A 401 here is a real failure and is raised immediately rather than
        retried: retrying an authentication error only turns one clear message
        into a timeout.
        """
        last: Exception | None = None
        for _ in range(attempts):
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                raise RestAuthFailure(
                    f"REST server exited early ({proc.returncode}): {self._stderr()}"
                )
            try:
                return self.request_json(path, timeout=timeout)
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 415):
                    body = exc.read().decode("utf-8", "replace")
                    raise RestAuthFailure(
                        f"REST {path} rejected an authenticated probe with HTTP {exc.code}: {body}\n"
                        f"token source: {TOKEN_ENV_VAR}\n"
                        f"server stderr: {self._stderr()}"
                    ) from exc
                last = exc
            except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
                # Connection refused while the socket is still coming up.
                last = exc
            time.sleep(delay)
        raise RestAuthFailure(f"REST server never became ready: {last!r}")


def assert_rejects_unauthenticated(server: RestServer, path: str, payload: dict[str, Any]) -> None:
    """Prove the mutating route still refuses an anonymous request.

    The smoke run must not be able to pass by accident if the security
    requirement is ever weakened, so the negative case is asserted explicitly:
    the same POST without an ``Authorization`` header has to come back 401.
    """
    request = urllib.request.Request(
        f"{server.base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            body = response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return
        raise RestAuthFailure(
            f"unauthenticated POST {path} returned HTTP {exc.code}, expected 401"
        ) from exc
    raise RestAuthFailure(
        f"unauthenticated POST {path} was accepted with HTTP 200: {body}. "
        "The mutating-route token requirement is not being enforced."
    )
