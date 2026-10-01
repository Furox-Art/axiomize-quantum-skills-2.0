"""Regression tests for the REST/MCP transport surface and run-path confinement.

Covers the three gaps fixed alongside the dependency policy:

1. The loopback REST bind exposed an unauthenticated *mutating* surface. A
   web page can send a "simple" cross-origin request (``text/plain``, no
   preflight) to ``http://127.0.0.1:<port>``, which previously solved, fit and
   ran Monte Carlo routes with no credential.
2. ``compare_runs_service`` did its filesystem reads with no confinement of its
   own; the guard lived only in the two transports, so any other caller got an
   arbitrary-path read.
3. ``import_run`` accepted any archive suffix and delegated to
   ``shutil.unpack_archive``, whose tar path escapes the destination on the
   Python versions this project supports.
"""

from __future__ import annotations

import io
import json
import os
import tarfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

_SOLVE_PAYLOAD = {"beta": 0.3, "gamma": 0.1, "I0": 10.0, "N": 100000.0, "days": 180.0}


# --- helpers -----------------------------------------------------------------

def _start(run_root: Path | None = None, **kwargs):
    from axiomize.server.rest_server import start_server

    server = start_server("127.0.0.1", 0, run_root=run_root, **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def _post(server, path: str, payload: dict, *, token: str | None = None,
          content_type: str = "application/json"):
    headers = {"Content-Type": content_type}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8") or "{}")


def _get(server, path: str, *, token: str | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_address[1]}{path}", headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


# --- 1. loopback binding and the mutating surface ----------------------------

def test_default_bind_is_loopback() -> None:
    import inspect

    from axiomize.server.rest_server import start_server

    default = inspect.signature(start_server).parameters["host"].default
    assert default == "127.0.0.1"


def test_start_server_never_leaves_the_token_unset(tmp_path: Path) -> None:
    """A loopback bind with no token is no longer a no-auth mode."""
    server = _start(tmp_path)
    try:
        assert server.auth_token is not None
        assert server.generated_token == server.auth_token
    finally:
        server.shutdown()
        server.server_close()


def test_generated_tokens_are_strong_and_unique(tmp_path: Path) -> None:
    first, second = _start(tmp_path), _start(tmp_path)
    try:
        for server in (first, second):
            token = server.generated_token
            assert token is not None
            # 32 urlsafe bytes -> at least 43 characters of base64.
            assert len(token) >= 43
        assert first.generated_token != second.generated_token
    finally:
        for server in (first, second):
            server.shutdown()
            server.server_close()


def test_supplied_token_is_not_replaced(tmp_path: Path) -> None:
    server = _start(tmp_path, auth_token="an-operator-chosen-token")
    try:
        assert server.auth_token == "an-operator-chosen-token"
        assert server.generated_token is None
    finally:
        server.shutdown()
        server.server_close()


def test_unauthenticated_post_is_rejected(tmp_path: Path) -> None:
    server = _start(tmp_path)
    try:
        code, body = _post(server, "/v1/solve", _SOLVE_PAYLOAD)
        assert code == 401, body
        assert body["error"] == "unauthorized"
    finally:
        server.shutdown()
        server.server_close()


def test_cross_origin_simple_post_is_rejected_before_auth(tmp_path: Path) -> None:
    """text/plain is a CORS "simple" content type, so a page can forge it.

    It must be refused as unsupported media rather than being parsed as JSON.
    """
    server = _start(tmp_path)
    try:
        code, body = _post(server, "/v1/solve", _SOLVE_PAYLOAD, content_type="text/plain")
        assert code == 415, body
        assert "application/json" in body["error"]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize(
    "content_type",
    ["application/x-www-form-urlencoded", "multipart/form-data", "text/html"],
)
def test_every_csrf_simple_content_type_is_rejected(tmp_path: Path, content_type: str) -> None:
    server = _start(tmp_path)
    try:
        code, _ = _post(server, "/v1/solve", _SOLVE_PAYLOAD, content_type=content_type)
        assert code == 415
    finally:
        server.shutdown()
        server.server_close()


def test_authenticated_post_succeeds(tmp_path: Path) -> None:
    server = _start(tmp_path)
    try:
        code, body = _post(server, "/v1/solve", _SOLVE_PAYLOAD, token=server.auth_token)
        assert code == 200, body
        assert body["status"] == "PASS"
    finally:
        server.shutdown()
        server.server_close()


def test_wrong_token_is_rejected(tmp_path: Path) -> None:
    server = _start(tmp_path)
    try:
        code, _ = _post(server, "/v1/solve", _SOLVE_PAYLOAD, token="not-the-token")
        assert code == 401
    finally:
        server.shutdown()
        server.server_close()


def test_alternate_token_header_is_accepted(tmp_path: Path) -> None:
    server = _start(tmp_path)
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_address[1]}/v1/solve",
            data=json.dumps(_SOLVE_PAYLOAD).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Axiomize-Token": server.auth_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            assert response.status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_read_gating_follows_whether_the_operator_supplied_a_token(tmp_path: Path) -> None:
    """A generated token protects writes only; an operator token protects reads.

    The release smoke contract in .github/scripts does an unauthenticated
    GET /v1/capabilities, so read gating must stay opt-in via an explicit
    operator token. Writes are gated either way.
    """
    generated = _start(tmp_path)
    operator = _start(tmp_path, auth_token="an-operator-chosen-token")
    try:
        assert generated.generated_token is not None
        assert generated.require_token_for_reads is False
        assert operator.generated_token is None
        assert operator.require_token_for_reads is True

        # Generated token: reads open, writes closed.
        assert _get(generated, "/v1/tools") == 200
        assert _post(generated, "/v1/solve", _SOLVE_PAYLOAD)[0] == 401
        assert _post(generated, "/v1/solve", _SOLVE_PAYLOAD, token=generated.auth_token)[0] == 200

        # Operator token: reads and writes both closed.
        assert _get(operator, "/v1/tools") == 401
        assert _get(operator, "/v1/tools", token=operator.auth_token) == 200
        assert _post(operator, "/v1/solve", _SOLVE_PAYLOAD, token=operator.auth_token)[0] == 200
    finally:
        for server in (generated, operator):
            server.shutdown()
            server.server_close()


