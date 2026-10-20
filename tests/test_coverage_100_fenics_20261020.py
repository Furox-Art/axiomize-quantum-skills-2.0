"""Coverage hardening for the FEniCS adapter using structured backend fakes.

The fakes implement only the small DOLFINx/legacy API surface the adapter
uses; assertions still target the adapter's validation, dispatch, and result
contracts rather than the fake solvers.
"""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from axiomize.tools.pde.fenics_tool import FEniCSAdapter, _finite


class _Expr:
    def __init__(self, value=None):
        self.value = value

    def __mul__(self, other):
        return _Expr()

    __rmul__ = __mul__

    def __add__(self, other):
        return _Expr()

    __radd__ = __add__

    def __sub__(self, other):
        return _Expr()

    def __rsub__(self, other):
        return _Expr()

    def __pow__(self, power):
        return _Expr()

    def __neg__(self):
        return _Expr()

    def __eq__(self, other):
        return _Expr()


class _Function:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=float)
        self.x = types.SimpleNamespace(array=np.array(self._values, dtype=float))

    def vector(self):
        holder = self

        class _Vector:
            def get_local(self):
                return holder._values

        return _Vector()

    def __mul__(self, other):
        return _Expr()

    __rmul__ = __mul__

    def __pow__(self, power):
        return _Expr()


class _Domain:
    def __init__(self, dim):
        self.topology = types.SimpleNamespace(dim=dim)


class _Space:
    def __init__(self, n=4):
        self.n = n

    def dim(self):
        return self.n


def _install_module(monkeypatch, name, module):
    monkeypatch.setitem(sys.modules, name, module)


def _fake_mpi(size=1):
    module = types.ModuleType("mpi4py")
    module.MPI = types.SimpleNamespace(COMM_WORLD=types.SimpleNamespace(size=size))
    return module


def _fake_ufl():
    module = types.ModuleType("ufl")
    module.dx = _Expr()
    module.Measure = lambda name, domain=None: _Expr()
    module.TestFunction = lambda V: _Expr()
    module.TrialFunction = lambda V: _Expr()
    module.inner = lambda a, b: _Expr()
    module.grad = lambda a: _Expr()
    return module


def _fake_dolfinx(*, solution=None, nonlinear_solution=None, l2=2.0, with_functionspace=True):
    solution = [0.0, 1.0, 2.0, 3.0] if solution is None else solution
    nonlinear_solution = [1.0, 1.0, 1.0] if nonlinear_solution is None else nonlinear_solution
    dolfinx = types.ModuleType("dolfinx")
    dolfinx.__version__ = "1.0-fake"
    dolfinx.__path__ = []
    fem = types.ModuleType("dolfinx.fem")
    fem.__path__ = []
    mesh = types.ModuleType("dolfinx.mesh")

    def functionspace(domain, element):
        return _Space()

    fem.functionspace = functionspace
    if not with_functionspace:
        del fem.functionspace
    fem.FunctionSpace = functionspace
    fem.Function = lambda V: _Function(np.zeros(V.n))
    fem.dirichletbc = lambda g, dofs: ("bc", g, dofs)
    fem.Constant = lambda domain, value: _Expr(value)
    fem.locate_dofs_topological = lambda V, fdim, facets: [0]
    fem.form = lambda expr: expr
    fem.assemble_scalar = lambda expr: l2
    dolfinx.fem = fem

    mesh.create_unit_interval = lambda comm, cells: _Domain(1)
    mesh.create_unit_square = lambda comm, cells1, cells2: _Domain(2)
    mesh.create_unit_cube = lambda comm, cells1, cells2, cells3: _Domain(3)
    mesh.locate_entities_boundary = lambda domain, fdim, marker: np.array([0])
    dolfinx.mesh = mesh

    petsc = types.ModuleType("petsc4py")
    petsc.PETSc = types.SimpleNamespace(ScalarType=float)

    class LinearProblem:
        def __init__(self, a, L, bcs, petsc_options):
            self.a = a
            self.L = L
            self.bcs = bcs
            self.petsc_options = petsc_options

        def solve(self):
            return _Function(solution)

    class NonlinearProblem:
        def __init__(self, F, u, bcs):
            self.F = F
            self.u = u
            self.bcs = bcs

    nlp = types.ModuleType("dolfinx.fem.petsc")
    nlp.LinearProblem = LinearProblem
    nlp.NonlinearProblem = NonlinearProblem
    nls = types.ModuleType("dolfinx.nls.petsc")

    class NewtonSolver:
        def __init__(self, comm, problem):
            self.comm = comm
            self.problem = problem

        def solve(self, u):
            u.x.array = np.asarray(nonlinear_solution, dtype=float)

    nls.NewtonSolver = NewtonSolver
    return {
        "dolfinx": dolfinx,
        "dolfinx.fem": fem,
        "dolfinx.fem.petsc": nlp,
        "dolfinx.mesh": mesh,
        "dolfinx.nls": types.ModuleType("dolfinx.nls"),
        "dolfinx.nls.petsc": nls,
        "petsc4py": petsc,
    }


