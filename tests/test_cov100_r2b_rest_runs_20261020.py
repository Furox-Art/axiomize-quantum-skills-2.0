"""Round-2 coverage hardening for the REST transport and run-state persistence.

Every test asserts an observable outcome; no bare calls are used.  Server
internals are exercised directly where HTTP cannot express the branch (slot
exhaustion, transport exceptions) and through a real loopback socket where the
wire contract matters.
"""

from __future__ import annotations

import io
import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from axiomize.limits import MAX_JSON_BYTES, MAX_RUN_JSON_BYTES
from axiomize.runs import state as run_state
from axiomize.runs.state import RunState, resolve_run_directory
from axiomize.server import rest_server


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

class _StubHandler:
    """Minimal BaseHTTPRequestHandler stand-in for pure helper tests."""

    def __init__(self, headers=None, body: bytes = b""):
        self.headers = headers or {}
        self.rfile = io.BytesIO(body)
        self.statuses: list[int] = []
        self.sent_headers: list[tuple[str, str]] = []
        self.wfile = io.BytesIO()
        self.ended = False

    def send_response(self, code):
        self.statuses.append(code)

    def send_header(self, name, value):
        self.sent_headers.append((name, value))

    def end_headers(self):
        self.ended = True


def _server(tmp_path, **overrides):
    settings = {
        "run_root": tmp_path,
        "auth_token": "operator-token-0123456789",
        "max_concurrent_requests": 8,
        "connection_timeout_s": 5.0,
    }
    settings.update(overrides)
    return rest_server.BoundedThreadingHTTPServer(("127.0.0.1", 0), rest_server.Handler, **settings)


def _start_thread(server):
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    return worker


def _stop(server, worker):
    server.shutdown()
    server.server_close()
    worker.join(timeout=10)


def _http(server, route, *, method="GET", payload=None, raw=None, headers=None):
    url = f"http://127.0.0.1:{server.server_port}{route}"
    request_headers = {"Accept": "application/json"}
    request_headers.update(headers or {})
    data = raw if raw is not None else (json.dumps(payload).encode() if payload is not None else None)
    if method == "POST" and data is None:
        data = b""
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        return response.status, json.loads(body) if body else {}


# --------------------------------------------------------------------------- #
# _read_json / _send / small helpers
# --------------------------------------------------------------------------- #

def test_read_json_returns_empty_without_content_length():
    assert rest_server._read_json(_StubHandler()) == {}


def test_read_json_rejects_non_numeric_content_length():
    with pytest.raises(ValueError, match="invalid Content-Length"):
        rest_server._read_json(_StubHandler({"Content-Length": "abc"}))


def test_read_json_rejects_negative_content_length():
    with pytest.raises(ValueError, match="cannot be negative"):
        rest_server._read_json(_StubHandler({"Content-Length": "-4"}))


def test_read_json_rejects_oversized_body():
    with pytest.raises(rest_server.RequestTooLarge, match="hard limit"):
        rest_server._read_json(_StubHandler({"Content-Length": str(MAX_JSON_BYTES + 1)}))


def test_read_json_zero_length_is_empty_object():
    assert rest_server._read_json(_StubHandler({"Content-Length": "0"})) == {}


def test_read_json_rejects_truncated_body():
    with pytest.raises(ValueError, match="ended before"):
        rest_server._read_json(_StubHandler({"Content-Length": "10"}, b"{}"))


def test_read_json_rejects_invalid_utf8():
    with pytest.raises(ValueError, match="invalid JSON request body"):
        rest_server._read_json(_StubHandler({"Content-Length": "2"}, b"\xff\xfe"))


def test_read_json_rejects_non_object_payload():
    raw = b"[1, 2]"
    with pytest.raises(ValueError, match="must be a JSON object"):
        rest_server._read_json(_StubHandler({"Content-Length": str(len(raw))}, raw))


def test_read_json_parses_object_payload():
    raw = b'{"beta": 0.3}'
    assert rest_server._read_json(_StubHandler({"Content-Length": str(len(raw))}, raw)) == {"beta": 0.3}