def test_read_gating_can_be_forced_on_with_a_generated_token(tmp_path: Path) -> None:
    server = _start(tmp_path, require_token_for_reads=True)
    try:
        assert server.generated_token is not None
        assert server.require_token_for_reads is True
        assert _get(server, "/v1/tools") == 401
        assert _get(server, "/v1/tools", token=server.auth_token) == 200
    finally:
        server.shutdown()
        server.server_close()


def test_unauthenticated_get_is_rejected(tmp_path: Path) -> None:
    server = _start(tmp_path, auth_token="an-operator-chosen-token")
    try:
        assert _get(server, "/v1/tools") == 401
        assert _get(server, "/v1/tools", token=server.auth_token) == 200
    finally:
        server.shutdown()
        server.server_close()


def test_directly_constructed_server_fails_closed_on_writes(tmp_path: Path) -> None:
    """Bypassing start_server must not re-open the mutating surface."""
    from axiomize.server.rest_server import BoundedThreadingHTTPServer, Handler

    server = BoundedThreadingHTTPServer(
        ("127.0.0.1", 0),
        Handler,
        run_root=tmp_path,
        auth_token=None,
        max_concurrent_requests=4,
        connection_timeout_s=5,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        code, body = _post(server, "/v1/solve", _SOLVE_PAYLOAD)
        assert code == 401
        assert "auth_token" in body["error"]
    finally:
        server.shutdown()
        server.server_close()


# --- remote binding rules unchanged ------------------------------------------

def test_remote_bind_still_requires_opt_in_and_a_long_token() -> None:
    from axiomize.server.rest_server import start_server

    with pytest.raises(ValueError, match="allow_remote"):
        start_server("0.0.0.0", 0)
    with pytest.raises(ValueError, match="at least 16 characters"):
        start_server("0.0.0.0", 0, allow_remote=True, auth_token="short")
    server = start_server("0.0.0.0", 0, allow_remote=True, auth_token="a-sufficiently-long-token")
    try:
        assert server.auth_token == "a-sufficiently-long-token"
    finally:
        server.server_close()


# --- 2. run-path confinement moved into the service layer --------------------

def test_compare_runs_service_confines_absolute_paths(tmp_path: Path) -> None:
    from axiomize.application.services import compare_runs_service
    from axiomize.runs.state import RunState

    outside = tmp_path / "outside"
    RunState(problem_definition="secret").save(outside)
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="absolute run paths"):
        compare_runs_service(
            {"before_dir": str(outside), "after_dir": str(outside)}, run_root=root
        )


