"""Coverage hardening round 2a: general_engine_core planning/validation helpers."""

from __future__ import annotations

import importlib.util
import sys

import numpy as np
import pytest

import axiomize.general_engine_core as core
from axiomize.model_ir import (
    ConstraintSpec,
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    VariableSpec,
)

# ``general_engine`` replaces several core module attributes with facade
# wrappers at import time. Loading an independent copy of the same source file
# lets these tests exercise the original core planning/execution bodies without
# disturbing the already-imported public facade.
_spec = importlib.util.spec_from_file_location("axiomize_cov_r2a_core", core.__file__)
assert _spec is not None and _spec.loader is not None
_fresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fresh)


def _model(
    family: ModelFamily = ModelFamily.ODE,
    *,
    variables=None,
    parameters=None,
    equations=None,
    constraints=None,
    metadata=None,
    name="core",
) -> ModelIR:
    return ModelIR(
        name=name,
        domain="test",
        family=family,
        variables=list(variables or []),
        parameters=list(parameters or []),
        equations=list(equations or []),
        constraints=list(constraints or []),
        metadata=dict(metadata or {}),
    )


def test_recommend_model_families_every_signal():
    rows = _fresh.recommend_model_families(
        domain="physics",
        signals=[
            "optimization",
            "network",
            "causal",
            "control",
            "agent",
            "event",
            "bayesian",
            "algebraic",
        ],
    )
    families = {row["family"] for row in rows}
    assert {"optimization", "network", "causal"} <= families
    assert [row["rank"] for row in rows] == [1, 2, 3]
    assert all(isinstance(row["score"], int) for row in rows)


def test_build_execution_plan_fit_stage():
    model = _model(
        variables=[VariableSpec(name="x", initial=1.0)],
        parameters=[ParameterSpec(name="k", value=1.0, fit=True)],
        equations=[EquationSpec(target="x", expression="-k*x", kind="derivative")],
    )
    plan = _fresh.build_execution_plan(model, action="fit", points=10)
    assert "identifiability_check" in plan["stages"]
    assert "residual_diagnostics" in plan["stages"]
    assert plan["approval_required"] is False


def test_core_expression_parser_accepts_and_rejects():
    # Direct call to the shared-budget helper (the facade bypasses it).
    core._validate_expression_syntax("x + 1", {"x"})
    with pytest.raises(ValueError):
        core._validate_expression_syntax("__import__('os')", {"x"})

    import sympy as sp

    symbol = sp.Symbol("x", real=True)
    parsed = _fresh._sympy_expression("x + 1", {"x": symbol})
    assert str(parsed) == "x + 1"
    with pytest.raises(ValueError):
        _fresh._sympy_expression("import os", {"x": symbol})


def test_parameter_values_bounds_and_unknown_overrides():
    model = _model(
        parameters=[
            ParameterSpec(name="k", value=1.0),
            ParameterSpec(name="bounded", value=2.0, bounds=(0.0, 3.0)),
        ]
    )
    assert core._parameter_values(model, {"k": 3.0}) == {"k": 3.0, "bounded": 2.0}
    with pytest.raises(ValueError, match="has no value"):
        core._parameter_values(_model(parameters=[ParameterSpec(name="n")]))
    with pytest.raises(ValueError, match="below lower bound"):
        core._parameter_values(
            _model(parameters=[ParameterSpec(name="k", value=1.0, bounds=(2.0, 3.0))])
        )
    with pytest.raises(ValueError, match="above upper bound"):
        core._parameter_values(
            _model(parameters=[ParameterSpec(name="k", value=4.0, bounds=(2.0, 3.0))])
        )
    with pytest.raises(ValueError, match="unknown parameter overrides"):
        core._parameter_values(_model(parameters=[ParameterSpec(name="k", value=1.0)]), {"z": 1.0})


