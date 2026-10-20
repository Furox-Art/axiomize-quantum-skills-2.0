"""Round-3 coverage completion for SciPy, CasADi, CVXPY, SymPy and SCS adapters."""

from __future__ import annotations

import math
import sys
import types

import numpy as np
import pytest
import scipy.integrate
import sympy

from axiomize.integrations import scs_adapter
from axiomize.tools.numerical import scipy_tool
from axiomize.tools.numerical.scipy_tool import SciPyTool, solve_sir
from axiomize.tools.optimization import casadi_tool, cvxpy_tool
from axiomize.tools.symbolic import sympy_tool
from axiomize.tools.symbolic.sympy_tool import SymPyTool
from axiomize.tools.optimization.casadi_tool import CasadiTool
from axiomize.validation.status import ValidationStatus


# --------------------------------------------------------------------------- #
# scipy_tool
# --------------------------------------------------------------------------- #

def _fake_ivp(y, t):
    class Result:
        success = True

        def __init__(self):
            self.y = y
            self.t = t

    return lambda *args, **kwargs: Result()


def test_solve_sir_rejects_malformed_solution_array(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scipy.integrate,
        "solve_ivp",
        _fake_ivp(np.zeros((2, 2)), np.array([0.0, 1.0])),
    )
    result = solve_sir(0.3, 0.1, 10.0, 1000.0)
    assert result.success is False
    assert math.isnan(result.final_size)
    assert result.max_conservation_error == math.inf
    assert result.max_residual == math.inf


def test_solve_sir_single_sample_marks_residual_infinite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        scipy.integrate,
        "solve_ivp",
        _fake_ivp(np.zeros((3, 1)), np.array([0.0])),
    )
    result = solve_sir(0.3, 0.1, 10.0, 1000.0)
    assert result.final_size == 0.0
    assert result.max_conservation_error == 1000.0
    assert result.max_residual == math.inf
    assert result.success is False


def test_scipy_tool_metadata_reports_live_backend() -> None:
    meta = SciPyTool().metadata()
    assert meta.name == "scipy"
    assert meta.available is True
    assert "ode_solve" in meta.capabilities


# --------------------------------------------------------------------------- #
# casadi_tool
# --------------------------------------------------------------------------- #

def test_casadi_validate_requires_x0() -> None:
    tool = CasadiTool()
    with pytest.raises(ValueError, match="payload needs 'x0'"):
        tool.validate_input({})


def test_casadi_rejects_non_numeric_initial_point() -> None:
    with pytest.raises(ValueError, match="numeric length-2 array"):
        casadi_tool._validate_rosenbrock_x0(["left", "right"])


def test_casadi_rejects_out_of_range_initial_point() -> None:
    with pytest.raises(ValueError, match="finite with"):
        casadi_tool._validate_rosenbrock_x0([1e13, 0.0])


def test_casadi_execute_solves_rosenbrock() -> None:
    result = CasadiTool().execute({"problem": "rosenbrock", "x0": [-1.2, 1.0]})
    assert result["success"] is True
    assert result["initial_x"] == [-1.2, 1.0]
    assert result["x"][0] == pytest.approx(1.0, abs=1e-6)
    assert result["x"][1] == pytest.approx(1.0, abs=1e-6)
    assert result["objective"] == pytest.approx(0.0, abs=1e-6)


class _FakeCasadiExpression:
    def __getitem__(self, index):
        return self

    def __pow__(self, exponent):
        return self

    def __rpow__(self, base):
        return self

    def __mul__(self, other):
        return self

    def __rmul__(self, other):
        return self

    def __add__(self, other):
        return self

    def __radd__(self, other):
        return self

    def __sub__(self, other):
        return self

    def __rsub__(self, other):
        return self


class _FakeCasadiMatrix:
    def full(self):
        return self

    def ravel(self):
        return [0.5]


class _FakeCasadiSolver:
    def __call__(self, **kwargs):
        return {"x": _FakeCasadiMatrix(), "f": 0.0}

    def stats(self):
        return {"success": True, "return_status": "Solve_Succeeded"}