def test_send_writes_json_headers_and_body():
    handler = _StubHandler()
    rest_server._send(handler, 201, {"ok": True})
    assert handler.statuses == [201]
    assert handler.ended is True
    assert dict(handler.sent_headers)["Content-Type"] == "application/json; charset=utf-8"
    assert handler.wfile.getvalue() == b'{"ok": true}'


def test_content_type_strips_parameters_and_lowercases():
    handler = _StubHandler({"Content-Type": " Application/JSON ; charset=utf-8"})
    assert rest_server._content_type(handler) == "application/json"
    assert rest_server._is_cross_origin_simple(handler) is False


def test_content_type_missing_header_is_empty():
    assert rest_server._content_type(_StubHandler()) == ""


@pytest.mark.parametrize("value", ["text/plain", "application/x-www-form-urlencoded", "multipart/form-data", "text/html"])
def test_csrf_simple_content_types_are_recognised(value):
    assert rest_server._is_cross_origin_simple(_StubHandler({"Content-Type": value})) is True


def test_strip_api_prefix_only_strips_v1():
    assert rest_server._strip_api_prefix("/v1/tools") == "/tools"
    assert rest_server._strip_api_prefix("/v2/tools") == "/v2/tools"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [({"model_ir": {}}, True), ({"model": {}}, True), ({"model_ir": "x"}, False), ({}, False)],
)
def test_has_model_ir_detects_dict_payloads(payload, expected):
    assert rest_server._has_model_ir(payload) is expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [("localhost", True), ("  LOCALHOST ", True), ("127.0.0.1", True), ("::1", True),
     ("10.0.0.1", False), ("not-a-host", False)],
)
def test_is_loopback_host_classifies_hosts(host, expected):
    assert rest_server._is_loopback_host(host) is expected


# --------------------------------------------------------------------------- #
# BoundedThreadingHTTPServer mechanics
# --------------------------------------------------------------------------- #

class _FakeSocket:
    def __init__(self):
        self.timeouts = []
        self.data = b""

    def settimeout(self, value):
        self.timeouts.append(value)

    def sendall(self, data):
        self.data += data


class _FakeRequest:
    def __init__(self):
        self.sent = b""
        self.shutdown_called = False
        self.closed = False

    def sendall(self, data):
        self.sent += data

    def shutdown(self, how):
        self.shutdown_called = True

    def close(self):
        self.closed = True


def test_get_request_applies_connection_timeout(monkeypatch, tmp_path):
    server = _server(tmp_path, connection_timeout_s=7.5)
    fake = _FakeSocket()
    monkeypatch.setattr(rest_server.ThreadingHTTPServer, "get_request", lambda self: (fake, ("1.2.3.4", 9)))
    request, address = server.get_request()
    try:
        assert request is fake
        assert address == ("1.2.3.4", 9)
        assert fake.timeouts == [7.5]
    finally:
        server.server_close()


def test_process_request_refuses_when_all_slots_are_taken(tmp_path):
    server = _server(tmp_path, max_concurrent_requests=1)
    held = server._request_slots.acquire(blocking=False)
    try:
        assert held is True
        request = _FakeRequest()
        server.process_request(request, ("1.2.3.4", 9))
        assert b"503 Service Unavailable" in request.sent
        assert request.shutdown_called is True
        assert request.closed is True
        # The refused request did not release the slot somebody else holds.
        assert server._request_slots.acquire(blocking=False) is False
    finally:
        if held:
            server._request_slots.release()
        server.server_close()


def test_process_request_releases_slot_when_dispatch_raises(monkeypatch, tmp_path):
    server = _server(tmp_path, max_concurrent_requests=1)
    try:
        def explode(self, request, client_address):
            raise RuntimeError("dispatch failed")

        monkeypatch.setattr(rest_server.ThreadingHTTPServer, "process_request", explode)
        with pytest.raises(RuntimeError, match="dispatch failed"):
            server.process_request(_FakeRequest(), ("1.2.3.4", 9))
        assert server._request_slots.acquire(blocking=False) is True
        server._request_slots.release()
    finally:
        server.server_close()


