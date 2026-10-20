"""Coverage hardening round 2a: advanced engines (PDE, DAE, optimization)."""

from __future__ import annotations

import math
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.integrate
import scipy.optimize

from axiomize import advanced_family_engine as adv
from axiomize.model_ir import (
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    SolverSpec,
    VariableSpec,
)


def _model(family, *, variables=None, parameters=None, equations=None, metadata=None, solver=None):
    kwargs = {}
    if solver is not None:
        kwargs["solver"] = solver
    return ModelIR(
        name=f"{family.value}-model",
        domain="test",
        family=family,
        variables=list(variables or []),
        parameters=list(parameters or []),
        equations=list(equations or []),
        metadata=dict(metadata or {}),
        **kwargs,
    )


def _pde(metadata, *, variables=None, equations=None) -> ModelIR:
    return _model(
        ModelFamily.PDE,
        variables=variables or [VariableSpec(name="u")],
        parameters=[ParameterSpec(name="k", value=1.0)],
        equations=equations or [EquationSpec(target="u", expression="-u", kind="derivative")],
        metadata=metadata,
    )


def _run_pde(model, points=6):
    return adv._simulate_pde(model, t_span=(0.0, 0.5), points=points, parameter_overrides=None, seed=0)


def _dae(*, variables, equations, parameters=None) -> ModelIR:
    return _model(
        ModelFamily.DAE,
        variables=variables,
        parameters=parameters or [ParameterSpec(name="k", value=1.0)],
        equations=equations,
    )


def _run_dae(model, points=6):
    return adv._simulate_dae(model, t_span=(0.0, 0.5), points=points, parameter_overrides=None, seed=0)


