"""Coverage hardening for the causal engine (DAG, estimators, guard rails)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.causal_engine import (
    _ancestors,
    _dag,
    _derive_adjustment,
    _descendants,
    _finite_vector,
    _parameter_values,
    _smd,
    estimate_causal_model,
)
from axiomize.model_ir import ModelFamily, ModelIR, ParameterSpec, VariableSpec


def _model(metadata, parameters=None):
    return ModelIR(
        name="causal",
        domain="test",
        family=ModelFamily.CAUSAL,
        variables=[VariableSpec(name="x"), VariableSpec(name="y")],
        parameters=list(parameters or []),
        equations=[],
        metadata=metadata,
    )


def _data(n=6):
    return {
        "x": [0, 1, 0, 1, 0, 1][:n],
        "y": [0, 1, 0, 1, 1, 0][:n],
    }


def _estimate(model):
    return estimate_causal_model(
        model, t_span=(0.0, 1.0), points=10, parameter_overrides=None, seed=7
    )


def test_parameter_values_validation():
    model = _model({}, parameters=[ParameterSpec(name="k", value=1.0), ParameterSpec(name="missing")])
    with pytest.raises(ValueError, match="unknown parameter overrides"):
        _parameter_values(model, {"nope": 1.0})
    with pytest.raises(ValueError, match="has no value"):
        _parameter_values(model, None)
    fixed = _model({}, parameters=[ParameterSpec(name="k", value=1.0)])
    with pytest.raises(ValueError, match="must be finite"):
        _parameter_values(fixed, {"k": math.inf})
    assert _parameter_values(fixed, {"k": 2}) == {"k": 2.0}


def test_finite_vector_validation():
    with pytest.raises(ValueError, match="missing from data"):
        _finite_vector({}, "x")
    with pytest.raises(ValueError, match="1D array with at least 3 rows"):
        _finite_vector({"x": [[1, 2, 3]]}, "x")
    with pytest.raises(ValueError, match="1D array with at least 3 rows"):
        _finite_vector({"x": [1, 2]}, "x")
    with pytest.raises(ValueError, match="length mismatch"):
        _finite_vector({"x": [1, 2, 3]}, "x", n=4)
    with pytest.raises(ValueError, match="must be finite"):
        _finite_vector({"x": [1, 2, math.nan]}, "x")
    assert _finite_vector({"x": [1, 2, 3]}, "x", n=3).tolist() == [1.0, 2.0, 3.0]


def test_dag_validation_and_traversal():
    parents, children = _dag(None)
    assert parents == {} and children == {}

    parents, children = _dag([
        {"source": "x", "target": "m"},
        ["m", "y"],
        ("z", "x"),
    ])
    assert parents["y"] == {"m"}
    assert children["z"] == {"x"}
    assert _ancestors("y", parents) == {"m", "x", "z"}
    assert _descendants("z", children) == {"x", "m", "y"}

    diamond_parents, diamond_children = _dag([("a", "b"), ("a", "c"), ("b", "d"), ("c", "d")])
    assert _ancestors("d", diamond_parents) == {"a", "b", "c"}
    assert _descendants("a", diamond_children) == {"b", "c", "d"}

    with pytest.raises(ValueError, match="must be an array"):
        _dag("x->y")
    with pytest.raises(ValueError, match="at most 10000"):
        _dag([("a", "b")] * 10001)
    with pytest.raises(ValueError, match="must contain source and target"):
        _dag([42])
    with pytest.raises(ValueError, match="distinct non-empty node names"):
        _dag([("a", "a")])
    with pytest.raises(ValueError, match="directed cycle"):
        _dag([("a", "b"), ("b", "a")])


def test_derive_adjustment():
    assert _derive_adjustment("x", "y", {}, {}, {"x", "y"}) == []
    parents, children = _dag([("z", "x"), ("z", "y"), ("x", "y")])
    assert _derive_adjustment("x", "y", parents, children, {"x", "y", "z"}) == ["z"]
    assert _derive_adjustment("x", "y", parents, children, {"x", "y"}) == []


def test_smd_requires_both_treatment_arms():
    assert _smd(np.array([1.0, 2.0]), np.array([1, 1])) == math.inf


def test_estimate_rejects_malformed_configuration():
    with pytest.raises(ValueError, match="metadata.causal must be an object"):
        _estimate(_model({"causal": []}))
    with pytest.raises(ValueError, match="causal.data must be an object"):
        _estimate(_model({"causal": {"data": []}}))
    with pytest.raises(ValueError, match="requires treatment and outcome"):
        _estimate(_model({"causal": {"data": {}}}))
    with pytest.raises(ValueError, match="adjustment set cannot include treatment"):
        _estimate(_model({"causal": {"data": _data(), "treatment": "x", "outcome": "y",
                                    "adjustment_set": ["x"]}}))


def test_estimate_non_dict_identification_falls_back_to_insufficient():
    model = _model({"causal": {"data": _data(), "treatment": "x", "outcome": "y",
                               "identification": "bogus"}})
    result = _estimate(model)
    assert result["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"


def test_estimate_rejects_post_treatment_adjustment():
    model = _model({"causal": {
        "data": _data(), "treatment": "x", "outcome": "y",
        "dag_edges": [{"source": "x", "target": "z"}],
        "adjustment_set": ["z"],
    }})
    with pytest.raises(ValueError, match="descendants of treatment"):
        _estimate(model)


def test_frontdoor_validation_errors():
    base = {"data": _data(), "treatment": "x", "outcome": "y"}
    with pytest.raises(ValueError, match="requires a 'mediator'"):
        _estimate(_model({"causal": dict(base, identification={"method": "frontdoor"})}))
    with pytest.raises(ValueError, match="mediator 'm' not found"):
        _estimate(_model({"causal": dict(
            base, identification={"method": "frontdoor", "mediator": "m"}
        )}))
    with pytest.raises(ValueError, match="mediator cannot be in the adjustment set"):
        _estimate(_model({"causal": dict(
            base,
            data=dict(_data(), m=[1, 2, 1, 2, 1, 2]),
            identification={"method": "frontdoor", "mediator": "m", "adjustment_set": ["m"]},
        )}))


def test_iv_and_longitudinal_validation_errors():
    base = {"data": _data(), "treatment": "x", "outcome": "y"}
    with pytest.raises(ValueError, match="requires an 'instrument'"):
        _estimate(_model({"causal": dict(base, identification={"method": "iv"})}))
    with pytest.raises(ValueError, match="requires a 'time' variable"):
        _estimate(_model({"causal": dict(base, identification={"method": "longitudinal"})}))
    with pytest.raises(ValueError, match="time variable 'time' not found"):
        _estimate(_model({"causal": dict(
            base, identification={"method": "longitudinal", "time": "time"}
        )}))


def test_longitudinal_non_binary_and_intervention_validation():
    model = _model({"causal": {
        "data": {"x": [0, 1, 2, 0, 1, 2], "y": [1, 2, 3, 2, 3, 4], "time": [0, 1, 2, 3, 4, 5]},
        "treatment": "x", "outcome": "y",
        "identification": {"method": "longitudinal", "time": "time", "randomized": True},
    }})
    result = _estimate(model)
    assert result["causal_effect"]["method"] == "marginal_structural_model_ipw"
    assert result["solver"]["method"] == "marginal_structural_model_ipw"
    assert result["causal_effect"]["weights_stats"]["min"] == 1.0
    assert result["causal_effect"]["weights_stats"]["max"] == 1.0

    bad = _model({"causal": {
        "data": _data(), "treatment": "x", "outcome": "y",
        "identification": {"randomized": True},
        "intervention_values": [float("inf")],
    }})
    with pytest.raises(ValueError, match="intervention values must be finite"):
        _estimate(bad)
