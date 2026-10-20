"""Coverage hardening round 2a: advanced engines (Bayes, agents, events, hybrid)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import scipy.integrate

from axiomize import advanced_family_engine as adv
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec

_SOURCE = Path(__file__).resolve().parents[1] / "src" / "axiomize" / "advanced_family_engine.py"
_FRESH = None


def fresh():
    """Load the pristine module: the package runtime swaps ``_infer_bayesian``."""
    global _FRESH
    if _FRESH is None:
        spec = importlib.util.spec_from_file_location("advanced_family_engine_r2a_cov", _SOURCE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _FRESH = module
    return _FRESH


def _model(family, *, variables=None, parameters=None, equations=None, metadata=None):
    return ModelIR(
        name=f"{family.value}-model",
        domain="test",
        family=family,
        variables=list(variables or []),
        parameters=list(parameters or []),
        equations=list(equations or []),
        metadata=dict(metadata or {}),
    )


def test_advanced_bayesian_array_predictor():
    model = _model(
        ModelFamily.BAYESIAN,
        variables=[VariableSpec(name="s", initial=1.0)],
        parameters=[ParameterSpec(name="p", value=1.0)],
        metadata={
            "bayesian": {
                "observations": [1.0, 2.0, 1.5, 2.5],
                "data": {"x": [1.0, 2.0, 3.0, 4.0]},
                "mean_expression": "p*x",
                "draws": 60,
                "burn": 0,
                "return_samples": True,
            }
        },
    )
    out = fresh()._infer_bayesian(
        model, t_span=(0.0, 1.0), points=10, parameter_overrides=None, seed=4
    )
    assert out["status"] == "PASS"
    assert out["diagnostics"]["draws"] == 60
    assert np.isfinite(out["posterior"]["p"]["mean"])
    assert len(out["samples"]["p"]) == 60


def _agent(metadata, *, variables=None, equations=None) -> ModelIR:
    return _model(
        ModelFamily.AGENT_BASED,
        variables=variables if variables is not None else [VariableSpec(name="x", initial=1.0)],
        parameters=[ParameterSpec(name="k", value=0.1)],
        equations=equations if equations is not None else [
            EquationSpec(target="x", expression="x + k", kind="update")
        ],
        metadata=metadata,
    )


def _run_agent(model, t_span=(0.0, 1.0), points=4, seed=0):
    return adv._simulate_agent_based(
        model, t_span=t_span, points=points, parameter_overrides=None, seed=seed
    )


def test_agent_configuration_and_initial_validation():
    with pytest.raises(ValueError, match="metadata.agents must be an object"):
        _run_agent(_agent({"agents": "bad"}))
    with pytest.raises(ValueError, match="requires state variables"):
        _run_agent(_agent({"agents": {"count": 2}}, variables=[], equations=[]))
    with pytest.raises(ValueError, match="missing update/derivative equations"):
        _run_agent(_agent({"agents": {"count": 2}}, equations=[]))
    with pytest.raises(ValueError, match="needs an initial value"):
        _run_agent(
            _agent(
                {"agents": {"count": 2}},
                variables=[VariableSpec(name="x")],
            )
        )
    with pytest.raises(ValueError, match="t_span must be increasing"):
        _run_agent(_agent({"agents": {"count": 2}}), t_span=(1.0, 0.5))


def test_agent_bounds_clipping_and_update_shape_guard(monkeypatch):
    bounded = _agent(
        {"agents": {"count": 2}},
        variables=[VariableSpec(name="x", initial=4.5, bounds=(None, 5.0))],
    )
    out = _run_agent(bounded, points=4)
    assert out["status"] == "PASS"
    final = np.asarray(out["states"]["x"], dtype=float)[-1]
    assert np.all(final <= 5.0)
    assert np.all(final >= 4.5)
    assert out["diagnostics"]["agents"] == 2

    monkeypatch.setattr(
        adv,
        "_compile_expression",
        lambda expression, names: (lambda *args: np.asarray([1.0, 2.0])),
    )
    with pytest.raises(ValueError, match="one value per agent"):
        _run_agent(_agent({"agents": {"count": 3}}))


def _event(metadata, *, variables=None, equations=None) -> ModelIR:
    return _model(
        ModelFamily.DISCRETE_EVENT,
        variables=variables if variables is not None else [VariableSpec(name="x", initial=0.0)],
        parameters=[ParameterSpec(name="k", value=1.0)],
        equations=list(equations or []),
        metadata=metadata,
    )


def test_discrete_event_configuration_and_finite_state():
    with pytest.raises(ValueError, match="metadata.discrete_event must be an object"):
        adv._simulate_discrete_event(
            _event({"discrete_event": "bad"}),
            t_span=(0.0, 1.0), points=4, parameter_overrides=None, seed=0,
        )
    with pytest.raises(ValueError, match="finite initial values"):
        adv._simulate_discrete_event(
            _event(
                {"discrete_event": {"events": [{"rate": "k", "delta": {"x": 1.0}}]}},
                variables=[VariableSpec(name="x")],
            ),
            t_span=(0.0, 1.0), points=4, parameter_overrides=None, seed=0,
        )

    out = adv._simulate_discrete_event(
        _event({"discrete_event": {"events": [{"rate": "k", "delta": {"x": 1.0}}]}}),
        t_span=(0.0, 1.0), points=4, parameter_overrides=None, seed=3,
    )
    assert out["status"] == "PASS"
    assert out["diagnostics"]["total_events"] >= 1
    assert float(out["states"]["x"][-1]) >= 1.0


def _hybrid(metadata, *, variables=None, equations=None) -> ModelIR:
    return _model(
        ModelFamily.HYBRID,
        variables=variables if variables is not None else [VariableSpec(name="x", initial=1.0)],
        parameters=[ParameterSpec(name="k", value=1.0)],
        equations=equations if equations is not None else [
            EquationSpec(target="x", expression="-k*x", kind="derivative")
        ],
        metadata=metadata,
    )


def _run_hybrid(model, points=4):
    return adv._simulate_hybrid(
        model, t_span=(0.0, 1.0), points=points, parameter_overrides=None, seed=0
    )


def test_hybrid_configuration_validation():
    with pytest.raises(ValueError, match="missing derivative equations"):
        _run_hybrid(_hybrid({"hybrid": {}}, equations=[]))
    with pytest.raises(ValueError, match="metadata.hybrid must be an object"):
        _run_hybrid(_hybrid({"hybrid": "bad"}))
    with pytest.raises(ValueError, match="hybrid.events must be an array"):
        _run_hybrid(_hybrid({"hybrid": {"events": "bad"}}))
    with pytest.raises(ValueError, match="requires expression"):
        _run_hybrid(_hybrid({"hybrid": {"events": [{}]}}))
    with pytest.raises(ValueError, match="reset must be an object"):
        _run_hybrid(_hybrid({"hybrid": {"events": [
            {"expression": "t - 0.5", "reset": "bad"}
        ]}}))
    with pytest.raises(ValueError, match="reset references unknown states"):
        _run_hybrid(_hybrid({"hybrid": {"events": [
            {"expression": "t - 0.5", "reset": {"z": "1.0"}}
        ]}}))
    with pytest.raises(ValueError, match="finite initial values"):
        _run_hybrid(
            _hybrid(
                {"hybrid": {"events": []}},
                variables=[VariableSpec(name="x")],
            )
        )


def test_hybrid_continuous_solve_failure(monkeypatch):
    def fake_solve_ivp(rhs, span, y0, method=None, rtol=None, atol=None, events=None):
        return SimpleNamespace(success=False, message="failed", y=np.zeros((1, 1)))

    monkeypatch.setattr(scipy.integrate, "solve_ivp", fake_solve_ivp)
    out = _run_hybrid(_hybrid({"hybrid": {"events": []}}))
    assert out["status"] == "FAIL"
    assert out["stage"] == "hybrid_continuous_solve"
    assert out["message"] == "failed"


def test_hybrid_events_without_hits_and_multiple_candidates():
    none_hit = _run_hybrid(_hybrid({"hybrid": {"events": []}}))
    assert none_hit["status"] == "PASS"
    assert none_hit["events"] == []
    assert none_hit["diagnostics"]["event_count"] == 0

    out = _run_hybrid(
        _hybrid(
            {
                "hybrid": {
                    "events": [
                        {"name": "never", "expression": "x - 100.0"},
                        {"name": "hit", "expression": "t - 0.5", "reset": {"x": "x + 1.0"}},
                    ]
                }
            }
        )
    )
    assert out["status"] == "PASS"
    assert [event["name"] for event in out["events"]] == ["hit"]
    assert out["events"][0]["time"] == pytest.approx(0.5, abs=1e-6)
    assert out["events"][0]["state_after"]["x"] > 0.0


def test_hybrid_event_chatter_is_bounded():
    out = _run_hybrid(
        _hybrid(
            {
                "hybrid": {
                    "events": [{"name": "chatter", "expression": "x - x"}],
                    "max_events_per_interval": 2,
                }
            }
        )
    )
    assert out["status"] == "FAIL"
    assert out["stage"] == "hybrid_event_chatter"


def test_hybrid_picks_earliest_of_several_candidate_events(monkeypatch):
    calls = {"count": 0}

    def multi_event_solve(rhs, span, y0, method=None, rtol=None, atol=None, events=None):
        calls["count"] += 1
        if calls["count"] == 1:
            return SimpleNamespace(
                success=True,
                message="ok",
                y=np.asarray([[1.0, 0.9]]),
                t_events=[np.asarray([0.4]), np.asarray([0.6])],
                y_events=[np.asarray([[0.9]]), np.asarray([[0.8]])],
            )
        return SimpleNamespace(
            success=True,
            message="ok",
            y=np.asarray([[0.9, 0.9]]),
            t_events=[np.asarray([]), np.asarray([])],
            y_events=[np.asarray([[]]), np.asarray([[]])],
        )

    monkeypatch.setattr(scipy.integrate, "solve_ivp", multi_event_solve)
    out = _run_hybrid(
        _hybrid(
            {
                "hybrid": {
                    "events": [
                        {"name": "first", "expression": "t - 0.4", "reset": {"x": "x"}},
                        {"name": "second", "expression": "t - 0.6"},
                    ]
                }
            }
        ),
        points=3,
    )
    assert out["status"] == "PASS"
    assert out["diagnostics"]["event_count"] == 1
    assert [event["name"] for event in out["events"]] == ["first"]
    assert out["events"][0]["time"] == pytest.approx(0.4)
    assert out["events"][0]["state_after"]["x"] == pytest.approx(0.9)
    assert calls["count"] == 3


def test_multiphysics_config_must_be_mapping():
    model = _model(
        ModelFamily.MULTIPHYSICS,
        variables=[VariableSpec(name="s", initial=1.0)],
        equations=[],
        metadata={"multiphysics": "bad"},
    )
    with pytest.raises(ValueError, match="metadata.multiphysics must be an object"):
        adv._simulate_multiphysics(
            model,
            t_span=(0.0, 1.0),
            points=4,
            parameter_overrides=None,
            seed=0,
            simulate_fn=lambda *args, **kwargs: {"status": "PASS"},
        )
