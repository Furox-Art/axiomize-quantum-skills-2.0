"""Tests for the shipped benchmark suite, the run-bundle helpers, and json_safe.

These modules had zero or near-zero coverage even though ``benchmark_suite`` is
part of the published wheel and is the project's own self-check. The tests
below deliberately avoid running the full 12-case suite as the default, because
each case simulates a full model and the suite is slow; ``test_run_suite_...``
covers the orchestration and reporting contract, and one opt-in test executes
the real cases.
"""
from __future__ import annotations

import json
import math
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import numpy as np
import pytest

from axiomize import benchmark_suite
from axiomize.json_safety import json_safe
from axiomize.runs.bundle import export_run, import_run

EXPECTED_CASES = {
    "deterministic_model",
    "nonlinear_ode_outbreak",
    "optimization",
    "regression",
    "bayesian_fitting",
    "network_model",
    "control_problem",
    "stochastic_model",
    "pde_convergence",
    "wrong_model_rejected",
    "missing_information_explicit",
    "multiple_models_compared",
}


# --------------------------------------------------------------- benchmark_suite
def test_case_registry_is_complete_and_unique() -> None:
    names = [name for name, _ in benchmark_suite._CASES]
    assert len(names) == len(set(names)), "duplicate benchmark case names"
    assert set(names) == EXPECTED_CASES


def test_case_registry_entries_are_zero_argument_callables() -> None:
    for name, case in benchmark_suite._CASES:
        assert callable(case), name
        assert case.__code__.co_argcount == 0, f"{name} must take no arguments"


def test_run_suite_reports_every_case_with_a_pass_or_fail_status(monkeypatch) -> None:
    monkeypatch.setattr(
        benchmark_suite,
        "_CASES",
        [("alpha", lambda: None), ("beta", lambda: None)],
    )
    result = benchmark_suite.run_suite()

    assert result["status"] == "PASS"
    assert result["passed"] == 2
    assert result["total"] == 2
    assert [item["status"] for item in result["results"]] == ["PASS", "PASS"]


def test_run_suite_contains_a_failing_case_instead_of_raising(monkeypatch) -> None:
    """The benchmark boundary must report failures, not propagate them."""
    seen: list[str] = []

    def _explode() -> None:
        raise RuntimeError("solver diverged")

    def _record() -> None:
        seen.append("ok")

    monkeypatch.setattr(
        benchmark_suite,
        "_CASES",
        [("good", _record), ("bad", _explode), ("after", _record)],
    )
    result = benchmark_suite.run_suite()

    assert result["status"] == "FAIL"
    assert result["passed"] == 2
    assert result["total"] == 3
    # A raising case must not stop the ones queued behind it.
    assert seen == ["ok", "ok"]

    failed = [item for item in result["results"] if item["status"] == "FAIL"]
    assert len(failed) == 1
    assert failed[0]["name"] == "bad"
    assert "RuntimeError: solver diverged" in failed[0]["error"]
    assert "RuntimeError" in failed[0]["traceback"]
    # A PASS record carries no error detail.
    passing = next(item for item in result["results"] if item["status"] == "PASS")
    assert "error" not in passing and "traceback" not in passing


def test_run_suite_on_empty_registry_reports_pass(monkeypatch) -> None:
    monkeypatch.setattr(benchmark_suite, "_CASES", [])
    result = benchmark_suite.run_suite()
    assert result == {"status": "PASS", "passed": 0, "total": 0, "results": []}


@pytest.mark.slow
def test_real_benchmark_suite_passes() -> None:
    """Opt-in: runs the shipped 12 cases for real. Deselect with -m 'not slow'."""
    result = benchmark_suite.run_suite()
    failures = [item for item in result["results"] if item["status"] == "FAIL"]
    assert not failures, failures
    assert result["passed"] == result["total"] == len(EXPECTED_CASES)