def test_process_request_thread_releases_slot(monkeypatch, tmp_path):
    server = _server(tmp_path, max_concurrent_requests=1)
    try:
        assert server._request_slots.acquire(blocking=False) is True
        monkeypatch.setattr(rest_server.ThreadingHTTPServer, "process_request_thread", lambda self, r, c: None)
        server.process_request_thread(_FakeRequest(), ("1.2.3.4", 9))
        assert server._request_slots.acquire(blocking=False) is True
        server._request_slots.release()
    finally:
        server.server_close()


# --------------------------------------------------------------------------- #
# Handler authentication helpers
# --------------------------------------------------------------------------- #

def _handler_for(server, headers):
    handler = object.__new__(rest_server.Handler)
    handler.headers = headers
    handler.server = server
    return handler


def test_authorized_is_open_when_server_has_no_token(tmp_path):
    server = _server(tmp_path, auth_token=None)
    try:
        assert _handler_for(server, {})._authorized() is True
    finally:
        server.server_close()


def test_authorized_is_open_when_reads_are_not_gated(tmp_path):
    server = _server(tmp_path, require_token_for_reads=False)
    try:
        assert _handler_for(server, {})._authorized() is True
    finally:
        server.server_close()


def test_authorized_requires_matching_bearer_when_reads_gated(tmp_path):
    server = _server(tmp_path, require_token_for_reads=True)
    try:
        assert _handler_for(server, {})._authorized() is False
        assert _handler_for(server, {"Authorization": "Bearer wrong"})._authorized() is False
        assert _handler_for(server, {"Authorization": "Bearer operator-token-0123456789"})._authorized() is True
        assert _handler_for(server, {"X-Axiomize-Token": "operator-token-0123456789"})._authorized() is True
    finally:
        server.server_close()


def test_require_authorized_sends_401(monkeypatch, tmp_path):
    server = _server(tmp_path, require_token_for_reads=True)
    sent = []
    monkeypatch.setattr(rest_server, "_send", lambda h, code, payload: sent.append((code, payload)))
    try:
        assert _handler_for(server, {})._require_authorized() is False
        assert sent == [(401, {"error": "unauthorized"})]
    finally:
        server.server_close()


def test_require_write_authorized_rejects_simple_content_type(monkeypatch, tmp_path):
    server = _server(tmp_path)
    sent = []
    monkeypatch.setattr(rest_server, "_send", lambda h, code, payload: sent.append((code, payload)))
    try:
        handler = _handler_for(server, {"Content-Type": "text/plain"})
        assert handler._require_write_authorized() is False
        assert sent[0][0] == 415
        assert "unsupported Content-Type" in sent[0][1]["error"]
    finally:
        server.server_close()


def test_require_write_authorized_fails_closed_without_token(monkeypatch, tmp_path):
    server = _server(tmp_path, auth_token=None)
    sent = []
    monkeypatch.setattr(rest_server, "_send", lambda h, code, payload: sent.append((code, payload)))
    try:
        handler = _handler_for(server, {"Content-Type": "application/json"})
        assert handler._require_write_authorized() is False
        assert sent[0][0] == 401
    finally:
        server.server_close()


def test_require_write_authorized_rejects_bad_credentials(monkeypatch, tmp_path):
    server = _server(tmp_path)
    sent = []
    monkeypatch.setattr(rest_server, "_send", lambda h, code, payload: sent.append((code, payload)))
    try:
        handler = _handler_for(server, {"Content-Type": "application/json"})
        assert handler._require_write_authorized() is False
        assert sent == [(401, {"error": "unauthorized"})]
    finally:
        server.server_close()


def test_require_write_authorized_accepts_valid_credentials(monkeypatch, tmp_path):
    server = _server(tmp_path)
    sent = []
    monkeypatch.setattr(rest_server, "_send", lambda h, code, payload: sent.append((code, payload)))
    try:
        handler = _handler_for(server, {
            "Content-Type": "application/json",
            "Authorization": "Bearer operator-token-0123456789",
        })
        assert handler._require_write_authorized() is True
        assert sent == []
    finally:
        server.server_close()


