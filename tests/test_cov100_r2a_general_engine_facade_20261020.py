"""Coverage hardening round 2a: general_engine facade (preflight + refinement)."""

from __future__ import annotations

import math

import pytest

import axiomize.general_engine as ge
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec


def _model(
    family: ModelFamily,
    *,
    variables=None,
    parameters=None,
    equations=None,
    metadata=None,
    solver=None,
    name="facade",
) -> ModelIR:
    kwargs = {}
    if solver is not None:
        kwargs["solver"] = solver
    return ModelIR(
        name=name,
        domain="test",
        family=family,
        variables=list(variables or []),
        parameters=list(parameters or []),
        equations=list(equations or []),
        metadata=dict(metadata or {}),
        **kwargs,
    )


def test_validated_span_and_points_reject_bad_input():
    with pytest.raises(ValueError, match="exactly"):
        ge._validated_span((0.0,))
    with pytest.raises(ValueError, match="exactly"):
        ge._validated_span("0:1")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="finite and strictly increasing"):
        ge._validated_span((1.0, 1.0))
    with pytest.raises(ValueError, match="finite and strictly increasing"):
        ge._validated_span((0.0, math.inf))
    assert ge._validated_span([0, 2]) == (0.0, 2.0)

    # No model: the result-cell guard is skipped entirely.
    assert ge._validated_points(5) == 5
    model = _model(ModelFamily.ODE, variables=[VariableSpec(name="x", initial=1.0)])
    assert ge._validated_points(5, model) == 5


def test_preflight_network_edge_discovery_and_limits(monkeypatch):
    state = [VariableSpec(name="x", initial=1.0)]
    derivative = [EquationSpec(target="x", expression="-x", kind="derivative")]

    # nodes omitted -> discovered from dict edges, long tuple edges and junk entries.
    model = _model(
        ModelFamily.NETWORK,
        variables=state,
        equations=derivative,
        metadata={
            "network": {
                "nodes": None,
                "edges": [
                    {"source": "a", "target": "b"},
                    ("b", "c"),
                    ("c",),
                    5,
                ],
            }
        },
    )
    ge._advanced_preflight(model, points=2)

    # nodes omitted, no usable edges -> fall back to n_nodes.
    model = _model(
        ModelFamily.NETWORK,
        variables=state,
        equations=derivative,
        metadata={"network": {"nodes": None, "edges": [], "n_nodes": 5}},
    )
    ge._advanced_preflight(model, points=2)

    # nodes supplied as a list.
    model = _model(
        ModelFamily.NETWORK,
        variables=state,
        equations=derivative,
        metadata={"network": {"nodes": ["a", "b"], "edges": []}},
    )
    ge._advanced_preflight(model, points=2)

    # network config is not an object -> preflight skips the family checks.
    ge._advanced_preflight(
        _model(ModelFamily.NETWORK, variables=state, equations=derivative,
               metadata={"network": "not-a-mapping"}),
        points=2,
    )

    with pytest.raises(ValueError, match="network.nodes must be an array"):
        ge._advanced_preflight(
            _model(ModelFamily.NETWORK, variables=state, equations=derivative,
                   metadata={"network": {"nodes": 5}}),
            points=2,
        )
    with pytest.raises(ValueError, match="dense network executor supports"):
        ge._advanced_preflight(
            _model(ModelFamily.NETWORK, variables=state, equations=derivative,
                   metadata={"network": {"nodes": []}}),
            points=2,
        )
    monkeypatch.setattr(ge, "MAX_DENSE_NETWORK_NODES", 1)
    with pytest.raises(ValueError, match="dense network executor supports"):
        ge._advanced_preflight(
            _model(ModelFamily.NETWORK, variables=state, equations=derivative,
                   metadata={"network": {"nodes": ["a", "b"]}}),
            points=2,
        )
    monkeypatch.setattr(ge, "MAX_ARRAY_ITEMS", 2)
    with pytest.raises(ValueError, match="network.edges exceeds hard limit"):
        ge._advanced_preflight(
            _model(ModelFamily.NETWORK, variables=state, equations=derivative,
                   metadata={"network": {"nodes": None, "edges": [("a", "b")] * 3}}),
            points=2,
        )