def _fake_fenics(*, solution=None, nonlinear_solution=None, l2=2.0):
    solution = [0.0, 1.0, 2.0, 3.0] if solution is None else solution
    nonlinear_solution = [2.0, 3.0] if nonlinear_solution is None else nonlinear_solution
    fe = types.ModuleType("fenics")
    fe.__version__ = "9.0-legacy"
    fe.UnitIntervalMesh = lambda cells: _Domain(1)
    fe.UnitSquareMesh = lambda cells1, cells2: _Domain(2)
    fe.UnitCubeMesh = lambda cells1, cells2, cells3: _Domain(3)
    fe.FunctionSpace = lambda domain, family, degree: _Space()
    fe.TestFunction = lambda V: _Expr()
    fe.TrialFunction = lambda V: _Expr()
    fe.Measure = lambda name: _Expr()
    fe.dx = _Expr()
    fe.Constant = _Expr
    fe.DirichletBC = lambda V, value, marker: ("bc", value, marker)
    fe.dot = lambda a, b: _Expr()
    fe.grad = lambda a: _Expr()

    def make_function(V):
        return _Function(np.zeros(V.n))

    fe.Function = make_function

    def solve(eq, uh, bc):
        uh._values = np.asarray(solution, dtype=float)
        uh.x.array = np.asarray(solution, dtype=float)

    fe.solve = solve
    fe.NonlinearVariationalProblem = lambda F, u, bc: ("nlp", F, u, bc)
    fe.NonlinearVariationalSolver = lambda problem: types.SimpleNamespace(
        solve=lambda u: setattr(u, "_values", np.asarray(nonlinear_solution, dtype=float))
    )
    fe.norm = lambda u, kind: l2
    return fe


def _install_dolfinx(monkeypatch, **kwargs):
    modules = _fake_dolfinx(**kwargs)
    for name, module in modules.items():
        _install_module(monkeypatch, name, module)
    _install_module(monkeypatch, "mpi4py", _fake_mpi())
    _install_module(monkeypatch, "ufl", _fake_ufl())
    _install_module(monkeypatch, "fenics", None)


def _install_legacy(monkeypatch, **kwargs):
    for name in list(_fake_dolfinx()):
        _install_module(monkeypatch, name, None)
    _install_module(monkeypatch, "mpi4py", None)
    _install_module(monkeypatch, "ufl", None)
    _install_module(monkeypatch, "fenics", _fake_fenics(**kwargs))


def test_finite_validation():
    assert _finite("2", "x") == 2.0
    with pytest.raises(ValueError, match="must be numeric"):
        _finite(None, "x")
    with pytest.raises(ValueError, match="must be finite"):
        _finite(float("inf"), "x")


def test_probe_backend_dolfinx_and_legacy(monkeypatch):
    _install_dolfinx(monkeypatch)
    assert FEniCSAdapter._probe_backend() == ("dolfinx", "1.0-fake")
    assert FEniCSAdapter._probe_version() == "dolfinx-1.0-fake"
    meta = FEniCSAdapter.availability()
    assert meta.available and meta.version == "dolfinx-1.0-fake"
    assert "dolfinx" in meta.reason

    _install_legacy(monkeypatch)
    assert FEniCSAdapter._probe_backend() == ("fenics", "9.0-legacy")
    meta = FEniCSAdapter.availability()
    assert meta.available and meta.version == "fenics-9.0-legacy"


def test_availability_reports_missing_backends(monkeypatch):
    for name in list(_fake_dolfinx()) + ["fenics"]:
        _install_module(monkeypatch, name, None)
    meta = FEniCSAdapter.availability()
    assert meta.available is False
    assert "neither DOLFINx nor legacy FEniCS" in meta.reason


