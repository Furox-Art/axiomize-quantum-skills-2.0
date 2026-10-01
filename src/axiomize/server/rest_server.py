"""REST API adapter (API v1).

Stdlib-only HTTP layer over shared application services. Legacy SIR/logistic
payloads remain supported while Model IR payloads use the general engine.

Security boundary:
- the bind defaults to loopback (127.0.0.1);
- **every mutating request requires a bearer token, including on loopback**;
- read routes are gated whenever the operator supplied their own token;
- non-loopback binding requires *both* ``allow_remote=True`` and an auth token;
- request bodies, concurrency, connection time and run-file access are bounded;
- run identifiers are confined beneath a configured run root.

Why every mutating request is authenticated, even on loopback
-------------------------------------------------------------
A loopback bind is not a private channel. Any process on the host, and any web
page the user has open, can send a request to ``http://127.0.0.1:<port>``. A
browser refuses to *read* a cross-origin response, but it will happily *send* a
"simple" request whose ``Content-Type`` is ``text/plain`` without any preflight,
and it will not attach an ``Authorization`` header cross-origin at all. This
API exposes solve, fit, falsify and approval-gated Monte Carlo routes, so
leaving them credential-free on loopback made them drivable from a web page.

Two independent gates close that:

1. ``start_server`` never returns a server without a token. When the operator
   supplies none, a 256-bit token is minted and exposed as
   ``server.generated_token``; ``axiomize serve`` prints it to stderr.
2. ``do_POST`` refuses any request whose ``Content-Type`` is a CORS "simple"
   value before it compares credentials, so a forged cross-origin request is
   rejected as malformed.

Read gating
------------
``do_GET`` requires the token when -- and only when -- the operator supplied
one (``--auth-token`` / ``--auth-token-env``), or when ``require_token_for_reads``
is set explicitly. When Axiomize minted the token itself, reads stay open so
the local discovery workflow and the release smoke contract keep working
without change.

That leaves recorded run contents readable by other local processes and user
accounts in the default loopback mode. A browser cannot exploit it, because it
cannot read a cross-origin response at all, but a co-resident process can.
Operators who share a host should pass an explicit ``auth_token``, which turns
on read gating as well. Constructing ``BoundedThreadingHTTPServer`` directly
with ``auth_token=None`` still fails closed on mutating routes.
"""


from __future__ import annotations

import hmac
import ipaddress
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from axiomize.limits import MAX_JSON_BYTES
from axiomize.runs.state import RunState, resolve_run_directory

_MAX_CONCURRENT_REQUESTS = 32
_DEFAULT_CONNECTION_TIMEOUT_S = 30.0

# Token generated when the operator did not supply one. 32 random bytes is 256
# bits of entropy, rendered as 43 urlsafe-base64 characters.
_GENERATED_TOKEN_BYTES = 32

# Content types a browser can send cross-origin without a CORS preflight. A
# request carrying one of these did not come from a JSON API client, so it is
# refused before authentication is even considered.
_CSRF_SIMPLE_CONTENT_TYPES = frozenset({
    "text/plain",
    "application/x-www-form-urlencoded",
    "multipart/form-data",
    "text/html",
})
_JSON_CONTENT_TYPE = "application/json"


class RequestTooLarge(ValueError):
    pass