def test_preflight_agent_control_and_bayesian_branches(monkeypatch):
    state = [VariableSpec(name="x", initial=1.0)]
    derivative = [EquationSpec(target="x", expression="-x", kind="derivative")]

    ge._advanced_preflight(
        _model(ModelFamily.AGENT_BASED, variables=state, equations=derivative,
               metadata={"agents": {"count": 3}}),
        points=4,
    )
    # Agent config not a mapping: skip.
    ge._advanced_preflight(
        _model(ModelFamily.AGENT_BASED, variables=state, equations=derivative,
               metadata={"agent_based": "bad"}),
        points=4,
    )

    control = _model(ModelFamily.CONTROL, variables=state, equations=derivative,
                     metadata={"control": {"A": [[1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]]}})
    ge._advanced_preflight(control, points=2)
    nested = _model(ModelFamily.CONTROL, variables=state, equations=derivative,
                    metadata={"control": {"state_space": {"A": [[1.0], [0.0]]}}})
    ge._advanced_preflight(nested, points=2)
    # state_space value is not a mapping -> skip matrix checks.
    ge._advanced_preflight(
        _model(ModelFamily.CONTROL, variables=state, equations=derivative,
               metadata={"control": {"state_space": 5}}),
        points=2,
    )
    ge._advanced_preflight(
        _model(ModelFamily.CONTROL, variables=state, equations=derivative,
               metadata={"control": "bad"}),
        points=2,
    )
    monkeypatch.setattr(ge, "MAX_CONTROL_DIMENSION", 1)
    with pytest.raises(ValueError, match="control state dimension exceeds"):
        ge._advanced_preflight(nested, points=2)

    bayes = _model(
        ModelFamily.BAYESIAN,
        variables=state, equations=derivative,
        parameters=[ParameterSpec(name="p", value=1.0)],
        metadata={"bayesian": {"outcome": "y", "data": {"y": [1.0, 2.0]}, "draws": 50, "burn": 0}},
    )
    ge._advanced_preflight(bayes, points=100)

    # Observations supplied as a scalar (non-list) and samples not requested.
    ge._advanced_preflight(
        _model(ModelFamily.BAYESIAN, variables=state, equations=derivative,
               metadata={"bayesian": {"observations": 5.0, "draws": 50, "burn": 0}}),
        points=100,
    )
    # Bayesian config not a mapping: skip.
    ge._advanced_preflight(
        _model(ModelFamily.BAYESIAN, variables=state, equations=derivative,
               metadata={"bayesian": "bad"}),
        points=100,
    )

    monkeypatch.setattr(ge, "MAX_ARRAY_ITEMS", 2)
    with pytest.raises(ValueError, match="bayesian observations exceed hard limit"):
        ge._advanced_preflight(
            _model(ModelFamily.BAYESIAN, variables=state, equations=derivative,
                   metadata={"bayesian": {"observations": [1.0, 2.0, 3.0], "draws": 50, "burn": 0}}),
            points=100,
        )
    monkeypatch.undo()

    with pytest.raises(ValueError, match="likelihood-work-unit limit"):
        ge._advanced_preflight(
            _model(ModelFamily.BAYESIAN, variables=state, equations=derivative,
                   metadata={
                       "bayesian": {
                           "observations": [1.0] * 300,
                           "draws": 100000,
                           "burn": 100000,
                       }
                   }),
            points=100,
        )

    # outcome is named but the data payload is unusable -> no observation vector.
    ge._advanced_preflight(
        _model(ModelFamily.BAYESIAN, variables=state, equations=derivative,
               metadata={"bayesian": {"outcome": "y", "data": 5, "draws": 50, "burn": 0}}),
        points=100,
    )

    requested = _model(
        ModelFamily.BAYESIAN,
        variables=state, equations=derivative,
        parameters=[ParameterSpec(name="p", value=1.0)],
        metadata={"bayesian": {"observations": [1.0, 2.0], "draws": 50, "burn": 0,
                               "return_samples": True}},
    )
    ge._advanced_preflight(requested, points=100)