def test_casadi_rejects_malformed_solver_result(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("casadi")
    fake.SX = types.SimpleNamespace(sym=lambda name, size: _FakeCasadiExpression())
    fake.nlpsol = lambda *args, **kwargs: _FakeCasadiSolver()
    monkeypatch.setitem(sys.modules, "casadi", fake)
    with pytest.raises(RuntimeError, match="non-finite or malformed"):
        casadi_tool.solve_rosenbrock((0.0, 0.0))


# --------------------------------------------------------------------------- #
# cvxpy_tool
# --------------------------------------------------------------------------- #

def test_cvxpy_rejects_empty_constraint_matrix() -> None:
    with pytest.raises(ValueError, match="G row count must be in"):
        cvxpy_tool._validated_qp([[1.0]], [1.0], np.zeros((0, 1)), np.zeros((0,)))


class _FakeCvxpyExpression:
    __array_priority__ = 1000

    def __init__(self, variable=None):
        self._variable = variable

    def __getattr__(self, item):
        if item == "value":
            return None
        raise AttributeError(item)

    def __mul__(self, other):
        return self

    def __rmul__(self, other):
        return self

    def __add__(self, other):
        return self

    def __radd__(self, other):
        return self

    def __matmul__(self, other):
        return self

    def __rmatmul__(self, other):
        return self


class _FakeCvxpyVariable(_FakeCvxpyExpression):
    created: list["_FakeCvxpyVariable"] = []

    def __init__(self, size):
        super().__init__(self)
        self.size = size
        self.value = None
        _FakeCvxpyVariable.created.append(self)


class _FakeCvxpyProblem:
    def __init__(self, objective, constraints):
        self.objective = objective
        self.constraints = constraints
        self.status = "optimal"
        self.value = 1.0

    def solve(self, **kwargs):
        _FakeCvxpyVariable.created[-1].value = np.array([np.nan])


def test_cvxpy_rejects_non_finite_solution(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = types.ModuleType("cvxpy")
    fake.Variable = _FakeCvxpyVariable
    fake.Minimize = lambda expression: expression
    fake.quad_form = lambda variable, matrix: _FakeCvxpyExpression(variable)
    fake.Problem = _FakeCvxpyProblem
    fake.CLARABEL = "CLARABEL"
    fake.OPTIMAL = "optimal"
    fake.OPTIMAL_INACCURATE = "optimal_inaccurate"
    fake.error = types.SimpleNamespace(SolverError=type("SolverError", (Exception,), {}))
    monkeypatch.setitem(sys.modules, "cvxpy", fake)
    _FakeCvxpyVariable.created.clear()
    with pytest.raises(RuntimeError, match="non-finite or malformed solution"):
        cvxpy_tool.solve_qp([[2.0]], [1.0])


# --------------------------------------------------------------------------- #
# sympy_tool
# --------------------------------------------------------------------------- #

def test_sympy_symbol_namespace_limit_is_enforced() -> None:
    extra = tuple(f"v{index}" for index in range(3001))
    with pytest.raises(ValueError, match="namespace exceeds hard symbol limit"):
        sympy_tool._symbols_for("x", extra=extra)


def test_sympy_tool_metadata_reports_live_backend() -> None:
    meta = SymPyTool().metadata()
    assert meta.name == "sympy"
    assert meta.available is True
    assert "simplify" in meta.capabilities


def test_sympy_rejects_out_of_range_symbolic_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sympy, "nsolve", lambda *args, **kwargs: 1.5)
    with pytest.raises(RuntimeError, match="outside \\[0, 1\\]"):
        sympy_tool.final_size_symbolic(2.0)


def test_sympy_rejects_excessive_singularity_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sympy, "solve", lambda *args, **kwargs: list(range(2001)))
    with pytest.raises(ValueError, match="exceeds hard result count"):
        sympy_tool.find_singularities("1/x", "x")


# --------------------------------------------------------------------------- #
# scs_adapter
# --------------------------------------------------------------------------- #

def _install_fake_cds(monkeypatch: pytest.MonkeyPatch, states_factory):
    captured = {}

    def solve_system(rhs, t0, y0, days, dt):
        captured["rhs"] = rhs(t0, list(y0))
        captured["y0"] = list(y0)
        captured["days"] = days
        captured["dt"] = dt
        return [t0, days], states_factory(list(y0))

    package = types.ModuleType("cds")
    diffeq = types.ModuleType("cds.diffeq")
    diffeq.solve_system = solve_system
    package.diffeq = diffeq
    monkeypatch.setitem(sys.modules, "cds", package)
    monkeypatch.setitem(sys.modules, "cds.diffeq", diffeq)
    return captured


def test_solve_sir_cds_uses_injected_zero_dependency_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_fake_cds(
        monkeypatch, lambda y0: [list(y0), [0.0, 0.0, 5.0]]
    )
    result = scs_adapter.solve_sir_cds(beta=0.5, gamma=0.2, I0=10.0, N=100.0, days=30.0, dt=0.1)
    assert result["final_size"] == pytest.approx(0.05)
    assert result["t"] == [0.0, 30.0]
    assert captured["y0"] == [90.0, 10.0, 0.0]
    assert captured["days"] == 30.0
    assert captured["dt"] == 0.1
    assert captured["rhs"] == pytest.approx([-4.5, 2.5, 2.0])


def test_cross_validate_reports_tool_unavailable_without_cds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(scs_adapter, "scs_probe", lambda: {"cds": False, "cds2": False})
    result = scs_adapter.cross_validate_sir(0.4, 0.2, 10.0, 500.0)
    assert result.status is ValidationStatus.TOOL_UNAVAILABLE
    assert result.primary_result is None
    assert result.verification_result is None
    assert result.recommended_action


def test_cross_validate_compares_scipy_with_cds(monkeypatch: pytest.MonkeyPatch) -> None:
    primary = solve_sir(0.4, 0.2, 10.0, 500.0, days=60.0).final_size
    _install_fake_cds(monkeypatch, lambda y0: [list(y0), [0.0, 0.0, primary * 500.0]])
    monkeypatch.setattr(scs_adapter, "scs_probe", lambda: {"cds": True, "cds2": False})
    result = scs_adapter.cross_validate_sir(0.4, 0.2, 10.0, 500.0, days=60.0)
    assert result.status is ValidationStatus.PASS
    assert result.primary_result == pytest.approx(primary)
    assert result.verification_result == pytest.approx(primary)
    assert result.difference == pytest.approx(0.0)
    assert result.recommended_action == []
