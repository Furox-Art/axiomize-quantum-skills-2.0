"""Regression tests for numeric-oracle keyword alternatives."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _runner():
    root = Path(__file__).resolve().parents[1]
    path = root / "skills" / "axiomize" / "tools" / "benchmark_runner.py"
    spec = importlib.util.spec_from_file_location("axiomize_benchmark_runner_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _oracle_result(report: str, expected: float = 50.0, tolerance: float = 30.0) -> bool:
    checks, _ = _runner().grade(
        report,
        {
            "must_contain": [],
            "expected_archetype": "",
            "min_lenses_built": 0,
            "must_reject_at_least_one": False,
            "numeric_oracle": {
                "keyword": "temperature|rise|delta|dT",
                "expected": expected,
                "tolerance": tolerance,
            },
        },
    )
    return checks["numeric oracle temperature|rise|delta|dT ~ 50.0 ±30.0"]


@pytest.mark.parametrize(
    "report",
    [
        "Steady-state temperature rise: 50 K.",
        "The measured dT 50 K.",
    ],
)
def test_numeric_oracle_matches_keyword_alternatives(report: str) -> None:
    assert _oracle_result(report) is True


def test_numeric_oracle_rejects_value_outside_tolerance() -> None:
    assert _oracle_result("Steady-state temperature rise: 100 K.") is False


def test_numeric_oracle_rejects_report_without_any_keyword_alternative() -> None:
    assert _oracle_result("Pressure increase: 50 K.") is False