def test_preflight_discrete_event_hybrid_optimization_multiphysics(monkeypatch):
    state = [VariableSpec(name="x", initial=1.0)]
    derivative = [EquationSpec(target="x", expression="-x", kind="derivative")]

    ge._advanced_preflight(
        _model(ModelFamily.DISCRETE_EVENT, variables=state, equations=derivative,
               metadata={"discrete_event": [{"rate": "1.0", "delta": {"x": 1.0}}]}),
        points=4,
    )
    ge._advanced_preflight(
        _model(ModelFamily.DISCRETE_EVENT, variables=state, equations=derivative,
               metadata={"events": {"events": [], "max_events": 10}}),
        points=4,
    )
    with pytest.raises(ValueError, match="discrete_event.max_events"):
        ge._advanced_preflight(
            _model(ModelFamily.DISCRETE_EVENT, variables=state, equations=derivative,
                   metadata={"discrete_event": "bad"}),
            points=4,
        )
    with pytest.raises(ValueError, match="discrete-event definitions exceed"):
        ge._advanced_preflight(
            _model(ModelFamily.DISCRETE_EVENT, variables=state, equations=derivative,
                   metadata={"discrete_event": {"events": [{}] * 10001}}),
            points=4,
        )
    with pytest.raises(ValueError, match="discrete_event.max_events"):
        ge._advanced_preflight(
            _model(ModelFamily.DISCRETE_EVENT, variables=state, equations=derivative,
                   metadata={"discrete_event": {"events": [], "max_events": 0}}),
            points=4,
        )

    ge._advanced_preflight(
        _model(ModelFamily.HYBRID, variables=state, equations=derivative,
               metadata={"hybrid": {"events": [], "max_events_per_interval": 10}}),
        points=4,
    )
    ge._advanced_preflight(
        _model(ModelFamily.HYBRID, variables=state, equations=derivative,
               metadata={"hybrid": "bad"}),
        points=4,
    )
    with pytest.raises(ValueError, match="hybrid event definitions exceed"):
        ge._advanced_preflight(
            _model(ModelFamily.HYBRID, variables=state, equations=derivative,
                   metadata={"hybrid": {"events": [{}] * 1001}}),
            points=4,
        )

    ge._advanced_preflight(
        _model(ModelFamily.OPTIMIZATION, variables=state, equations=derivative,
               metadata={"optimization": {"maxiter": 10, "constraints": []}}),
        points=4,
    )
    ge._advanced_preflight(
        _model(ModelFamily.OPTIMIZATION, variables=state, equations=derivative,
               metadata={"optimization": "bad"}),
        points=4,
    )
    with pytest.raises(ValueError, match="optimization constraints exceed"):
        ge._advanced_preflight(
            _model(ModelFamily.OPTIMIZATION, variables=state, equations=derivative,
                   metadata={"optimization": {"constraints": [{}] * 10001}}),
            points=4,
        )

    ge._advanced_preflight(
        _model(ModelFamily.MULTIPHYSICS, variables=state, equations=derivative,
               metadata={"multiphysics": {"components": {"a": {}}, "max_iterations": 3}}),
        points=4,
    )
    ge._advanced_preflight(
        _model(ModelFamily.MULTIPHYSICS, variables=state, equations=derivative,
               metadata={"multiphysics": "bad"}),
        points=4,
    )
    monkeypatch.setattr(ge, "MAX_MODEL_COMPONENTS", 1)
    with pytest.raises(ValueError, match="multiphysics components exceed"):
        ge._advanced_preflight(
            _model(ModelFamily.MULTIPHYSICS, variables=state, equations=derivative,
                   metadata={"multiphysics": {"components": {"a": {}, "b": {}}}}),
            points=4,
        )