def _read_json(handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    raw_length = handler.headers.get("Content-Length")
    if raw_length is None:
        return {}
    try:
        length = int(raw_length)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length < 0:
        raise ValueError("Content-Length cannot be negative")
    if length > MAX_JSON_BYTES:
        raise RequestTooLarge(f"request body exceeds hard limit of {MAX_JSON_BYTES} bytes")
    if length == 0:
        return {}
    raw = handler.rfile.read(length)
    if len(raw) != length:
        raise ValueError("request body ended before Content-Length bytes were received")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON request body: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")
    return payload


def _send(handler: BaseHTTPRequestHandler, code: int, payload: Any) -> None:
    body = json.dumps(payload, default=str, allow_nan=False).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.wfile.write(body)


def _content_type(handler: BaseHTTPRequestHandler) -> str:
    raw = handler.headers.get("Content-Type", "") or ""
    return raw.split(";", 1)[0].strip().lower()


def _is_cross_origin_simple(handler: BaseHTTPRequestHandler) -> bool:
    """True when the request shape is one a web page can forge cross-origin.

    A browser attaches no ``Authorization`` header to a cross-origin request
    without first completing a CORS preflight, and it will not preflight a
    request whose ``Content-Type`` is one of the three "simple" values. So a
    cross-origin forging attempt is recognisable by its content type alone, and
    this API only ever speaks JSON.
    """
    return _content_type(handler) in _CSRF_SIMPLE_CONTENT_TYPES


def _strip_api_prefix(path: str) -> str:
    return path[3:] if path.startswith("/v1/") else path


def _has_model_ir(payload: dict[str, Any]) -> bool:
    return isinstance(payload.get("model_ir", payload.get("model")), dict)


def _is_loopback_host(host: str) -> bool:
    normalized = str(host).strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 64

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        *,
        run_root: Path,
        auth_token: str | None,
        max_concurrent_requests: int,
        connection_timeout_s: float,
        generated_token: str | None = None,
        require_token_for_reads: bool = False,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.run_root = run_root.resolve()
        self.auth_token = auth_token
        self.connection_timeout_s = float(connection_timeout_s)
        self._request_slots = threading.BoundedSemaphore(max_concurrent_requests)
        # Non-None only when Axiomize minted the token itself because the
        # operator did not supply one. Callers read it to authenticate; it is
        # never written to a response body or a log line by this module.
        self.generated_token = generated_token
        # True when an operator-supplied token protects reads as well as writes.
        self.require_token_for_reads = bool(require_token_for_reads)

    def get_request(self) -> tuple[Any, Any]:
        request, client_address = super().get_request()
        # Bound slow/incomplete header and body reads. This is deliberately a
        # per-connection wall-clock I/O timeout, independent of compute gates.
        request.settimeout(self.connection_timeout_s)
        return request, client_address

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self._request_slots.acquire(blocking=False):
            try:
                request.sendall(
                    b"HTTP/1.1 503 Service Unavailable\r\n"
                    b"Content-Length: 0\r\nConnection: close\r\n\r\n"
                )
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = "AxiomizeREST/1.1"
    protocol_version = "HTTP/1.1"

    @property
    def _server(self) -> BoundedThreadingHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, *args: Any) -> None:
        pass

    def _authorized(self) -> bool:
        expected = self._server.auth_token
        if expected is None:
            return True
        if not self._server.require_token_for_reads:
            # Axiomize minted this token itself; the operator did not ask for
            # read protection, so local discovery stays open. Writes are gated
            # separately in _require_write_authorized.
            return True
        auth = self.headers.get("Authorization", "")
        supplied = auth[7:] if auth.startswith("Bearer ") else self.headers.get("X-Axiomize-Token", "")
        return bool(supplied) and hmac.compare_digest(str(supplied), expected)

    def _require_authorized(self) -> bool:
        if self._authorized():
            return True
        _send(self, 401, {"error": "unauthorized"})
        return False

    def _require_write_authorized(self) -> bool:
        """Authenticate a mutating request.

        Writes are gated on a token even when the server is bound to loopback
        and no token was configured, because :meth:`start_server` always mints
        one. The order matters: the content-type check runs first so a forged
        cross-origin request is rejected as malformed before any credential
        comparison happens.
        """
        if _is_cross_origin_simple(self):
            _send(self, 415, {
                "error": (
                    f"unsupported Content-Type; this API accepts {_JSON_CONTENT_TYPE} only"
                )
            })
            return False
        if self._server.auth_token is None:
            # Only reachable if a caller constructed the server directly and
            # bypassed start_server. Fail closed rather than serving an
            # unauthenticated mutating surface.
            _send(self, 401, {
                "error": "mutating routes require an auth token; start the server with auth_token"
            })
            return False
        auth = self.headers.get("Authorization", "")
        supplied = auth[7:] if auth.startswith("Bearer ") else self.headers.get("X-Axiomize-Token", "")
        # Writes are always gated, including on a generated token, so this
        # comparison runs even when require_token_for_reads is False.
        if not supplied or not hmac.compare_digest(str(supplied), self._server.auth_token):
            _send(self, 401, {"error": "unauthorized"})
            return False
        return True

    def _load_run(self, run_id: str) -> RunState:
        return RunState.load_under_root(self._server.run_root, unquote(run_id))

    def do_GET(self) -> None:
        from axiomize.application import services

        if not self._require_authorized():
            return
        path = _strip_api_prefix(urlparse(self.path).path)
        if path == "/tools":
            _send(self, 200, services.tools_service())
        elif path == "/capabilities":
            _send(self, 200, services.capabilities_service())
        elif path == "/workflow-policy":
            _send(self, 200, services.workflow_policy_service({}))
        elif path.startswith("/runs/"):
            run_id = path[len("/runs/"):]
            try:
                run = self._load_run(run_id)
            except (OSError, ValueError):
                _send(self, 404, {"error": "run not found or failed integrity checks"})
                return
            _send(self, 200, {"input_hash": run.input_hash(), "results": run.results})
        else:
            _send(self, 404, {"error": "unknown route"})

    def do_POST(self) -> None:
        from axiomize.application import advanced_services, general_services, services, surrogate_services

        if not self._require_write_authorized():
            return
        path = _strip_api_prefix(urlparse(self.path).path)
        try:
            payload = _read_json(self)
            if path == "/intake":
                _send(self, 200, services.intake_service(payload))
            elif path == "/workflow-policy":
                _send(self, 200, services.workflow_policy_service(payload))
            elif path == "/clean-data":
                _send(self, 200, services.clean_data_service(payload))
            elif path == "/compare-runs":
                # Percent-decode the untrusted identifiers in the transport, then
                # let the service apply run-root confinement so the guard lives
                # with the filesystem access rather than only at the edge.
                decoded = dict(payload)
                for field in ("before_dir", "after_dir"):
                    decoded[field] = unquote(str(decoded.get(field, "")))
                _send(self, 200, services.compare_runs_service(decoded, run_root=self._server.run_root))
            elif path == "/model":
                _send(self, 200, general_services.model_plan_service(payload))
            elif path in ("/solve", "/simulate"):
                if _has_model_ir(payload):
                    _send(self, 200, general_services.model_simulate_service(payload))
                else:
                    _send(self, 200, services.solve_sir_service(payload))
            elif path == "/fit":
                if _has_model_ir(payload):
                    _send(self, 200, general_services.model_fit_service(payload))
                else:
                    _send(self, 200, services.fit_logistic_service(payload))
            elif path == "/validate":
                if _has_model_ir(payload):
                    _send(self, 200, general_services.model_validate_service(payload))
                else:
                    _send(self, 200, services.validate_sir_service(payload))
            elif path == "/model/compare":
                _send(self, 200, general_services.model_compare_service(payload))
            elif path == "/model/repair":
                _send(self, 200, general_services.model_repair_service(payload))
            elif path == "/model/export":
                _send(self, 200, general_services.model_export_service(payload))
            elif path == "/model/stability":
                _send(self, 200, general_services.model_stability_service(payload))
            elif path == "/model/validity-scan":
                _send(self, 200, general_services.model_validity_service(payload))
            elif path == "/model/discover":
                _send(self, 200, general_services.model_discovery_service(payload))
            elif path == "/model/experiment-design":
                _send(self, 200, general_services.experiment_design_service(payload))
            elif path == "/model/numerical-verify":
                _send(self, 200, advanced_services.model_numerical_verification_service(payload))
            elif path == "/model/surrogate":
                _send(self, 200, surrogate_services.model_surrogate_service(payload))
            elif path == "/model/uncertainty":
                _send(self, 200, advanced_services.model_uncertainty_service(payload))
            elif path == "/model/bifurcation":
                _send(self, 200, advanced_services.model_bifurcation_service(payload))
            elif path == "/model/stop-check":
                _send(self, 200, advanced_services.model_stopping_service(payload))
            elif path == "/cross-validate":
                _send(self, 200, services.solve_sir_service(payload)["cross_validation"])
            elif path == "/falsify":
                _send(self, 200, services.falsify_service(payload))
            elif path == "/compare":
                _send(self, 200, services.compare_service(payload))
            elif path == "/sensitivity":
                _send(self, 200, services.sensitivity_service(payload))
            elif path == "/uncertainty":
                _send(self, 200, services.uncertainty_service(payload))
            elif path.startswith("/runs/") and path.endswith("/reproduce"):
                run_id = path[len("/runs/"):-len("/reproduce")]
                run = self._load_run(run_id)
                _send(self, 200, {"input_hash": run.input_hash(), "results": run.results})
            else:
                _send(self, 404, {"error": "unknown route"})
        except RequestTooLarge as exc:
            _send(self, 413, {"error": str(exc)})
        except (ValueError, KeyError) as exc:
            _send(self, 400, {"error": str(exc)})
        except Exception:
            _send(self, 500, {"error": "internal server error"})