def test_handler_log_message_is_silent(tmp_path):
    handler = object.__new__(rest_server.Handler)
    assert handler.log_message("anything", 1) is None
    server = _server(tmp_path)
    try:
        assert _handler_for(server, {})._server is server
    finally:
        server.server_close()


# --------------------------------------------------------------------------- #
# start_server validation and defaults
# --------------------------------------------------------------------------- #

def test_start_server_rejects_empty_host():
    with pytest.raises(ValueError, match="host must be non-empty"):
        rest_server.start_server("   ", 0)


def test_start_server_requires_remote_opt_in():
    with pytest.raises(ValueError, match="allow_remote=True"):
        rest_server.start_server("0.0.0.0", 0)


@pytest.mark.parametrize("token", [None, "", "short"])
def test_start_server_remote_requires_long_token(token):
    with pytest.raises(ValueError, match="at least 16 characters"):
        rest_server.start_server("0.0.0.0", 0, allow_remote=True, auth_token=token)


@pytest.mark.parametrize("port", [-1, 65536])
def test_start_server_rejects_port_out_of_range(port):
    with pytest.raises(ValueError, match="port must be between"):
        rest_server.start_server("127.0.0.1", port, auth_token="operator-token-0123456789")


@pytest.mark.parametrize("limit", [0, 257])
def test_start_server_rejects_bad_concurrency(limit):
    with pytest.raises(ValueError, match="max_concurrent_requests"):
        rest_server.start_server("127.0.0.1", 0, auth_token="operator-token-0123456789",
                                 max_concurrent_requests=limit)


def test_start_server_rejects_non_numeric_timeout():
    with pytest.raises(ValueError, match="connection_timeout_s must be numeric"):
        rest_server.start_server("127.0.0.1", 0, auth_token="operator-token-0123456789",
                                 connection_timeout_s="soon")


@pytest.mark.parametrize("timeout", [0.5, 301.0])
def test_start_server_rejects_timeout_out_of_range(timeout):
    with pytest.raises(ValueError, match="between 1 and 300"):
        rest_server.start_server("127.0.0.1", 0, auth_token="operator-token-0123456789",
                                 connection_timeout_s=timeout)


def test_start_server_mints_token_and_keeps_reads_open():
    server = rest_server.start_server("127.0.0.1", 0)
    try:
        assert server.auth_token
        assert server.generated_token == server.auth_token
        assert server.require_token_for_reads is False
    finally:
        server.server_close()


def test_start_server_operator_token_gates_reads_by_default():
    server = rest_server.start_server("127.0.0.1", 0, auth_token="operator-token-0123456789")
    try:
        assert server.generated_token is None
        assert server.require_token_for_reads is True
    finally:
        server.server_close()


def test_start_server_explicit_read_gate_overrides_default():
    server = rest_server.start_server("127.0.0.1", 0, require_token_for_reads=False)
    try:
        assert server.require_token_for_reads is False
        assert server.generated_token is not None
    finally:
        server.server_close()


# --------------------------------------------------------------------------- #
# Real HTTP routes
# --------------------------------------------------------------------------- #

def test_get_workflow_policy_route(tmp_path):
    server = _server(tmp_path, require_token_for_reads=False)
    worker = _start_thread(server)
    try:
        status, body = _http(server, "/workflow-policy")
        assert status == 200
        assert isinstance(body, dict)
        status, body = _http(server, "/unknown-route")
        assert status == 404
    finally:
        _stop(server, worker)


def test_get_run_returns_hash_and_results(tmp_path):
    run = RunState(problem_definition="p", parameters={"b": 1.0})
    run.add_result("answer", 42)
    run.save(tmp_path / "run-a")
    server = _server(tmp_path, require_token_for_reads=False)
    worker = _start_thread(server)
    try:
        status, body = _http(server, "/runs/run-a")
        assert status == 200
        assert body["input_hash"] == run.input_hash()
        assert body["results"] == {"answer": 42}
        status, _ = _http(server, "/runs/missing")
        assert status == 404
    finally:
        _stop(server, worker)