# ---------------------------------------------------------------- runs.bundle
def test_export_run_rejects_a_non_zip_destination(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    with pytest.raises(ValueError, match=r"must end in \.zip"):
        export_run(run_dir, tmp_path / "out.tar")


def test_export_then_import_round_trips_the_run_directory(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "nested").mkdir(parents=True)
    (run_dir / "top.txt").write_text("top level", encoding="utf-8")
    (run_dir / "nested" / "deep.json").write_text('{"k": 1}', encoding="utf-8")

    bundle = export_run(run_dir, tmp_path / "bundle.zip")
    assert bundle == tmp_path / "bundle.zip"
    assert zipfile.is_zipfile(bundle)
    # shutil.make_archive derives the real name from the stem.
    assert (tmp_path / "bundle.zip").is_file()

    dest = import_run(bundle, tmp_path / "restored")
    assert dest == tmp_path / "restored"
    assert (dest / "top.txt").read_text(encoding="utf-8") == "top level"
    assert json.loads((dest / "nested" / "deep.json").read_text(encoding="utf-8")) == {"k": 1}


def test_import_run_creates_missing_destination_directories(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "f.txt").write_text("data", encoding="utf-8")
    bundle = export_run(run_dir, tmp_path / "b.zip")

    dest = import_run(bundle, tmp_path / "a" / "b" / "c")
    assert dest.is_dir()
    assert (dest / "f.txt").read_text(encoding="utf-8") == "data"


def test_import_run_into_an_existing_directory_overwrites(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "f.txt").write_text("new", encoding="utf-8")
    bundle = export_run(run_dir, tmp_path / "b.zip")

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "f.txt").write_text("old", encoding="utf-8")
    import_run(bundle, dest)
    assert (dest / "f.txt").read_text(encoding="utf-8") == "new"


# ----------------------------------------------------------------- json_safety
def test_json_safe_passes_through_json_native_scalars() -> None:
    for value in (None, "text", True, False, 7, -3):
        assert json_safe(value) == value


def test_json_safe_replaces_non_finite_floats_with_strings() -> None:
    """RFC 8259 has no NaN/Infinity, so these must become explicit strings."""
    assert json_safe(float("nan")) == "NaN"
    assert json_safe(float("inf")) == "Infinity"
    assert json_safe(float("-inf")) == "-Infinity"
    assert json_safe(1.5) == 1.5


def test_json_safe_output_is_always_strict_json() -> None:
    payload = {"a": float("nan"), "b": [float("inf"), float("-inf")]}
    encoded = json.dumps(json_safe(payload), allow_nan=False)
    assert json.loads(encoded) == {"a": "NaN", "b": ["Infinity", "-Infinity"]}


class Colour(Enum):
    RED = "red"
    OTHER = "other"


@dataclass
class Sample:
    name: str
    value: float


def test_json_safe_unwraps_enums_paths_and_dataclasses() -> None:
    assert json_safe(Colour.RED) == "red"
    assert json_safe(Colour.OTHER) == "other"
    assert json_safe(Path("a/b/c.txt")) == str(Path("a/b/c.txt"))
    assert json_safe(Sample("x", float("nan"))) == {"name": "x", "value": "NaN"}


def test_json_safe_normalises_dict_keys_to_strings() -> None:
    assert json_safe({1: "int", ("t", 2): "tuple", None: "none"}) == {
        "1": "int",
        "('t', 2)": "tuple",
        "None": "none",
    }


def test_json_safe_handles_every_sequence_flavour() -> None:
    assert json_safe((1, 2)) == [1, 2]
    assert json_safe([1, (2, 3)]) == [1, [2, 3]]
    assert sorted(json_safe({1, 2})) == [1, 2]
    assert sorted(json_safe(frozenset({3}))) == [3]


def test_json_safe_converts_numpy_scalars_and_arrays() -> None:
    assert json_safe(np.float64(2.5)) == 2.5
    assert json_safe(np.int64(7)) == 7
    assert json_safe(np.array([1.0, np.nan])) == [1.0, "NaN"]
    assert json_safe(np.array([[1, 2], [3, 4]])) == [[1, 2], [3, 4]]
    # bool_ is an int subclass; it must still round-trip as a bool.
    assert json_safe(np.bool_(True)) is True


def test_json_safe_falls_back_to_str_for_unknown_objects() -> None:
    class Opaque:
        def __repr__(self) -> str:
            return "<opaque>"

    assert json_safe(Opaque()) == "<opaque>"
    assert json_safe(complex(1, 2)) == str(complex(1, 2))
    assert json_safe(b"bytes") == str(b"bytes")


def test_json_safe_result_survives_a_strict_encoder_round_trip() -> None:
    payload = {
        "nan": float("nan"),
        "nested": {"arr": np.array([1.5, float("inf")])},
        "enum": Colour.OTHER,
    }
    encoded = json.dumps(json_safe(payload), allow_nan=False)
    assert "NaN" in encoded and "Infinity" in encoded


def test_json_safe_is_idempotent() -> None:
    once = json_safe({"v": [float("nan"), np.float32(1.5)]})
    assert json_safe(once) == once


def test_nan_inside_a_large_structure_is_not_lost() -> None:
    payload = {str(i): {"value": float("nan") if i % 2 else i} for i in range(10)}
    safe = json_safe(payload)
    assert safe["1"]["value"] == "NaN"
    assert safe["2"]["value"] == 2
    assert not any(isinstance(item, float) and math.isnan(item) for item in safe.values())