def start_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    run_root: str | Path = ".",
    allow_remote: bool = False,
    auth_token: str | None = None,
    max_concurrent_requests: int = _MAX_CONCURRENT_REQUESTS,
    connection_timeout_s: float = _DEFAULT_CONNECTION_TIMEOUT_S,
    require_token_for_reads: bool | None = None,
) -> BoundedThreadingHTTPServer:
    """Start the REST server, defaulting to a loopback bind with a token.

    Loopback binding with no operator-supplied token is no longer a
    no-authentication mode: a 256-bit token is minted and attached to the
    returned server as ``generated_token``. Mutating requests must present it.
    This keeps a same-host web page from driving the solve/fit/falsify and
    Monte Carlo routes through a "simple" cross-origin request.

    ``require_token_for_reads`` defaults to True when the operator supplied
    their own ``auth_token`` and False when Axiomize generated one, so local
    read-only discovery keeps working while an explicit token protects reads
    too. Pass it explicitly to override either default.
    """
    host = str(host).strip()
    if not host:
        raise ValueError("host must be non-empty")
    if not _is_loopback_host(host):
        if not allow_remote:
            raise ValueError("non-loopback REST binding requires allow_remote=True")
        if not isinstance(auth_token, str) or len(auth_token) < 16:
            raise ValueError("remote REST binding requires an auth token of at least 16 characters")
    port = int(port)
    if port < 0 or port > 65535:
        raise ValueError("port must be between 0 and 65535")
    max_concurrent_requests = int(max_concurrent_requests)
    if max_concurrent_requests < 1 or max_concurrent_requests > 256:
        raise ValueError("max_concurrent_requests must be between 1 and 256")
    try:
        connection_timeout_s = float(connection_timeout_s)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("connection_timeout_s must be numeric") from exc
    if not 1.0 <= connection_timeout_s <= 300.0:
        raise ValueError("connection_timeout_s must be between 1 and 300 seconds")

    operator_supplied_token = isinstance(auth_token, str) and auth_token != ""
    generated: str | None = None
    effective_token = auth_token
    if effective_token is None:
        # Fail closed: never leave the mutating surface unauthenticated.
        generated = secrets.token_urlsafe(_GENERATED_TOKEN_BYTES)
        effective_token = generated
    if require_token_for_reads is None:
        require_token_for_reads = operator_supplied_token

    root = Path(run_root).expanduser().resolve()
    return BoundedThreadingHTTPServer(
        (host, port), Handler, run_root=root, auth_token=effective_token,
        max_concurrent_requests=max_concurrent_requests,
        connection_timeout_s=connection_timeout_s,
        generated_token=generated,
        require_token_for_reads=bool(require_token_for_reads),
    )