def test_post_run_reproduce_returns_stored_results(tmp_path):
    run = RunState(problem_definition="p", parameters={"b": 2.0})
    run.add_result("answer", 7)
    run.save(tmp_path / "run-b")
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(
            server, "/runs/run-b/reproduce", method="POST", payload={},
            headers={"Authorization": "Bearer operator-token-0123456789",
                     "Content-Type": "application/json"},
        )
        assert status == 200
        assert body["results"] == {"answer": 7}
    finally:
        _stop(server, worker)


def test_post_unknown_route_returns_404(tmp_path):
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(
            server, "/v1/nope", method="POST", payload={},
            headers={"Authorization": "Bearer operator-token-0123456789",
                     "Content-Type": "application/json"},
        )
        assert status == 404
        assert body == {"error": "unknown route"}
    finally:
        _stop(server, worker)


def test_post_internal_error_is_500_without_leaking_detail(tmp_path, monkeypatch):
    from axiomize.application import services

    def explode(payload):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(services, "intake_service", explode)
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(
            server, "/intake", method="POST", payload={"idea": "x"},
            headers={"Authorization": "Bearer operator-token-0123456789",
                     "Content-Type": "application/json"},
        )
        assert status == 500
        assert body == {"error": "internal server error"}
    finally:
        _stop(server, worker)


def test_post_key_error_is_bad_request(tmp_path, monkeypatch):
    from axiomize.application import services

    def explode(payload):
        raise KeyError("missing")

    monkeypatch.setattr(services, "intake_service", explode)
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(
            server, "/intake", method="POST", payload={"idea": "x"},
            headers={"Authorization": "Bearer operator-token-0123456789",
                     "Content-Type": "application/json"},
        )
        assert status == 400
        assert "missing" in body["error"]
    finally:
        _stop(server, worker)


def test_directly_constructed_server_rejects_plain_text_write(tmp_path):
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(
            server, "/intake", method="POST", raw=b"{}",
            headers={"Authorization": "Bearer operator-token-0123456789",
                     "Content-Type": "text/plain"},
        )
        assert status == 415
        assert "unsupported Content-Type" in body["error"]
    finally:
        _stop(server, worker)


# --------------------------------------------------------------------------- #
# RunState gaps
# --------------------------------------------------------------------------- #

def test_read_json_bounded_surfaces_stat_errors(tmp_path):
    with pytest.raises(ValueError, match="cannot read run-state file"):
        run_state._read_json_bounded(tmp_path / "absent.json")


def test_read_json_bounded_rejects_oversized_file(tmp_path):
    path = tmp_path / "big.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="exceeds hard size limit"):
        run_state._read_json_bounded(path, maximum=1)


def test_read_json_bounded_rejects_invalid_json(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{oops", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid run-state JSON"):
        run_state._read_json_bounded(path)


def test_read_json_bounded_rejects_non_object(tmp_path):
    path = tmp_path / "list.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must contain a JSON object"):
        run_state._read_json_bounded(path)


def test_atomic_write_rejects_oversized_text(tmp_path):
    with pytest.raises(ValueError, match="exceeds hard size limit"):
        run_state._atomic_write_text(tmp_path / "run.json", "x" * (MAX_RUN_JSON_BYTES + 1))
    assert list(tmp_path.iterdir()) == []