@pytest.mark.parametrize("run_id", ["../outside", "a/../../outside", "../../etc"])
def test_compare_runs_service_confines_traversal(tmp_path: Path, run_id: str) -> None:
    from axiomize.application.services import compare_runs_service
    from axiomize.runs.state import RunState

    RunState(problem_definition="secret").save(tmp_path / "outside")
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(ValueError, match="escapes the configured run root"):
        compare_runs_service({"before_dir": run_id, "after_dir": run_id}, run_root=root)


@pytest.mark.skipif(os.name != "nt", reason="backslash is a separator only on Windows")
def test_compare_runs_service_confines_windows_separator_traversal(tmp_path: Path) -> None:
    from axiomize.application.services import compare_runs_service

    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="escapes the configured run root"):
        compare_runs_service(
            {"before_dir": "..\\outside", "after_dir": "..\\outside"}, run_root=root
        )


@pytest.mark.skipif(os.name == "nt", reason="POSIX treats a backslash as an ordinary filename character")
def test_posix_backslash_is_confined_as_a_filename_not_a_traversal(tmp_path: Path) -> None:
    """On POSIX ``..\\outside`` is one filename, not a parent reference.

    The guard must confine it inside the root rather than reject it, so this
    pins the platform-specific behaviour in both directions.
    """
    from axiomize.runs.state import RunState, resolve_run_directory

    root = tmp_path / "root"
    root.mkdir()
    resolved = resolve_run_directory(root, "..\\outside")
    assert resolved.parent == root
    assert resolved.name == "..\\outside"
    with pytest.raises(ValueError, match="run.json"):
        RunState.load(resolved)


def test_compare_runs_service_confines_nul_bytes(tmp_path: Path) -> None:
    from axiomize.application.services import compare_runs_service

    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="NUL"):
        compare_runs_service({"before_dir": "a\x00b", "after_dir": "a\x00b"}, run_root=root)


def test_compare_runs_service_accepts_a_run_id_inside_the_root(tmp_path: Path) -> None:
    from axiomize.application.services import compare_runs_service
    from axiomize.runs.state import RunState

    root = tmp_path / "root"
    run = root / "run-a"
    RunState(problem_definition="x", parameters={"beta": 0.3}).save(run)

    out = compare_runs_service({"before_dir": "run-a", "after_dir": "run-a"}, run_root=root)
    assert out["same_input_hash"] is True
    assert out["same_results"] is True


def test_compare_runs_service_without_a_root_stays_a_local_operator_path(tmp_path: Path) -> None:
    """run_root=None is the explicit trust decision used by the CLI."""
    from axiomize.application.services import compare_runs_service
    from axiomize.runs.state import RunState

    run = tmp_path / "run-a"
    RunState(problem_definition="x").save(run)
    out = compare_runs_service({"before_dir": str(run), "after_dir": str(run)})
    assert out["same_input_hash"] is True


def test_compare_run_directories_honours_run_root(tmp_path: Path) -> None:
    from axiomize.runs.compare import compare_run_directories

    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="absolute run paths"):
        compare_run_directories(str(tmp_path), str(tmp_path), run_root=root)


def test_rest_compare_runs_route_is_confined(tmp_path: Path) -> None:
    from axiomize.runs.state import RunState

    root = tmp_path / "root"
    RunState(problem_definition="x").save(root / "run-a")
    server = _start(root)
    try:
        code, body = _post(
            server, "/v1/compare-runs",
            {"before_dir": str(tmp_path), "after_dir": str(tmp_path)},
            token=server.auth_token,
        )
        assert code == 400, body
        assert "absolute run paths" in body["error"]

        code, body = _post(
            server, "/v1/compare-runs",
            {"before_dir": "run-a", "after_dir": "run-a"},
            token=server.auth_token,
        )
        assert code == 200, body
        assert body["same_input_hash"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_mcp_compare_runs_is_confined(tmp_path: Path) -> None:
    from axiomize.runs.state import RunState

    root = tmp_path / "root"
    RunState(problem_definition="x").save(root / "run-a")
    from axiomize.server import mcp_server

    out = mcp_server.call_tool(
        "axiomize.compare_runs",
        {"before_dir": str(tmp_path), "after_dir": str(tmp_path)},
        run_root=root,
    )
    assert "absolute run paths" in out["error"]

    ok = mcp_server.call_tool(
        "axiomize.compare_runs",
        {"before_dir": "run-a", "after_dir": "run-a"},
        run_root=root,
    )
    assert ok["same_input_hash"] is True


# --- 3. bundle import is confined --------------------------------------------

def _zip_with(tmp_path: Path, name: str, member: str, content: bytes = b"x") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(member, content)
    return path


def test_import_run_rejects_tar_archives(tmp_path: Path) -> None:
    """shutil.unpack_archive's tar path is not path-confined on 3.10-3.13."""
    from axiomize.runs.bundle import import_run

    tar_path = tmp_path / "evil.tar.gz"
    payload = b"owned\n"
    with tarfile.open(tar_path, "w:gz") as archive:
        info = tarfile.TarInfo("../ESCAPED.txt")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))

    dest = tmp_path / "dest"
    with pytest.raises(ValueError, match=r"must end in \.zip"):
        import_run(tar_path, dest)
    assert not (tmp_path / "ESCAPED.txt").exists()


