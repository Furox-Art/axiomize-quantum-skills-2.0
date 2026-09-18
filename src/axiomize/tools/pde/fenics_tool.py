"""Optional real FEniCS/DOLFINx finite-element executor.

The adapter intentionally exposes a small structured problem contract rather
than evaluating arbitrary UFL/Python text. It currently solves scalar Poisson
problems on unit intervals/squares with P1 Lagrange elements and constant
Dirichlet boundary conditions. The native Axiomize PDE engine remains available
when FEniCS is not installed.
"""
from __future__ import annotations

import importlib
import math
from typing import Any, ClassVar

import numpy as np

from axiomize.tools.base import ScientificTool, ToolMetadata

_MAX_CELLS_1D = 100_000
_MAX_CELLS_2D = 512
_MAX_CELLS_3D = 64


def _finite(value: Any, name: str) -> float:
    try: out=float(value)
    except (TypeError,ValueError,OverflowError) as exc: raise ValueError(f"fenics: {name} must be numeric") from exc
    if not math.isfinite(out): raise ValueError(f"fenics: {name} must be finite")
    return out


class FEniCSAdapter(ScientificTool):
    name: ClassVar[str] = "fenics"
    capabilities: ClassVar[list[str]] = ["fem", "pde_weak_form", "poisson", "nonlinear_fem", "neumann_bc", "mesh_3d"]

    @classmethod
    def _probe_backend(cls) -> tuple[str,str]:
        try:
            module=importlib.import_module("dolfinx")
            importlib.import_module("ufl"); importlib.import_module("petsc4py"); importlib.import_module("mpi4py")
            return "dolfinx",str(getattr(module,"__version__","unknown"))
        except Exception as first:
            try:
                module=importlib.import_module("fenics")
                return "fenics",str(getattr(module,"__version__","unknown"))
            except Exception as second:
                raise RuntimeError(f"neither DOLFINx nor legacy FEniCS is runnable: {first}; {second}") from second

    @classmethod
    def _probe_version(cls) -> str:
        backend,version=cls._probe_backend(); return f"{backend}-{version}"

    @classmethod
    def availability(cls) -> ToolMetadata:
        try:
            backend,version=cls._probe_backend()
        except Exception as exc:
            return ToolMetadata(name=cls.name,capabilities=list(cls.capabilities),available=False,reason=str(exc))
        return ToolMetadata(name=cls.name,capabilities=list(cls.capabilities),version=f"{backend}-{version}",available=True,
                            reason=f"bounded structured FEM executor (Poisson/nonlinear, 1D-3D, Dirichlet/Neumann) via {backend}")

    def validate_input(self,payload:dict[str,Any])->None:
        if not isinstance(payload,dict): raise ValueError("fenics: payload must be an object")
        problem=str(payload.get("problem","poisson")).lower()
        if problem not in ("poisson","nonlinear_poisson"): raise ValueError("fenics: supported problem types are 'poisson' and 'nonlinear_poisson'")
        dimension=payload.get("dimension",1)
        if isinstance(dimension,bool) or not isinstance(dimension,(int,float)) or not float(dimension).is_integer() or int(dimension) not in {1,2,3}:
            raise ValueError("fenics: dimension must be 1, 2, or 3")
        cells=payload.get("cells",32)
        if isinstance(cells,bool) or not isinstance(cells,(int,float)) or not float(cells).is_integer(): raise ValueError("fenics: cells must be an integer")
        cells=int(cells); dim=int(dimension); maximum=_MAX_CELLS_1D if dim==1 else (_MAX_CELLS_2D if dim==2 else _MAX_CELLS_3D)
        if not 2<=cells<=maximum: raise ValueError(f"fenics: cells must be in [2, {maximum}]")
        _finite(payload.get("source",1.0),"source"); _finite(payload.get("dirichlet",0.0),"dirichlet"); _finite(payload.get("neumann",0.0),"neumann")
        if problem=="nonlinear_poisson":
            exponent=payload.get("nonlinear_exponent",2.0)
            _finite(exponent,"nonlinear_exponent")
            if exponent<=0 or exponent>5: raise ValueError("fenics: nonlinear_exponent must be in (0, 5]")
        degree=payload.get("degree",1)
        if degree!=1: raise ValueError("fenics: current bounded executor supports degree=1 only")

    def execute(self,payload:dict[str,Any])->dict[str,Any]:
        self.validate_input(payload)
        meta=self.availability()
        if not meta.available: raise RuntimeError(f"TOOL_UNAVAILABLE: {meta.reason}")
        backend,_=self._probe_backend()
        result=self._solve_dolfinx(payload) if backend=="dolfinx" else self._solve_legacy(payload)
        self.validate_output(result); return result

    @staticmethod
    def _solve_dolfinx(payload:dict[str,Any])->dict[str,Any]:
        from mpi4py import MPI
        from petsc4py import PETSc
        from dolfinx import fem,mesh
        from dolfinx.fem.petsc import LinearProblem,NonlinearProblem
        from dolfinx.nls.petsc import NewtonSolver
        import ufl
        if MPI.COMM_WORLD.size!=1: raise RuntimeError("fenics: bounded executor currently requires a single MPI rank")
        problem=str(payload.get("problem","poisson")).lower()
        dim=int(payload.get("dimension",1)); cells=int(payload.get("cells",32))
        source=_finite(payload.get("source",1.0),"source"); boundary=_finite(payload.get("dirichlet",0.0),"dirichlet"); neumann=_finite(payload.get("neumann",0.0),"neumann")
        if dim==1: domain=mesh.create_unit_interval(MPI.COMM_WORLD,cells)
        elif dim==2: domain=mesh.create_unit_square(MPI.COMM_WORLD,cells,cells)
        else: domain=mesh.create_unit_cube(MPI.COMM_WORLD,cells,cells,cells)
        try: V=fem.functionspace(domain,("Lagrange",1))
        except AttributeError: V=fem.FunctionSpace(domain,("Lagrange",1))
        fdim=domain.topology.dim-1
        facets=mesh.locate_entities_boundary(domain,fdim,lambda x: np.full(x.shape[1],True,dtype=bool))
        dofs=fem.locate_dofs_topological(V,fdim,facets)
        g=fem.Function(V); g.x.array[:]=PETSc.ScalarType(boundary)
        bc=fem.dirichletbc(g,dofs)
        forcing=fem.Constant(domain,PETSc.ScalarType(source))
        neumann_c=PETSc.ScalarType(neumann)
        ds=ufl.Measure("ds",domain=domain)
        v=ufl.TestFunction(V)
        if problem=="poisson":
            u=ufl.TrialFunction(V)
            a_form=ufl.inner(ufl.grad(u),ufl.grad(v))*ufl.dx
            L=forcing*v*ufl.dx + neumann_c*v*ds
            p=LinearProblem(a_form,L,bcs=[bc],petsc_options={"ksp_type":"preonly","pc_type":"lu"})
            uh=p.solve()
            values=np.asarray(uh.x.array,dtype=float)
        else:
            exponent=_finite(payload.get("nonlinear_exponent",2.0),"nonlinear_exponent")
            u=fem.Function(V); F=ufl.inner(u**exponent*ufl.grad(u),ufl.grad(v))*ufl.dx-forcing*v*ufl.dx-neumann_c*v*ds
            problem_nlp=NonlinearProblem(F,u,bcs=[bc])
            solver=NewtonSolver(MPI.COMM_WORLD,problem_nlp); solver.convergence_criterion="incremental"; solver.atol=1e-12; solver.rtol=1e-12
            solver.solve(u)
            uh=u; values=np.asarray(uh.x.array,dtype=float)
        l2=math.sqrt(max(0.0,float(fem.assemble_scalar(fem.form(ufl.inner(uh,uh)*ufl.dx)))))
        if not np.all(np.isfinite(values)) or not math.isfinite(l2): raise RuntimeError("fenics: non-finite FEM solution")
        return {"status":"PASS","backend":"dolfinx","problem":problem,"dimension":dim,"cells":cells,"degree":1,"nonlinear_exponent":_finite(payload.get("nonlinear_exponent",1.0),"nonlinear_exponent") if problem=="nonlinear_poisson" else 1,
                "dofs":int(values.size),"solution":{"min":float(np.min(values)),"max":float(np.max(values)),"l2":l2,"finite":True}}

    @staticmethod
    def _solve_legacy(payload:dict[str,Any])->dict[str,Any]:
        import fenics as fe  # type: ignore[import-untyped]
        problem=str(payload.get("problem","poisson")).lower()
        dim=int(payload.get("dimension",1)); cells=int(payload.get("cells",32))
        source=_finite(payload.get("source",1.0),"source"); boundary=_finite(payload.get("dirichlet",0.0),"dirichlet"); neumann=_finite(payload.get("neumann",0.0),"neumann")
        domain=fe.UnitIntervalMesh(cells) if dim==1 else (fe.UnitSquareMesh(cells,cells) if dim==2 else fe.UnitCubeMesh(cells,cells,cells))
        V=fe.FunctionSpace(domain,"P",1); v=fe.TestFunction(V); ds=fe.Measure("ds")
        bc=fe.DirichletBC(V,fe.Constant(boundary),"on_boundary")
        if problem=="poisson":
            u=fe.TrialFunction(V)
            a=fe.dot(fe.grad(u),fe.grad(v))*fe.dx; L=fe.Constant(source)*v*fe.dx+fe.Constant(neumann)*v*ds
            uh=fe.Function(V); fe.solve(a==L,uh,bc)
        else:
            exponent=_finite(payload.get("nonlinear_exponent",2.0),"nonlinear_exponent")
            u=fe.Function(V); F=fe.dot(u**exponent*fe.grad(u),fe.grad(v))*fe.dx-fe.Constant(source)*v*fe.dx-fe.Constant(neumann)*v*ds
            problem_nlp=fe.NonlinearVariationalProblem(F,u,bc)
            solver=fe.NonlinearVariationalSolver(problem_nlp); solver.solve(u)
            uh=u
        values=np.asarray(uh.vector().get_local(),dtype=float); l2=float(fe.norm(uh,"L2"))
        if not np.all(np.isfinite(values)) or not math.isfinite(l2): raise RuntimeError("fenics: non-finite FEM solution")
        return {"status":"PASS","backend":"fenics","problem":problem,"dimension":dim,"cells":cells,"degree":1,
                "nonlinear_exponent":_finite(payload.get("nonlinear_exponent",1.0),"nonlinear_exponent") if problem=="nonlinear_poisson" else 1,
                "dofs":int(V.dim()),"solution":{"min":float(np.min(values)),"max":float(np.max(values)),"l2":l2,"finite":True}}