def test_atomic_write_cleans_temp_file_when_replace_fails(tmp_path, monkeypatch):
    target = tmp_path / "run.json"

    def fail_replace(src, dst):
        raise OSError("replace failed")

    monkeypatch.setattr(run_state.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        run_state._atomic_write_text(target, "{}")
    assert [p.name for p in tmp_path.iterdir()] == []


@pytest.mark.parametrize("run_id", ["", "   ", 5, None])
def test_resolve_run_directory_requires_non_empty_string(tmp_path, run_id):
    with pytest.raises(ValueError, match="non-empty string"):
        resolve_run_directory(tmp_path, run_id)


def test_resolve_run_directory_rejects_nul(tmp_path):
    with pytest.raises(ValueError, match="contains NUL"):
        resolve_run_directory(tmp_path, "a\x00b")


def test_resolve_run_directory_rejects_absolute(tmp_path):
    with pytest.raises(ValueError, match="absolute run paths"):
        resolve_run_directory(tmp_path, str(tmp_path / "run"))


def test_resolve_run_directory_rejects_escape(tmp_path):
    with pytest.raises(ValueError, match="escapes the configured run root"):
        resolve_run_directory(tmp_path, "../outside")


def test_run_state_post_init_copies_inputs_and_parameters():
    from_inputs = RunState(inputs={"beta": 1.0})
    assert from_inputs.parameters == {"beta": 1.0}
    from_parameters = RunState(parameters={"gamma": 2.0})
    assert from_parameters.inputs == {"gamma": 2.0}
    both = RunState(inputs={"a": 1}, parameters={"b": 2})
    assert both.inputs == {"a": 1}
    assert both.parameters == {"b": 2}


def test_input_hash_uses_explicit_inputs_or_state_fields():
    explicit = RunState(inputs={"z": 1})
    implicit = RunState(problem_definition="p")
    assert explicit.input_hash() == RunState(parameters={"z": 1}).input_hash()
    assert implicit.input_hash() == RunState(problem_definition="p").input_hash()
    changed = RunState(problem_definition="q")
    assert changed.input_hash() != implicit.input_hash()
    assert RunState(inputs={"z": 2}).input_hash() != explicit.input_hash()


def test_tool_versions_marks_missing_distributions(monkeypatch):
    calls = []

    def fake_version(name):
        calls.append(name)
        if name == "numpy":
            return "9.9.9"
        raise run_state.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(run_state.metadata, "version", fake_version)
    versions = RunState._tool_versions()
    assert versions["numpy"] == "9.9.9"
    assert versions["scipy"] == "not-installed"
    assert versions["python"]
    assert "z3-solver" in calls


def test_manifest_includes_run_hash_only_when_supplied():
    run = RunState(problem_definition="p")
    plain = run.manifest()
    hashed = run.manifest(run_sha256="deadbeef")
    assert "run_sha256" not in plain
    assert hashed["run_sha256"] == "deadbeef"
    assert hashed["run_format_version"] == run_state.RUN_FORMAT_VERSION


def test_save_and_load_roundtrip(tmp_path):
    run = RunState(problem_definition="p", parameters={"a": 1.0})
    run.add_result("x", 3)
    directory = run.save(tmp_path / "r")
    loaded = RunState.load(directory)
    assert loaded.results == {"x": 3}
    assert loaded.problem_definition == "p"


def test_load_without_integrity_skips_manifest_checks(tmp_path):
    run = RunState(problem_definition="p")
    directory = run.save(tmp_path / "r")
    (directory / "manifest.json").write_text(json.dumps({"run_sha256": "bogus"}), encoding="utf-8")
    loaded = RunState.load(directory, verify_integrity=False)
    assert loaded.problem_definition == "p"


def test_load_rejects_tampered_run_payload(tmp_path):
    run = RunState(problem_definition="p")
    directory = run.save(tmp_path / "r")
    (directory / "run.json").write_text(json.dumps({"problem_definition": "tampered"}), encoding="utf-8")
    with pytest.raises(ValueError, match="integrity check failed"):
        RunState.load(directory)


def test_load_rejects_wrong_input_hash(tmp_path):
    run = RunState(problem_definition="p")
    directory = run.save(tmp_path / "r")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["input_hash"] = "0" * 64
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="input_hash integrity check failed"):
        RunState.load(directory)


def test_load_rejects_unknown_format_version(tmp_path):
    run = RunState(problem_definition="p")
    directory = run.save(tmp_path / "r")
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["run_format_version"] = 99
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="run_format_version"):
        RunState.load(directory)