def test_validate_model_unit_engine_fail_and_unverified(monkeypatch):
    invalid = _model(
        variables=[VariableSpec(name="x", initial=1.0, unit="bogus")],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    checks = core.validate_model(invalid)["checks"]
    unit_checks = [check for check in checks if check["name"] == "variable_unit:x"]
    assert unit_checks and unit_checks[0]["status"] == "FAIL"

    monkeypatch.setitem(sys.modules, "axiomize.validation.dimensions", None)
    checks = core.validate_model(
        _model(
            variables=[VariableSpec(name="x", initial=1.0)],
            equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
        )
    )["checks"]
    engine = [check for check in checks if check["name"] == "unit_engine"]
    assert engine and engine[0]["status"] == "UNVERIFIED"


def test_validate_model_constraint_errors_become_scientific_failures():
    missing_upper = ConstraintSpec(name="range", expression="x", relation="between", threshold=0.0)
    with pytest.raises(ValueError, match="requires upper"):
        core._evaluate_constraint(missing_upper, [{"x": 1.0}])

    model = _model(
        variables=[VariableSpec(name="x", initial=1.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
        constraints=[ConstraintSpec(name="weird", expression="x", relation="weird")],
    )
    report = core.validate_model(model)
    assert report["status"] == "FAIL"
    assert report["repair_requires_approval"] is True
    assert report["repair_proposal"]["failed_constraints"] == ["weird"]
    weird = [item for item in report["scientific_constraints"] if item["name"] == "weird"]
    assert weird and weird[0]["status"] == "FAIL"
    assert "unsupported constraint relation" in weird[0]["detail"]

    between = _model(
        variables=[VariableSpec(name="x", initial=0.5)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
        constraints=[
            ConstraintSpec(
                name="range",
                expression="x",
                relation="between",
                threshold=0.1,
                upper=0.4,
            )
        ],
    )
    report = core.validate_model(between)
    assert report["status"] == "FAIL"
    assert "range=[" in report["scientific_constraints"][0]["detail"]


def test_validate_model_constraint_context_without_initial_values():
    model = _model(
        variables=[VariableSpec(name="x"), VariableSpec(name="z", role="latent")],
        parameters=[ParameterSpec(name="k", value=1.0)],
        equations=[EquationSpec(target="x", expression="-k*x", kind="derivative")],
        constraints=[ConstraintSpec(name="pos", expression="x", relation="ge", threshold=0.0)],
    )
    report = core.validate_model(model)
    assert report["status"] == "FAIL"
    # No initial values, so the constraint namespace has no state symbols.
    assert "unknown symbol in expression: x" in report["scientific_constraints"][0]["detail"]


def test_causal_guard_non_mapping_evidence():
    model = _model(
        ModelFamily.CAUSAL,
        variables=[VariableSpec(name="x", initial=1.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
        metadata={"causal_identification": "not-a-mapping"},
    )
    report = core.validate_model(model)
    guard = [check for check in report["checks"] if check["name"] == "causal_identification"]
    assert guard and guard[0]["status"] == "UNVERIFIED"


def test_residual_diagnostics_shape_and_finite_guards():
    with pytest.raises(ValueError, match="shape mismatch"):
        core.residual_diagnostics(np.ones((3, 1)), np.ones(3))
    with pytest.raises(ValueError, match="require observations"):
        core.residual_diagnostics(np.asarray([]), np.asarray([]))

    short = core.residual_diagnostics(np.asarray([1.0, 2.0]), np.asarray([0.5, 1.0]))
    assert short["lag1_autocorrelation"] == 0.0
    assert short["std"] > 0.0

    degenerate = core.residual_diagnostics(np.asarray([1.0, 1.0, 1.0, 2.0]), np.zeros(4))
    assert degenerate["lag1_autocorrelation"] == 0.0
    assert degenerate["systematic_error_warning"] is True


def test_rank_model_fits_criterion_validation_and_missing_scores():
    with pytest.raises(ValueError, match="criterion must be"):
        core.rank_model_fits({}, criterion="rmse")
    fits = {
        "alpha": {"selection_scores": {"bic": 12.0}},
        "beta": {"selection_scores": {"aic": 1.0}},
    }
    ranked = core.rank_model_fits(fits, criterion="bic")
    assert ranked["winner"] == "alpha"
    assert len(ranked["ranked"]) == 1


def test_local_stability_requires_ode():
    with pytest.raises(ValueError, match="requires an ODE model"):
        core.local_stability(
            _model(ModelFamily.ALGEBRAIC, variables=[VariableSpec(name="x", initial=1.0)]),
            state={"x": 1.0},
        )


def test_nondimensionalization_plan_without_initial_values():
    model = _model(
        variables=[
            VariableSpec(name="x", bounds=(1.0, 100.0)),
            VariableSpec(name="y", initial=2.0),
        ],
        parameters=[ParameterSpec(name="k", value=0.0)],
    )
    plan = core.nondimensionalization_plan(model)
    assert plan["variable_scales"]["x"] == 100.0
    assert plan["variable_scales"]["y"] == 2.0
    assert plan["parameter_scales"]["k"] == 1.0
    assert plan["applied"] is False


def test_provenance_snapshot_skips_absent_and_unimportable_modules(monkeypatch):
    model = _model(
        variables=[VariableSpec(name="x", initial=1.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    monkeypatch.setattr(core, "_module_present", lambda name: False)
    versions = core.provenance_snapshot(model, seed=7, data_hash="abc")["tool_versions"]
    assert set(versions) == {"python", "numpy", "scipy", "sympy"}

    monkeypatch.setattr(core, "_module_present", lambda name: name == "z3")
    monkeypatch.setitem(sys.modules, "z3", None)
    snapshot = core.provenance_snapshot(model, seed=8)
    assert snapshot["tool_versions"]["z3"] == "available"
    assert snapshot["seed"] == 8
    assert snapshot["model_family"] == "ode"


def test_export_model_yaml_present_absent_and_invalid(monkeypatch):
    model = _model(
        variables=[VariableSpec(name="x", initial=1.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    yaml_out = _fresh.export_model(model, format="yaml")
    assert yaml_out["format"] == "yaml"
    assert "name: core" in yaml_out["content"]

    monkeypatch.setattr(_fresh, "_module_present", lambda name: False)
    absent = _fresh.export_model(model, format="yml")
    assert absent["status"] == "TOOL_UNAVAILABLE"
    assert absent["format"] == "yml"

    adapter = _fresh.export_model(model, format="sbml")
    assert adapter["status"] == "ADAPTER_REQUIRED"
    assert adapter["portable_ir"]["name"] == "core"

    with pytest.raises(ValueError, match="format must be"):
        _fresh.export_model(model, format="docx")