def test_validate_input_rejections():
    tool = FEniCSAdapter()
    with pytest.raises(ValueError, match="payload must be an object"):
        tool.validate_input([])
    with pytest.raises(ValueError, match="supported problem types"):
        tool.validate_input({"problem": "heat"})
    with pytest.raises(ValueError, match="dimension must be"):
        tool.validate_input({"dimension": True})
    with pytest.raises(ValueError, match="dimension must be"):
        tool.validate_input({"dimension": 4})
    with pytest.raises(ValueError, match="cells must be an integer"):
        tool.validate_input({"cells": 2.5})
    with pytest.raises(ValueError, match="cells must be in \\[2"):
        tool.validate_input({"cells": 1})
    with pytest.raises(ValueError, match="cells must be in \\[2, 512\\]"):
        tool.validate_input({"dimension": 2, "cells": 513})
    with pytest.raises(ValueError, match="source must be numeric"):
        tool.validate_input({"source": "hot"})
    with pytest.raises(ValueError, match="dirichlet must be finite"):
        tool.validate_input({"dirichlet": float("nan")})
    with pytest.raises(ValueError, match="nonlinear_exponent must be in"):
        tool.validate_input({"problem": "nonlinear_poisson", "nonlinear_exponent": 6})
    with pytest.raises(ValueError, match="degree=1 only"):
        tool.validate_input({"degree": 2})
    tool.validate_input({"dimension": 3, "cells": 64})


def test_execute_unavailable_raises(monkeypatch):
    monkeypatch.setattr(
        FEniCSAdapter, "_probe_backend",
        classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("missing"))),
    )
    with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE: missing"):
        FEniCSAdapter().execute({})


def test_dolfinx_poisson_all_dimensions(monkeypatch):
    _install_dolfinx(monkeypatch)
    tool = FEniCSAdapter()
    for dim in (1, 2, 3):
        result = tool.execute({"dimension": dim, "cells": 4})
        assert result["status"] == "PASS"
        assert result["backend"] == "dolfinx"
        assert result["dimension"] == dim
        assert result["dofs"] == 4
        assert result["solution"]["min"] == 0.0
        assert result["solution"]["max"] == 3.0
        assert result["solution"]["l2"] == pytest.approx(np.sqrt(2.0))
        assert result["nonlinear_exponent"] == 1


def test_dolfinx_functionspace_fallback(monkeypatch):
    _install_dolfinx(monkeypatch, with_functionspace=False)
    result = FEniCSAdapter().execute({"dimension": 1, "cells": 4})
    assert result["backend"] == "dolfinx"
    assert result["dofs"] == 4


def test_dolfinx_nonlinear(monkeypatch):
    _install_dolfinx(monkeypatch, nonlinear_solution=[1.0, 1.0, 1.0])
    result = FEniCSAdapter().execute({"problem": "nonlinear_poisson", "dimension": 1, "cells": 4, "nonlinear_exponent": 2.0})
    assert result["problem"] == "nonlinear_poisson"
    assert result["nonlinear_exponent"] == 2.0
    assert result["dofs"] == 3
    assert result["solution"]["min"] == 1.0


def test_dolfinx_rejects_multiple_mpi_ranks(monkeypatch):
    _install_dolfinx(monkeypatch)
    _install_module(monkeypatch, "mpi4py", _fake_mpi(size=2))
    with pytest.raises(RuntimeError, match="single MPI rank"):
        FEniCSAdapter().execute({})


def test_dolfinx_non_finite_solution(monkeypatch):
    _install_dolfinx(monkeypatch, solution=[0.0, np.nan, 1.0])
    with pytest.raises(RuntimeError, match="non-finite FEM solution"):
        FEniCSAdapter().execute({})


def test_legacy_poisson_all_dimensions(monkeypatch):
    _install_legacy(monkeypatch)
    tool = FEniCSAdapter()
    for dim in (1, 2, 3):
        result = tool.execute({"dimension": dim, "cells": 4})
        assert result["status"] == "PASS"
        assert result["backend"] == "fenics"
        assert result["dimension"] == dim
        assert result["dofs"] == 4
        assert result["solution"]["l2"] == pytest.approx(2.0)


def test_legacy_nonlinear_and_error(monkeypatch):
    _install_legacy(monkeypatch, nonlinear_solution=[2.0, 3.0])
    result = FEniCSAdapter().execute({"problem": "nonlinear_poisson", "dimension": 1, "cells": 4, "nonlinear_exponent": 2.0})
    assert result["backend"] == "fenics"
    assert result["nonlinear_exponent"] == 2.0
    assert result["solution"]["min"] == 2.0
    assert result["solution"]["max"] == 3.0

    _install_legacy(monkeypatch, solution=[0.0, np.inf])
    with pytest.raises(RuntimeError, match="non-finite FEM solution"):
        FEniCSAdapter().execute({})
