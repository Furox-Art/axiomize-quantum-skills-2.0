"""Regression pins for the 1.2.7 type-baseline fixes and the py.typed correction.

Each cheap mypy fix is behaviour-preserving; these tests pin the observable
contract at the fix site so a revert that changes behaviour fails loudly, and
the packaging/typing configuration decisions cannot silently drift back.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

from axiomize.bayesian.likelihoods import _validate_shape
from axiomize.general_engine_core import _simulate_sde, nondimensionalization_plan
from axiomize.model_ir import ModelIR
from axiomize.numerical_verification_v2 import numerical_refinement_study_v2
from axiomize.reasoning.ablation import run_ablation

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pyproject_text() -> str:
    return (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# likelihoods._validate_shape returns a builtin bool (was numpy.bool_)
# --------------------------------------------------------------------------- #

def test_validate_shape_returns_builtin_bool() -> None:
    observed = np.array([1.0, 2.0])
    good = _validate_shape(observed, np.array([1.0, 2.0]))
    bad_nan = _validate_shape(observed, np.array([1.0, float("nan")]))
    bad_shape = _validate_shape(observed, np.array([1.0]))
    assert good is True
    assert bad_nan is False
    assert bad_shape is False
    assert type(good) is bool
    assert type(bad_nan) is bool
    assert type(bad_shape) is bool


# --------------------------------------------------------------------------- #
# ablation dispatch table stays callable (annotated policies dict)
# --------------------------------------------------------------------------- #

def test_ablation_dispatch_runs_all_three_policies() -> None:
    results = run_ablation(seed=3, trials=2)
    for cell in results["cells"].values():
        assert set(cell["policies"]) == {"argmax_commit", "beam_top2", "branch_controller"}


# --------------------------------------------------------------------------- #
# general_engine_core: walrus narrowing keeps the None/0 semantics
# --------------------------------------------------------------------------- #

def _stochastic_model(initial: float | None) -> ModelIR:
    variable: dict = {"name": "x", "unit": "dimensionless"}
    if initial is not None:
        variable["initial"] = initial
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "sde", "domain": "test", "family": "stochastic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [variable], "parameters": [],
        "equations": [{"target": "x", "expression": "-x", "kind": "derivative"}],
    })


def test_sde_initial_none_is_rejected_and_set_initial_runs() -> None:
    with pytest.raises(ValueError, match="finite initial values"):
        _simulate_sde(_stochastic_model(None), t_span=(0.0, 1.0), points=5,
                      parameter_overrides=None, seed=1)
    result = _simulate_sde(_stochastic_model(1.0), t_span=(0.0, 1.0), points=5,
                           parameter_overrides=None, seed=1)
    assert result["status"] == "PASS"
    assert result["solver"]["method"] == "euler_maruyama"


def test_nondimensionalization_parameter_scales_none_zero_and_value() -> None:
    model = ModelIR.from_dict({
        "schema_version": "1.0", "name": "scales", "domain": "test", "family": "algebraic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [
            {"name": "p_none", "unit": "dimensionless"},
            {"name": "p_zero", "value": 0.0, "unit": "dimensionless"},
            {"name": "p_two", "value": 2.0, "unit": "dimensionless"},
            {"name": "p_neg", "value": -3.0, "unit": "dimensionless"},
        ],
        "equations": [{"target": "x", "expression": "p_two - x", "kind": "residual"}],
    })
    scales = nondimensionalization_plan(model)["parameter_scales"]
    assert scales == {"p_none": 1.0, "p_zero": 1.0, "p_two": 2.0, "p_neg": 3.0}


# --------------------------------------------------------------------------- #
# numerical_verification_v2 dispatch (annotated kwargs dict)
# --------------------------------------------------------------------------- #

def _ode_model() -> ModelIR:
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "n", "domain": "test", "family": "ode",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "-x", "kind": "derivative"}],
    })


def test_refinement_v2_stochastic_and_algebraic_dispatch() -> None:
    def simulate(model, **kwargs):
        return {"status": "PASS", "states": {"x": [1.0, 1.0]}}

    stochastic = ModelIR.from_dict({
        "schema_version": "1.0", "name": "s", "domain": "test", "family": "stochastic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "-x", "kind": "derivative"}],
    })
    replay = numerical_refinement_study_v2(
        stochastic, simulate_once=simulate, t_span=(0.0, 1.0), points=4, seed=0,
        approve_heavy=True)
    assert replay["study"] == "same_seed_reproducibility"

    algebraic = ModelIR.from_dict({
        "schema_version": "1.0", "name": "a", "domain": "test", "family": "algebraic",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [],
        "equations": [{"target": "x", "expression": "1 - x", "kind": "residual"}],
    })
    deterministic = numerical_refinement_study_v2(
        algebraic, simulate_once=simulate, t_span=(0.0, 1.0), points=4, seed=0,
        approve_heavy=True)
    assert deterministic["study"] == "same_seed_reproducibility"
    assert deterministic["status"] == "PASS"


# --------------------------------------------------------------------------- #
# py.typed: the marker ships; the false comment is gone; the pin is in place
# --------------------------------------------------------------------------- #

def test_py_typed_marker_exists_and_comment_no_longer_denies_it() -> None:
    assert (REPO_ROOT / "src" / "axiomize" / "py.typed").is_file()
    text = _pyproject_text()
    assert "The wheel ships no `py.typed` marker" not in text
    assert "src/axiomize ships a `py.typed` marker" in text


def test_packaging_contract_pins_py_typed_in_wheel_and_sdist() -> None:
    script = REPO_ROOT / ".github" / "scripts" / "package_contents_smoke.py"
    spec = importlib.util.spec_from_file_location("package_contents_smoke", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "axiomize/py.typed" in module.REQUIRED_WHEEL_PREFIXES
    assert "src/axiomize/py.typed" in module.REQUIRED_SDIST_PATHS


def test_optional_backend_imports_are_covered_by_mypy_override() -> None:
    text = _pyproject_text()
    for module in ('"jax"', '"jax.*"', '"arviz"', '"cds.diffeq"'):
        assert module in text, f"mypy override must list optional backend {module}"


# --------------------------------------------------------------------------- #
# README Python floor and quickstart version currency
# --------------------------------------------------------------------------- #

def _current_version() -> str:
    text = _pyproject_text()
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    for line in project.splitlines():
        if line.strip().startswith("version"):
            return line.split("=", 1)[1].strip().strip('"')
    raise AssertionError("pyproject has no version")


def test_readme_python_floor_matches_requires_python() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Python 3.11+" in readme
    assert "Python 3.10+" not in readme
    assert "python-3.11" in readme
    assert "python-3.10" not in readme
    assert 'requires-python = ">=3.11"' in _pyproject_text()


def test_readme_quickstart_current_line_matches_release() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    version = _current_version()
    assert f"Current package line: **{version}**" in readme
    # the quickstart's "current package line" prose must track the release too
    assert "The current package line is 1.2.5" not in readme
    assert f"The current package line is {version}" in readme