def test_dispatch_without_executor_is_explicitly_routed():
    ode = _model(
        ModelFamily.ODE,
        variables=[VariableSpec(name="x", initial=1.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    out = adv.simulate_advanced_family(
        ode,
        t_span=(0.0, 1.0),
        points=3,
        parameter_overrides=None,
        seed=0,
        validate_fn=lambda *args, **kwargs: {"status": "PASS"},
        simulate_fn=lambda *args, **kwargs: {"status": "PASS"},
    )
    assert out["status"] == "TOOL_ROUTE_REQUIRED"
    assert out["family"] == "ode"
    assert "no advanced native executor" in out["detail"]


def test_pde_configuration_and_profile_errors():
    with pytest.raises(ValueError, match="metadata.pde must be an object"):
        _run_pde(_pde({"pde": "bad"}))
    with pytest.raises(ValueError, match="missing derivative equations"):
        _run_pde(
            _model(
                ModelFamily.PDE,
                variables=[VariableSpec(name="u", initial=1.0)],
                equations=[],
                metadata={"pde": {"grid_points": 8}},
            )
        )
    with pytest.raises(ValueError, match="must have grid length"):
        _run_pde(
            _pde(
                {"pde": {"grid_points": 8, "initial_profiles": {"u": [1.0, 2.0]}}},
            )
        )
    with pytest.raises(ValueError, match="needs initial or metadata.pde.initial_profiles"):
        _run_pde(_pde({"pde": {"grid_points": 8}}))


def test_pde_scalar_initial_profile_broadcast():
    out = _run_pde(
        _pde({"pde": {"grid_points": 8, "initial_profiles": {"u": "1.0"}, "diffusion": 0.0}}),
    )
    assert out["status"] == "PASS"
    grid = np.asarray(out["states"]["u"], dtype=float)
    assert grid.shape == (6, 8)
    assert np.allclose(grid[0], 1.0)
    assert grid[-1].mean() == pytest.approx(math.exp(-0.5), rel=5e-3)


def test_pde_string_profile_wrong_grid_shape(monkeypatch):
    original = adv._compile_expression

    def guarded(expression, names):
        if expression == "wrong_length_profile":
            return lambda *args: np.ones(3)
        return original(expression, names)

    monkeypatch.setattr(adv, "_compile_expression", guarded)
    with pytest.raises(ValueError, match="initial profile for 'u' must evaluate to grid length 8"):
        _run_pde(
            _pde(
                {"pde": {"grid_points": 8, "initial_profiles": {"u": "wrong_length_profile"}}},
            )
        )


def _dae_model() -> ModelIR:
    return _dae(
        variables=[
            VariableSpec(name="x", initial=1.0),
            VariableSpec(name="z", initial=1.0, role="latent"),
        ],
        equations=[
            EquationSpec(target="x", expression="-z", kind="derivative"),
            EquationSpec(target="z", expression="k*x", kind="algebraic"),
        ],
    )


def test_dae_algebraic_equation_and_argument_errors():
    out = _run_dae(_dae_model())
    assert out["status"] == "PASS"
    assert set(out["states"]) == {"x", "z"}
    assert out["diagnostics"]["max_algebraic_residual"] < 1e-6
    assert out["states"]["x"][-1] == pytest.approx(math.exp(-0.5), rel=5e-3)

    with pytest.raises(ValueError, match="both differential and algebraic"):
        _run_dae(
            _dae(
                variables=[VariableSpec(name="x", initial=1.0)],
                equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
            )
        )
    with pytest.raises(ValueError, match="one residual per algebraic variable"):
        _run_dae(
            _dae(
                variables=[
                    VariableSpec(name="x", initial=1.0),
                    VariableSpec(name="z", initial=1.0, role="latent"),
                ],
                equations=[EquationSpec(target="x", expression="-z", kind="derivative")],
            )
        )
    with pytest.raises(ValueError, match="finite initial values"):
        _run_dae(
            _dae(
                variables=[
                    VariableSpec(name="x"),
                    VariableSpec(name="z", initial=1.0, role="latent"),
                ],
                equations=[
                    EquationSpec(target="x", expression="-z", kind="derivative"),
                    EquationSpec(target="z", expression="k*x", kind="residual"),
                ],
            )
        )


def test_dae_algebraic_root_fallback_and_failure(monkeypatch):
    calls = []

    def fake_root(fun, x0, method=None):
        calls.append(method)
        guess = np.asarray(x0, dtype=float)
        if method == "hybr":
            return SimpleNamespace(success=False, x=guess, message="hybr failed")
        return SimpleNamespace(success=True, x=guess, message="lm ok")

    monkeypatch.setattr(scipy.optimize, "root", fake_root)
    out = _run_dae(_dae_model())
    assert out["status"] == "PASS"
    assert calls[0] == "hybr" and calls[1] == "lm"

    calls.clear()

    def always_fail(fun, x0, method=None):
        calls.append(method)
        guess = np.asarray(x0, dtype=float)
        return SimpleNamespace(success=False, x=guess, message="no root")

    monkeypatch.setattr(scipy.optimize, "root", always_fail)
    with pytest.raises(RuntimeError, match="algebraic solve failed"):
        _run_dae(_dae_model())
    assert calls == ["hybr", "lm"]


def test_dae_solver_attempt_failures(monkeypatch):
    calls = []

    def fake_solve_ivp(rhs, span, y0, t_eval=None, method=None, rtol=None, atol=None):
        calls.append(method)
        if len(calls) == 1:
            return SimpleNamespace(success=False, message="stiff refusal", y=np.zeros((2, 1)))
        raise FloatingPointError("integration exploded")

    monkeypatch.setattr(scipy.integrate, "solve_ivp", fake_solve_ivp)
    out = _run_dae(_dae_model())
    assert out["status"] == "FAIL"
    assert out["stage"] == "dae_solve"
    assert [attempt["success"] for attempt in out["solver_attempts"]] == [False, False, False]
    assert out["solver_attempts"][0]["message"] == "stiff refusal"
    assert out["solver_attempts"][1]["message"].startswith("FloatingPointError")
    assert calls == ["BDF", "Radau", "DOP853"]


def _optimization(**metadata) -> ModelIR:
    cfg = metadata.pop("cfg", {})
    return _model(
        ModelFamily.OPTIMIZATION,
        variables=metadata.pop(
            "variables",
            [VariableSpec(name="x", role="decision", initial=0.0, bounds=(-10.0, 10.0))],
        ),
        equations=metadata.pop(
            "equations",
            [EquationSpec(target="", expression="(x-3)**2", kind="objective")],
        ),
        metadata={"optimization": cfg} if cfg else {},
        **metadata,
    )


def _run_optimization(model):
    return adv._solve_optimization(
        model, t_span=(0.0, 1.0), points=4, parameter_overrides=None, seed=0
    )


def test_optimization_configuration_and_objective_sources():
    with pytest.raises(ValueError, match="metadata.optimization must be an object"):
        _run_optimization(
            _model(
                ModelFamily.OPTIMIZATION,
                variables=[VariableSpec(name="x", role="decision", initial=0.0)],
                equations=[EquationSpec(target="", expression="x**2", kind="objective")],
                metadata={"optimization": "bad"},
            )
        )
    with pytest.raises(ValueError, match="requires decision variables"):
        _run_optimization(
            _model(
                ModelFamily.OPTIMIZATION,
                variables=[],
                equations=[EquationSpec(target="", expression="1", kind="objective")],
                metadata={"optimization": {"objective": "1"}},
            )
        )
    out = _run_optimization(_optimization())
    assert out["status"] == "PASS"
    assert out["states"]["x"] == pytest.approx(3.0, abs=2e-4)
    assert out["objective"]["value"] < 1e-7

    with pytest.raises(ValueError, match="requires metadata.optimization.objective"):
        _run_optimization(
            _model(
                ModelFamily.OPTIMIZATION,
                variables=[VariableSpec(name="x", role="decision", initial=0.0)],
                equations=[],
                metadata={"optimization": {}},
            )
        )


def test_optimization_method_fallback_and_exception(monkeypatch):
    def failing_then_ok(fun, x0, method=None, bounds=None, constraints=None, options=None):
        if method == "SLSQP":
            return SimpleNamespace(success=False, x=np.asarray([0.5]), message="SLSQP stalled", nit=2)
        return SimpleNamespace(success=True, x=np.asarray([3.0]), message="ok", nit=3)

    monkeypatch.setattr(scipy.optimize, "minimize", failing_then_ok)
    model = _optimization(solver=SolverSpec(method="BFGS"))
    out = _run_optimization(model)
    assert out["status"] == "PASS"
    assert [attempt["method"] for attempt in out["solver"]["attempts"]] == ["SLSQP", "trust-constr"]
    assert out["solver"]["attempts"][0]["success"] is False
    assert out["states"]["x"] == pytest.approx(3.0)

    def raising_then_ok(fun, x0, method=None, bounds=None, constraints=None, options=None):
        if method == "SLSQP":
            raise RuntimeError("bad gradient")
        return SimpleNamespace(success=True, x=np.asarray([2.5]), message="ok", nit=1)

    monkeypatch.setattr(scipy.optimize, "minimize", raising_then_ok)
    out = _run_optimization(_optimization())
    assert out["status"] == "PASS"
    assert out["solver"]["attempts"][0]["message"].startswith("RuntimeError")
    assert out["states"]["x"] == pytest.approx(2.5)

    def always_fail(fun, x0, method=None, bounds=None, constraints=None, options=None):
        return SimpleNamespace(success=False, x=np.asarray([0.0]), message="nope", nit=1)

    monkeypatch.setattr(scipy.optimize, "minimize", always_fail)
    out = _run_optimization(_optimization())
    assert out["status"] == "FAIL"
    assert out["stage"] == "optimization"
    assert [attempt["success"] for attempt in out["solver_attempts"]] == [False, False]


def test_optimization_nonfinite_candidate_keeps_initial_guess(monkeypatch):
    starts = []

    def nonfinite_then_ok(fun, x0, method=None, bounds=None, constraints=None, options=None):
        starts.append(np.asarray(x0, dtype=float).copy())
        if method == "SLSQP":
            return SimpleNamespace(success=False, x=np.asarray([np.nan]), message="not finite", nit=1)
        return SimpleNamespace(success=True, x=np.asarray([1.5]), message="ok", nit=1)

    monkeypatch.setattr(scipy.optimize, "minimize", nonfinite_then_ok)
    out = _run_optimization(_optimization())
    assert out["status"] == "PASS"
    assert [attempt["method"] for attempt in out["solver"]["attempts"]] == ["SLSQP", "trust-constr"]
    assert [start.tolist() for start in starts] == [[0.0], [0.0]]
    assert out["states"]["x"] == pytest.approx(1.5)
