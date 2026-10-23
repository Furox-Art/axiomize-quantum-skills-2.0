"""Regression tests for REST run errors, width scoring and benchmark input."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from axiomize import dependency_policy
from axiomize.reasoning.benchmark import evaluate
from axiomize.reasoning.branch_controller import normalized_entropy
from axiomize.reasoning.cli import main as reasoning_main
from axiomize.runs.state import RunState
from axiomize.server import rest_server

AUTH = {"Authorization": "Bearer operator-token-0123456789", "Content-Type": "application/json"}


def _server(tmp_path: Path) -> rest_server.BoundedThreadingHTTPServer:
    return rest_server.BoundedThreadingHTTPServer(
        ("127.0.0.1", 0),
        rest_server.Handler,
        run_root=tmp_path,
        auth_token="operator-token-0123456789",
        max_concurrent_requests=8,
        connection_timeout_s=5.0,
    )


def _http(server, route, *, method="GET", payload=None, headers=None):
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.server_port}{route}",
        data=json.dumps(payload).encode()
        if payload is not None
        else (b"" if method == "POST" else None),
        headers={"Accept": "application/json", **(headers or {})},
        method=method,
    )
    try:
        response = urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        body = response.read()
        return response.status, json.loads(body) if body else {}


def test_reproduce_post_missing_run_is_404_like_get(tmp_path: Path) -> None:
    server = _server(tmp_path)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        get_status, _ = _http(server, "/runs/missing")
        post_status, body = _http(
            server, "/runs/missing/reproduce", method="POST", payload={}, headers=AUTH
        )
        assert get_status == 404
        assert post_status == 404
        assert body == {"error": "run not found or failed integrity checks"}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)


def test_reproduce_post_corrupt_run_is_404_like_get(tmp_path: Path) -> None:
    run = RunState(problem_definition="p", parameters={"b": 1.0})
    run.add_result("answer", 1)
    run.save(tmp_path / "run-c")
    (tmp_path / "run-c" / "run.json").write_text("{not json", encoding="utf-8")
    server = _server(tmp_path)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        get_status, _ = _http(server, "/runs/run-c")
        post_status, body = _http(
            server, "/runs/run-c/reproduce", method="POST", payload={}, headers=AUTH
        )
        assert get_status == 404
        assert post_status == 404
        assert body == {"error": "run not found or failed integrity checks"}
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=10)


def test_width_uses_the_given_scores_directly(capsys) -> None:
    assert reasoning_main(["width", "0.1", "0.9"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["uncertainty"] == pytest.approx(normalized_entropy([0.1, 0.9]))
    assert payload["uncertainty"] < 0.9


def test_width_rejects_scores_outside_the_unit_interval() -> None:
    with pytest.raises(SystemExit, match=r"\[0, 1\]"):
        reasoning_main(["width", "1.5"])


def _result(**overrides) -> dict:
    row = {
        "case_id": "c1",
        "answer": "2",
        "tokens": 1,
        "tool_calls": 0,
        "latency_ms": 1,
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize("field", ["tokens", "tool_calls", "latency_ms"])
def test_benchmark_rejects_non_finite_required_measurements(field: str) -> None:
    with pytest.raises(ValueError, match="not finite"):
        evaluate.validate_result(_result(**{field: float("nan")}))


def test_benchmark_rejects_non_finite_telemetry() -> None:
    with pytest.raises(ValueError, match="not finite"):
        evaluate.validate_result(_result(branches_total=2, branches_distinct=float("inf")))


def test_benchmark_rejects_boolean_measurements() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        evaluate.validate_result(_result(tokens=True))


def test_benchmark_rejects_an_integer_too_large_for_a_float() -> None:
    with pytest.raises(ValueError, match="not finite"):
        evaluate.validate_result(_result(tokens=10**400))


@pytest.mark.parametrize(
    "fields",
    [
        {"branches_total": 3},
        {"branches_distinct": 1},
        {"contradictions_found": 2},
        {"contradictions_resolved": 1},
    ],
)
def test_benchmark_rejects_half_recorded_telemetry_pairs(fields: dict) -> None:
    with pytest.raises(ValueError, match="provided together"):
        evaluate.validate_result(_result(**fields))


def test_benchmark_output_never_contains_nan(tmp_path: Path, capsys) -> None:
    cases = tmp_path / "cases.jsonl"
    cases.write_text(
        json.dumps({"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]})
        + "\n",
        encoding="utf-8",
    )
    skill = tmp_path / "skill.jsonl"
    skill.write_text(
        json.dumps({"case_id": "c1", "answer": "2", "tokens": 1, "tool_calls": 0, "latency_ms": 1})
        + "\n",
        encoding="utf-8",
    )
    assert evaluate.main(["--cases", str(cases), "--skill", str(skill)]) == 0
    out = capsys.readouterr().out
    assert "NaN" not in out and "Infinity" not in out
    json.loads(out)


def test_ensure_finite_rejects_an_infinite_metric() -> None:
    with pytest.raises(ValueError, match="latency is not finite"):
        evaluate.ensure_finite(float("inf"), "latency")


def test_installed_version_is_absent_for_an_uninstalled_distribution() -> None:
    assert dependency_policy._installed_version("axiomize-not-installed-2026") is None