def test_import_run_rejects_parent_traversal_members(tmp_path: Path) -> None:
    from axiomize.runs.bundle import import_run

    bundle = _zip_with(tmp_path, "evil.zip", "../ESCAPED.txt")
    dest = tmp_path / "dest"
    with pytest.raises(ValueError, match="escapes the extraction directory"):
        import_run(bundle, dest)
    assert not (tmp_path / "ESCAPED.txt").exists()
    assert not dest.exists(), "a rejected bundle must not create the destination"


def test_import_run_rejects_absolute_members(tmp_path: Path) -> None:
    from axiomize.runs.bundle import import_run

    bundle = _zip_with(tmp_path, "abs.zip", "/tmp/axiomize-absolute-escape.txt")
    with pytest.raises(ValueError, match="escapes the extraction directory"):
        import_run(bundle, tmp_path / "dest")


def test_import_run_rejects_a_missing_bundle(tmp_path: Path) -> None:
    from axiomize.runs.bundle import import_run

    with pytest.raises(ValueError, match="existing regular file"):
        import_run(tmp_path / "nope.zip", tmp_path / "dest")


def test_import_run_round_trips_a_real_run(tmp_path: Path) -> None:
    from axiomize.runs.bundle import export_run, import_run
    from axiomize.runs.state import RunState

    run = tmp_path / "run-a"
    RunState(problem_definition="round-trip", parameters={"beta": 0.3}).save(run)
    bundle = export_run(run, tmp_path / "run-a.zip")
    dest = import_run(bundle, tmp_path / "restored")
    assert (dest / "run.json").is_file()
    assert (dest / "manifest.json").is_file()
    assert RunState.load(dest).problem_definition == "round-trip"


def test_import_run_can_confine_the_destination_to_a_run_root(tmp_path: Path) -> None:
    from axiomize.runs.bundle import export_run, import_run
    from axiomize.runs.state import RunState

    run = tmp_path / "run-a"
    RunState(problem_definition="x").save(run)
    bundle = export_run(run, tmp_path / "run-a.zip")

    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(ValueError, match="escapes the configured run root"):
        import_run(bundle, "../escaped", run_root=root)
    with pytest.raises(ValueError, match="absolute run paths"):
        import_run(bundle, str(tmp_path / "escaped"), run_root=root)
    import_run(bundle, "restored", run_root=root)
    assert (root / "restored" / "run.json").is_file()


def test_inspect_bundle_members_lists_valid_members(tmp_path: Path) -> None:
    from axiomize.runs.bundle import export_run, inspect_bundle_members
    from axiomize.runs.state import RunState

    run = tmp_path / "run-a"
    RunState(problem_definition="x").save(run)
    bundle = export_run(run, tmp_path / "run-a.zip")
    names = {name for name, _size in inspect_bundle_members(bundle)}
    assert {"run.json", "manifest.json"} <= names


def test_inspect_bundle_members_enforces_the_member_ceiling(tmp_path: Path, monkeypatch) -> None:
    from axiomize.runs import bundle as bundle_mod

    bundle = _zip_with(tmp_path, "many.zip", "run.json")
    monkeypatch.setattr(bundle_mod, "_MAX_BUNDLE_MEMBERS", 0)
    with pytest.raises(ValueError, match="member limit"):
        bundle_mod.inspect_bundle_members(bundle)
