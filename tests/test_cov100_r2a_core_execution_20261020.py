"""Coverage hardening round 2a: general_engine_core execution and fitting."""

from __future__ import annotations

import importlib.util
import math
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.integrate

import axiomize.general_engine_core as core
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec

_spec = importlib.util.spec_from_file_location("axiomize_cov_r2a_core_exec", core.__file__)
assert _spec is not None and _spec.loader is not None
_fresh = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fresh)


def _model(
    family: ModelFamily = ModelFamily.ODE,
    *,
    variables=None,
    parameters=None,
    equations=None,
    metadata=None,
) -> ModelIR:
    return ModelIR(
        name="exec",
        domain="test",
        family=family,
        variables=list(variables or []),
        parameters=list(parameters or []),
        equations=list(equations or []),
        metadata=dict(metadata or {}),
    )


def _ode(**kwargs) -> ModelIR:
    defaults = dict(
        variables=[VariableSpec(name="x", initial=1.0)],
        parameters=[ParameterSpec(name="k", value=1.0)],
        equations=[EquationSpec(target="x", expression="-k*x", kind="derivative")],
    )
    defaults.update(kwargs)
    return _model(ModelFamily.ODE, **defaults)


def test_core_simulate_structure_approval_and_route():
    broken = _model(
        ModelFamily.ODE,
        variables=[VariableSpec(name="x", initial=1.0), VariableSpec(name="x", initial=2.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    out = _fresh.simulate_model(broken)
    assert out["status"] == "FAIL"
    assert out["stage"] == "structure"

    pde = _model(
        ModelFamily.PDE,
        variables=[VariableSpec(name="u", initial=1.0)],
        equations=[EquationSpec(target="u", expression="-u", kind="derivative")],
    )
    approval = _fresh.simulate_model(pde, points=70000)
    assert approval["status"] == "APPROVAL_REQUIRED"
    assert approval["plan"]["approval_required"] is True

    routed = _fresh.simulate_model(pde, points=10)
    assert routed["status"] == "TOOL_ROUTE_REQUIRED"
    assert routed["family"] == "pde"
    assert routed["solver"]["backend"] in {"scipy", "fenics"}


def test_core_ode_missing_initial_and_bad_span():
    missing = _model(
        ModelFamily.ODE,
        variables=[VariableSpec(name="x")],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    with pytest.raises(ValueError, match="needs an initial value"):
        _fresh.simulate_model(missing)

    with pytest.raises(ValueError, match="t_span must be finite and increasing"):
        _fresh.simulate_model(_ode(), t_span=(1.0, 0.5), points=5)


def test_core_ode_solver_attempt_failures(monkeypatch):
    calls = []

    def fake_solve_ivp(rhs, span, y0, t_eval=None, method=None, rtol=None, atol=None):
        calls.append(method)
        if len(calls) == 1:
            return SimpleNamespace(success=False, message="no convergence")
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(scipy.integrate, "solve_ivp", fake_solve_ivp)
    out = _fresh.simulate_model(_ode(), t_span=(0.0, 1.0), points=5)
    assert out["status"] == "FAIL"
    assert out["stage"] == "solve"
    assert len(out["solver_attempts"]) == 4
    assert out["solver_attempts"][0]["message"] == "no convergence"
    assert all(attempt["success"] is False for attempt in out["solver_attempts"])
    assert any(attempt["message"].startswith("RuntimeError") for attempt in out["solver_attempts"])
    assert calls[0] == "DOP853"


def _sde_model(metadata=None, initial=1.0) -> ModelIR:
    return _model(
        ModelFamily.STOCHASTIC,
        variables=[VariableSpec(name="x", initial=initial)],
        parameters=[ParameterSpec(name="k", value=1.0)],
        equations=[EquationSpec(target="x", expression="-k*x", kind="derivative")],
        metadata=metadata or {},
    )


def test_core_sde_initial_span_and_diffusion_errors():
    with pytest.raises(ValueError, match="need finite initial values"):
        _fresh.simulate_model(_sde_model(initial=None), points=5)
    with pytest.raises(ValueError, match="t_span must be increasing"):
        _fresh.simulate_model(_sde_model(), t_span=(1.0, 0.5), points=5)
    with pytest.raises(ValueError, match="metadata.diffusion must be an object"):
        _fresh.simulate_model(_sde_model(metadata={"diffusion": "bad"}), points=5)


def _fit_model(*, params=None, variables=None, expression="-k*x") -> ModelIR:
    return _model(
        ModelFamily.ODE,
        variables=variables or [VariableSpec(name="x", initial=1.0)],
        parameters=params or [ParameterSpec(name="k", value=1.0, fit=True)],
        equations=[EquationSpec(target="x", expression=expression, kind="derivative")],
    )


def test_fit_ode_model_route_approval_and_argument_errors():
    routed = core.fit_ode_model(
        _model(ModelFamily.BAYESIAN, variables=[VariableSpec(name="x", initial=1.0)]),
        time=[0.0, 0.5, 1.0],
        observations={},
    )
    assert routed["status"] == "TOOL_ROUTE_REQUIRED"

    approval = core.fit_ode_model(
        _fit_model(),
        time=[index * 0.001 for index in range(100000)],
        observations={},
    )
    assert approval["status"] == "APPROVAL_REQUIRED"

    with pytest.raises(ValueError, match="strictly increasing"):
        core.fit_ode_model(_fit_model(), time=[0.0, 1.0, 1.0], observations={"x": [1.0, 1.0, 1.0]})
    with pytest.raises(ValueError, match="fit=true"):
        core.fit_ode_model(
            _fit_model(params=[ParameterSpec(name="k", value=1.0)]),
            time=[0.0, 0.5, 1.0],
            observations={"x": [1.0, 1.0, 1.0]},
        )
    with pytest.raises(ValueError, match="length must match time"):
        core.fit_ode_model(_fit_model(), time=[0.0, 0.5, 1.0], observations={"x": [1.0, 1.0]})
    with pytest.raises(ValueError, match="unknown states"):
        core.fit_ode_model(_fit_model(), time=[0.0, 0.5, 1.0], observations={"y": [1.0, 1.0, 1.0]})
    with pytest.raises(ValueError, match="needs an initial value"):
        core.fit_ode_model(
            _fit_model(params=[ParameterSpec(name="k", fit=True)]),
            time=[0.0, 0.5, 1.0],
            observations={"x": [1.0, 1.0, 1.0]},
        )


def test_fit_ode_model_propagates_prediction_failure(monkeypatch):
    monkeypatch.setattr(core, "_simulate_ode", lambda *args, **kwargs: {"status": "FAIL", "stage": "solve"})
    with pytest.raises(RuntimeError, match="ODE simulation failed during fitting"):
        core.fit_ode_model(
            _fit_model(),
            time=[0.0, 0.5, 1.0],
            observations={"x": [1.0, 0.6, 0.4]},
        )


def test_fit_ode_model_identifiability_paths(monkeypatch):
    times = [0.0, 0.5, 1.0]
    observations = {"x": [1.0, 0.6, 0.4]}
    crowded = _fit_model(
        params=[
            ParameterSpec(name="k", value=1.0, fit=True),
            ParameterSpec(name="a", value=1.0, fit=True),
            ParameterSpec(name="b", value=1.0, fit=True),
        ]
    )
    out = core.fit_ode_model(crowded, time=times, observations=observations)
    assert out["status"] == "PASS"
    assert out["identifiability"]["identifiable"] is False
    assert out["covariance"] is None
    assert all(value is None for value in out["stderr"].values())

    def raising_inv(matrix):
        raise np.linalg.LinAlgError("singular")

    monkeypatch.setattr(np.linalg, "inv", raising_inv)
    out = core.fit_ode_model(_fit_model(), time=times, observations=observations)
    assert out["status"] == "PASS"
    assert out["identifiability"]["identifiable"] is False
    assert out["covariance"] is None
    assert out["stderr"]["k"] is None


def test_discover_sparse_dynamics_validation_and_modes():
    with pytest.raises(ValueError, match="same-length increasing"):
        core.discover_sparse_dynamics(time=[0.0, 1.0], state=[1.0, 2.0])
    time = np.linspace(0.0, 1.0, 12)
    with pytest.raises(ValueError, match="degree must be between 1 and 5"):
        core.discover_sparse_dynamics(time=time.tolist(), state=np.ones(12).tolist(), degree=0)

    gate = core.discover_sparse_dynamics(time=time.tolist(), state=np.ones(12).tolist(), degree=2)
    assert gate["status"] == "APPROVAL_REQUIRED"

    constant = core.discover_sparse_dynamics(
        time=time.tolist(), state=np.ones(12).tolist(), degree=2, approve_heavy=True
    )
    assert constant["status"] == "PASS"
    assert constant["candidate_terms"] == []

    decay = np.exp(-time)
    discovered = core.discover_sparse_dynamics(
        time=time.tolist(), state=decay.tolist(), degree=2, threshold=1e-6, approve_heavy=True
    )
    assert discovered["status"] == "PASS"
    coefficients = {term["term"]: term["coefficient"] for term in discovered["candidate_terms"]}
    assert -1.4 < coefficients["x"] < -0.8
    assert 0.0 <= discovered["rmse_derivative"] < 5e-2
    assert math.isfinite(discovered["rmse_derivative"])