def test_load_accepts_manifest_without_version_or_hashes(tmp_path):
    run = RunState(problem_definition="p")
    directory = run.save(tmp_path / "r")
    (directory / "manifest.json").write_text(json.dumps({"unrelated": True}), encoding="utf-8")
    assert RunState.load(directory).problem_definition == "p"


def test_load_without_manifest_still_works(tmp_path):
    run = RunState(problem_definition="p")
    directory = run.save(tmp_path / "r")
    (directory / "manifest.json").unlink()
    assert RunState.load(directory).problem_definition == "p"


def test_export_and_import_roundtrip(tmp_path):
    run = RunState(problem_definition="exported", parameters={"a": 0.5})
    target = run.export(tmp_path / "exported.json")
    assert target.is_file()
    assert RunState.import_file(target).problem_definition == "exported"


def test_load_under_root_confines_run_id(tmp_path):
    run = RunState(problem_definition="p")
    run.save(tmp_path / "inside")
    assert RunState.load_under_root(tmp_path, "inside").problem_definition == "p"
    with pytest.raises(ValueError, match="escapes the configured run root"):
        RunState.load_under_root(tmp_path, "../outside")


# --------------------------------------------------------------------------- #
# Remaining POST route dispatch arms
# --------------------------------------------------------------------------- #

def _write_headers():
    return {"Authorization": "Bearer operator-token-0123456789",
            "Content-Type": "application/json"}


def test_post_clean_data_route_dispatches(tmp_path, monkeypatch):
    from axiomize.application import services

    seen = {}

    def fake_clean(payload):
        seen.update(payload)
        return {"cleaned": True}

    monkeypatch.setattr(services, "clean_data_service", fake_clean)
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(server, "/clean-data", method="POST",
                             payload={"rows": [1, 2]}, headers=_write_headers())
        assert status == 200
        assert body == {"cleaned": True}
        assert seen == {"rows": [1, 2]}
    finally:
        _stop(server, worker)


def test_post_fit_with_model_ir_uses_general_service(tmp_path, monkeypatch):
    from axiomize.application import general_services

    seen = {}

    def fake_fit(payload):
        seen.update(payload)
        return {"fitted": True}

    monkeypatch.setattr(general_services, "model_fit_service", fake_fit)
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(server, "/fit", method="POST",
                             payload={"model_ir": {"kind": "ode"}},
                             headers=_write_headers())
        assert status == 200
        assert body == {"fitted": True}
        assert seen["model_ir"] == {"kind": "ode"}
    finally:
        _stop(server, worker)


def test_post_validate_with_model_alias_uses_general_service(tmp_path, monkeypatch):
    from axiomize.application import general_services

    seen = {}

    def fake_validate(payload):
        seen.update(payload)
        return {"validated": True}

    monkeypatch.setattr(general_services, "model_validate_service", fake_validate)
    server = _server(tmp_path)
    worker = _start_thread(server)
    try:
        status, body = _http(server, "/validate", method="POST",
                             payload={"model": {"kind": "ode"}},
                             headers=_write_headers())
        assert status == 200
        assert body == {"validated": True}
        assert seen["model"] == {"kind": "ode"}
    finally:
        _stop(server, worker)


def test_atomic_write_swallows_cleanup_unlink_errors(tmp_path, monkeypatch):
    target = tmp_path / "state.json"
    real_unlink = Path.unlink

    def failing_unlink(self, *args, **kwargs):
        if self.name.startswith(f".{target.name}.") and self.suffix == ".tmp":
            raise OSError("temporary file is locked")
        return real_unlink(self, *args, **kwargs)

    def failing_replace(src, dst):
        raise RuntimeError("replace failed")

    monkeypatch.setattr(Path, "unlink", failing_unlink)
    monkeypatch.setattr(run_state.os, "replace", failing_replace)
    with pytest.raises(RuntimeError, match="replace failed"):
        run_state._atomic_write_text(target, "payload")
    assert target.exists() is False
