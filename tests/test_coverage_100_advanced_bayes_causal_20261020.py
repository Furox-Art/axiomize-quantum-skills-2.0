"""Coverage hardening for advanced-family native executors.

The package runtime replaces ``_infer_bayesian`` and ``_estimate_causal`` with
v1.2.0 wrappers, so the pristine module is also loaded under a private name to
exercise those original implementations directly.  All assertions target
observable results/errors; only optional expression/solver boundaries are
stubbed where noted.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from axiomize.model_ir import (
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    SolverSpec,
    VariableSpec,
)

_SOURCE = Path(__file__).resolve().parents[1] / "src" / "axiomize" / "advanced_family_engine.py"
_FRESH = None


def fresh():
    global _FRESH
    if _FRESH is None:
        spec = importlib.util.spec_from_file_location("advanced_family_engine_fresh_cov", _SOURCE)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _FRESH = module
    return _FRESH


def _model(family, *, variables=None, parameters=None, equations=None, metadata=None, solver=None):
    return ModelIR(
        name="coverage",
        domain="test",
        family=family,
        variables=list(variables or []),
        parameters=list(parameters or []),
        equations=list(equations or []),
        metadata=dict(metadata or {}),
        solver=solver or SolverSpec(),
    )


def _call(method, model, *, points=8, overrides=None, seed=5, t_span=(0.0, 1.0)):
    return method(model, t_span=t_span, points=points, parameter_overrides=overrides, seed=seed)


# ---------------------------------------------------------------------------
# Bayesian native executor (original, pre-runtime-patch implementation)
# ---------------------------------------------------------------------------

def _bayes_model(*, parameters=None, equations=None, metadata=None, variable_initial=0.0):
    return _model(
        ModelFamily.BAYESIAN,
        variables=[VariableSpec(name="y", initial=variable_initial)],
        parameters=parameters,
        equations=equations,
        metadata=metadata,
    )


def _normal_param(name="mu", value=0.0, **kwargs):
    return ParameterSpec(name=name, value=value, **kwargs)


def test_bayesian_success_and_samples():
    module = fresh()
    model = _bayes_model(
        parameters=[_normal_param("mu", 0.0, fit=True, prior={"dist": "normal", "sigma": 2.0})],
        metadata={"bayesian": {
            "observations": [0.1, 0.2, 0.3],
            "mean_expression": "mu",
            "draws": 60,
            "burn": 10,
            "seed": 3,
            "return_samples": True,
        }},
    )
    result = _call(module._infer_bayesian, model)
    assert result["status"] == "PASS"
    assert result["family"] == "bayesian"
    assert result["states"] == {"y": 0.0}
    assert set(result["posterior"]) == {"mu"}
    summary = result["posterior"]["mu"]
    assert summary["q025"] <= summary["median"] <= summary["q975"]
    assert np.isfinite(summary["sd"])
    assert result["diagnostics"]["draws"] == 60
    assert result["diagnostics"]["burn"] == 10
    assert 0.0 <= result["diagnostics"]["acceptance_rate"] <= 1.0
    assert result["diagnostics"]["finite"] is True
    assert len(result["samples"]["mu"]) == 60
    assert result["solver"] == {"backend": "builtin", "method": "random_walk_metropolis", "seed": 5}


def test_bayesian_proposal_scale_variants_and_sigma_parameter():
    module = fresh()
    parameters = [
        _normal_param("a", 0.0, fit=True, prior={"dist": "normal", "sigma": 0.5}),
        _normal_param("b", 1.0, fit=True, bounds=(0.0, 2.0)),
        _normal_param("c", 2.0, fit=True),
        _normal_param("d", 3.0, fit=True),
        _normal_param("s", 1.0, fit=True),
    ]
    metadata = {"bayesian": {
        "observations": [0.0, 0.1, -0.1],
        "mean_expression": "a",
        "sigma": "s",
        "draws": 50,
        "burn": 5,
        "proposal_scale": {"d": 0.2},
    }}
    result = _call(module._infer_bayesian, _bayes_model(parameters=parameters, metadata=metadata))
    assert result["status"] == "PASS"
    assert set(result["posterior"]) == {"a", "b", "c", "d", "s"}
    assert "samples" not in result

    metadata["bayesian"]["proposal_scale"] = 0.3
    result = _call(module._infer_bayesian, _bayes_model(parameters=parameters, metadata=metadata))
    assert result["status"] == "PASS"


def test_bayesian_outcome_and_equation_fallbacks():
    module = fresh()
    model = _bayes_model(
        parameters=[_normal_param()],
        equations=[EquationSpec(target="y", expression="mu", kind="observation")],
        metadata={"bayesian": {
            "outcome": "y",
            "data": {"y": [0.2, 0.3, 0.4]},
            "draws": 50,
            "burn": 5,
        }},
    )
    result = _call(module._infer_bayesian, model)
    assert result["status"] == "PASS"


def test_bayesian_configuration_errors():
    module = fresh()
    with pytest.raises(ValueError, match="metadata.bayesian must be an object"):
        _call(module._infer_bayesian, _bayes_model(parameters=[_normal_param()], metadata={"bayesian": []}))
    with pytest.raises(ValueError, match="bayesian.data must be an object"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param()], metadata={"bayesian": {"data": []}}))
    with pytest.raises(ValueError, match="requires observations"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param()], metadata={"bayesian": {}}))
    with pytest.raises(ValueError, match="at least 2 values"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param()], metadata={"bayesian": {"observations": [1.0]}}))
    with pytest.raises(ValueError, match="requires mean_expression"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param()], metadata={"bayesian": {"observations": [1.0, 2.0]}}))
    with pytest.raises(ValueError, match="requires at least one parameter"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[],
            metadata={"bayesian": {"observations": [1.0, 2.0], "mean_expression": "mu"}}))
    with pytest.raises(ValueError, match="must be scalar or match observations"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param()],
            metadata={"bayesian": {
                "observations": [1.0, 2.0, 3.0], "mean_expression": "mu",
                "data": {"p": [1.0, 2.0]}, "outcome": "y",
            }},
        ))
    with pytest.raises(ValueError, match="sigma parameter name is unknown"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param()],
            metadata={"bayesian": {
                "observations": [1.0, 2.0], "mean_expression": "mu", "sigma": "missing",
            }},
        ))
    with pytest.raises(ValueError, match="draws must be in"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param()],
            metadata={"bayesian": {
                "observations": [1.0, 2.0], "mean_expression": "mu", "draws": 10,
            }},
        ))


def test_bayesian_invalid_initial_posterior():
    module = fresh()
    with pytest.raises(ValueError, match="zero/invalid posterior density"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param("mu", -1.0, fit=True, prior={"dist": "halfnormal"})],
            metadata={"bayesian": {"observations": [1.0, 2.0], "mean_expression": "mu"}},
        ))
    with pytest.raises(ValueError, match="zero/invalid posterior density"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param("s", -1.0, fit=True)],
            metadata={"bayesian": {
                "observations": [1.0, 2.0], "mean_expression": "s", "sigma": "s",
            }},
        ))
    with pytest.raises(ValueError, match="zero/invalid posterior density"):
        _call(module._infer_bayesian, _bayes_model(
            parameters=[_normal_param("mu", 0.0, fit=True)],
            metadata={"bayesian": {
                "observations": [1.0, 2.0],
                "mean_expression": "p * 1e300",
                "data": {"p": 1e10},
                "outcome": "o",
            }},
        ))


# ---------------------------------------------------------------------------
# Causal native executor (original, pre-runtime-patch implementation)
# ---------------------------------------------------------------------------

def _causal_metadata(**overrides):
    metadata = {
        "data": {
            "x": [0, 1, 0, 1, 0, 1],
            "z": [0.5, 0.2, 1.1, 0.9, 1.7, 1.4],
            "y": [2.5, 3.6, 4.3, 5.7, 6.1, 7.2],
        },
        "treatment": "x",
        "outcome": "y",
        "identification": {
            "identified_dag": True,
            "adjustment_set": ["z"],
            "assumptions": ["exchangeability"],
        },
        "intervention_values": [0.0, 1.0],
    }
    metadata.update(overrides)
    return {"causal": metadata}


def test_causal_success_with_counterfactuals():
    module = fresh()
    model = _model(ModelFamily.CAUSAL, variables=[VariableSpec(name="y")], metadata=_causal_metadata())
    result = _call(module._estimate_causal, model)
    assert result["status"] == "PASS"
    assert result["family"] == "causal"
    assert result["causal_effect"]["treatment"] == "x"
    assert math_isclose(result["causal_effect"]["estimate"], 2.0)
    assert result["causal_effect"]["std_error"] >= 0.0
    assert len(result["counterfactuals"]) == 2
    assert result["counterfactuals"][0]["do"] == {"x": 0.0}
    assert result["diagnostics"]["n"] == 6
    assert result["diagnostics"]["columns"] == ["intercept", "x", "z"]
    assert result["solver"]["method"] == "linear_backdoor_adjustment"


def math_isclose(left, right, tol=1e-9):
    return abs(float(left) - float(right)) <= tol


def test_causal_insufficient_and_non_dict_identification():
    module = fresh()
    model = _model(ModelFamily.CAUSAL, variables=[VariableSpec(name="y")],
                   metadata={"causal": {"data": {"x": [0, 1, 0], "y": [0, 1, 0]},
                                        "treatment": "x", "outcome": "y"}})
    result = _call(module._estimate_causal, model)
    assert result["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"

    model = _model(ModelFamily.CAUSAL, variables=[VariableSpec(name="y")],
                   metadata={"causal": {"data": {"x": [0, 1, 0], "y": [0, 1, 0]},
                                        "treatment": "x", "outcome": "y",
                                        "identification": "bogus"}})
    assert _call(module._estimate_causal, model)["status"] == "INSUFFICIENT_CAUSAL_EVIDENCE"


def test_causal_errors():
    module = fresh()
    with pytest.raises(ValueError, match="metadata.causal must be an object"):
        _call(module._estimate_causal, _model(ModelFamily.CAUSAL, metadata={"causal": []}))

    identified = {"randomized": True}
    with pytest.raises(ValueError, match="adjustment_set/covariates must be an array"):
        _call(module._estimate_causal, _model(
            ModelFamily.CAUSAL,
            metadata={"causal": {"identification": dict(identified, adjustment_set="z")}},
        ))
    with pytest.raises(ValueError, match="causal.data must be an object"):
        _call(module._estimate_causal, _model(
            ModelFamily.CAUSAL, metadata={"causal": {"identification": identified, "data": []}}))
    with pytest.raises(ValueError, match="treatment/outcome names present in data"):
        _call(module._estimate_causal, _model(
            ModelFamily.CAUSAL, metadata={"causal": {"identification": identified, "data": {}}}))
    with pytest.raises(ValueError, match="same-length 1D arrays"):
        _call(module._estimate_causal, _model(
            ModelFamily.CAUSAL,
            metadata={"causal": {"identification": identified, "data": {"x": [0, 1], "y": [0, 1]},
                                 "treatment": "x", "outcome": "y"}},
        ))
    with pytest.raises(ValueError, match="adjustment variable 'z' missing"):
        _call(module._estimate_causal, _model(
            ModelFamily.CAUSAL,
            metadata={"causal": {
                "identification": dict(identified, adjustment_set=["z"]),
                "data": {"x": [0, 1, 0], "y": [0, 1, 0]},
                "treatment": "x", "outcome": "y",
            }},
        ))
    with pytest.raises(ValueError, match="covariate 'z' length mismatch"):
        _call(module._estimate_causal, _model(
            ModelFamily.CAUSAL,
            metadata={"causal": {
                "identification": dict(identified, adjustment_set=["z"]),
                "data": {"x": [0, 1, 0], "y": [0, 1, 0], "z": [1, 2]},
                "treatment": "x", "outcome": "y",
            }},
        ))


def test_causal_without_intervention_list():
    module = fresh()
    model = _model(ModelFamily.CAUSAL, metadata=_causal_metadata(intervention_values="all"))
    result = _call(module._estimate_causal, model)
    assert result["status"] == "PASS"
    assert result["counterfactuals"] == []