def test_select_solver_and_estimate_multiphysics():
    from axiomize.model_ir import SolverSpec

    auto = _model(ModelFamily.MULTIPHYSICS, variables=[VariableSpec(name="x", initial=1.0)],
                  equations=[EquationSpec(target="x", expression="-x", kind="derivative")])
    selected = ge.select_solver(auto)
    assert selected["method"] == "partitioned_fixed_point_cosimulation"
    assert selected["fallbacks"] == []

    explicit = _model(
        ModelFamily.MULTIPHYSICS,
        variables=[VariableSpec(name="x", initial=1.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
        solver=SolverSpec(backend="custom", method="solver", fallbacks=("alt",)),
    )
    selected = ge.select_solver(explicit)
    assert selected["backend"] == "custom"
    assert selected["fallbacks"] == ["alt"]

    estimate = ge.estimate_compute(auto, action="solve", points=10)
    assert estimate["requires_user_approval"] is True
    assert "multi-physics" in estimate["reason"]

    bayes = _model(ModelFamily.BAYESIAN, variables=[VariableSpec(name="x", initial=1.0)],
                   equations=[EquationSpec(target="x", expression="-x", kind="derivative")])
    estimate = ge.estimate_compute(bayes, action="simulate", points=10)
    assert estimate["requires_user_approval"] is True
    assert "Bayesian" in estimate["reason"]

    via_signal = ge.recommend_model_families(signals=["multiphysics", "other"])
    assert via_signal[0]["family"] == "multiphysics"
    assert [row["rank"] for row in via_signal] == [1, 2, 3]
    via_text = ge.recommend_model_families(idea="a multi-scale coupled physics study")
    assert via_text[0]["family"] == "multiphysics"


def test_simulate_once_structure_failure_and_route_fallback(monkeypatch):
    broken = _model(
        ModelFamily.ODE,
        variables=[VariableSpec(name="x", initial=1.0), VariableSpec(name="x", initial=2.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    out = ge._simulate_once(broken)
    assert out["status"] == "FAIL"
    assert out["stage"] == "structure"
    assert any(check["status"] == "FAIL" for check in out["checks"])

    monkeypatch.setattr(ge, "_CORE_NATIVE", frozenset())
    monkeypatch.setattr(ge, "_ADVANCED_NATIVE", frozenset())
    routable = _model(
        ModelFamily.ODE,
        variables=[VariableSpec(name="x", initial=1.0)],
        equations=[EquationSpec(target="x", expression="-x", kind="derivative")],
    )
    out = ge._simulate_once(routable)
    assert out["status"] == "TOOL_ROUTE_REQUIRED"
    assert out["family"] == "ode"
    assert out["solver"]["backend"] == "scipy"


def test_numerical_refinement_validation_and_study():
    # The package runtime replaces the facade attribute with the v2 wrapper; the
    # original facade body is still shipped, so load an isolated copy and check
    # it directly while restoring the shared core patch targets afterwards.
    import importlib.util

    import axiomize.general_engine_core as core_module

    patch_targets = (
        "_sympy_expression",
        "select_solver",
        "estimate_compute",
        "recommend_model_families",
        "export_model",
        "simulate_model",
    )
    saved = {name: getattr(core_module, name) for name in patch_targets}
    spec = importlib.util.spec_from_file_location("axiomize_cov_r2a_general_engine", ge.__file__)
    assert spec is not None and spec.loader is not None
    isolated = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(isolated)
        model = _model(
            ModelFamily.ODE,
            variables=[VariableSpec(name="x", initial=1.0)],
            parameters=[ParameterSpec(name="k", value=1.0)],
            equations=[EquationSpec(target="x", expression="-k*x", kind="derivative")],
        )
        with pytest.raises(ValueError, match="tolerance must be finite and positive"):
            isolated.numerical_refinement(model, tolerance=0.0)
        with pytest.raises(ValueError, match="tolerance must be finite and positive"):
            isolated.numerical_refinement(model, tolerance=math.nan)
        out = isolated.numerical_refinement(model, t_span=(0.0, 1.0), points=5, tolerance=1e-3)
        assert out["status"] == "APPROVAL_REQUIRED"
        assert out["cost"]["requires_user_approval"] is True
    finally:
        for name, value in saved.items():
            setattr(core_module, name, value)


def _refinable_pde(tolerance: float | None = None) -> ModelIR:
    metadata = {
        "pde": {
            "grid_points": 5,
            "space_span": [0.0, 1.0],
            "diffusion": {"u": 0.1},
            "initial_profiles": {"u": "0.5+0.5*sin(3.141592653589793*x)"},
        }
    }
    if tolerance is not None:
        metadata["numerical_verification"] = {"tolerance": tolerance}
    return _model(
        ModelFamily.PDE,
        variables=[VariableSpec(name="u")],
        equations=[EquationSpec(target="u", expression="-u", kind="derivative")],
        metadata=metadata,
    )


def test_simulate_model_numerical_verification_paths(monkeypatch):
    model = _refinable_pde()
    out = ge.simulate_model(model, t_span=(0.0, 0.1), points=5)
    assert out["status"] == "PASS"
    assert out["numerical_verification"]["status"] == "APPROVAL_REQUIRED"
    assert out["diagnostics"]["discretization_error"] == "pending explicit approval for numerical refinement"

    strict = _refinable_pde(tolerance=1e-12)
    out = ge.simulate_model(strict, t_span=(0.0, 0.2), points=5, approve_heavy=True)
    assert out["status"] == "FAIL"
    assert out["stage"] == "numerical_verification"
    assert out["numerical_verification"]["status"] == "FAIL"
    assert out["diagnostics"]["estimated_numerical_error"] == out["numerical_verification"]["estimated_numerical_error"]

    # Non-mapping diagnostics and a verification payload without an error estimate.
    monkeypatch.setattr(
        ge, "_simulate_once",
        lambda *args, **kwargs: {
            "status": "PASS",
            "family": "pde",
            "time": [0.0, 0.1],
            "states": {"u": [1.0, 0.9]},
            "diagnostics": ["not", "a", "mapping"],
        },
    )
    monkeypatch.setattr(ge, "numerical_refinement", lambda *args, **kwargs: {"status": "FAIL"})
    out = ge.simulate_model(_refinable_pde(), t_span=(0.0, 0.1), points=5)
    assert out["status"] == "PASS"
    assert out["diagnostics"] == ["not", "a", "mapping"]
    assert out["numerical_verification"] == {"status": "FAIL"}

    # Mapping diagnostics but a verification status that is neither an error
    # estimate nor an approval request: leave the diagnostics untouched.
    monkeypatch.setattr(
        ge, "_simulate_once",
        lambda *args, **kwargs: {
            "status": "PASS",
            "family": "pde",
            "time": [0.0, 0.1],
            "states": {"u": [1.0, 0.9]},
            "diagnostics": {},
        },
    )
    monkeypatch.setattr(ge, "numerical_refinement", lambda *args, **kwargs: {"status": "NOT_APPLICABLE"})
    out = ge.simulate_model(_refinable_pde(), t_span=(0.0, 0.1), points=5)
    assert out["status"] == "PASS"
    assert out["diagnostics"] == {}
    assert out["numerical_verification"] == {"status": "NOT_APPLICABLE"}
