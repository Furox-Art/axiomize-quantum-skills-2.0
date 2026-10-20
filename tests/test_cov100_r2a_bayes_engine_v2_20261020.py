"""Coverage hardening round 2a: Bayesian Engine 2.0 (engine_v2)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.bayesian.engine_v2 import (
    _log_prior,
    _parameters,
    _validate_observations_for_family,
    infer_bayesian_model,
)
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec

OBS = [0.9, 1.1, 1.0, 0.8]


def _cfg(**overrides):
    cfg = {"observations": OBS, "mean_expression": "p", "draws": 50, "burn": 0, "chains": 2}
    cfg.update(overrides)
    return cfg


def _model(parameters, bayesian, *, variables=None, equations=None) -> ModelIR:
    return ModelIR(
        name="bayes",
        domain="test",
        family=ModelFamily.BAYESIAN,
        variables=list(variables or []),
        parameters=list(parameters),
        equations=list(equations or []),
        metadata={"bayesian": bayesian},
    )


def _run(model, seed=3):
    return infer_bayesian_model(
        model, t_span=(0.0, 1.0), points=50, parameter_overrides=None, seed=seed
    )


def test_observation_family_validation():
    for family, bad in (
        ("bernoulli", [0.0, 2.0]),
        ("poisson", [1.0, -1.0]),
        ("gamma", [1.0, 0.0]),
        ("exponential", [1.0, -0.5]),
    ):
        with pytest.raises(ValueError):
            _validate_observations_for_family(family, np.asarray(bad, dtype=float))
    assert _validate_observations_for_family("bernoulli", np.asarray([0.0, 1.0])) is None
    assert _validate_observations_for_family("poisson", np.asarray([0.0, 3.0])) is None
    assert _validate_observations_for_family("gamma", np.asarray([0.5, 3.0])) is None
    assert _validate_observations_for_family("exponential", np.asarray([0.0, 3.0])) is None
    assert _validate_observations_for_family("normal", np.asarray([-3.0, 3.0])) is None


def test_parameter_resolution_errors():
    model = _model([ParameterSpec(name="k", value=2.0)], _cfg(mean_expression="k"))
    assert _parameters(model, {"k": 3}) == {"k": 3.0}
    with pytest.raises(ValueError, match="unknown parameter overrides"):
        _parameters(model, {"nope": 1.0})
    with pytest.raises(ValueError, match="has no value"):
        _parameters(_model([ParameterSpec(name="k")], _cfg(mean_expression="k")), None)
    with pytest.raises(ValueError, match="must be finite"):
        _parameters(model, {"k": math.inf})


def test_log_prior_bounds_and_builtin_distributions():
    assert _log_prior(-1.0, None, (0.0, 1.0), 0.5) == -math.inf
    assert _log_prior(2.0, None, (0.0, 1.0), 0.5) == -math.inf
    assert math.isfinite(_log_prior(0.5, None, (0.0, 1.0), 0.5))
    assert _log_prior(2.0, None, (None, 1.0), 0.5) == -math.inf
    assert math.isfinite(_log_prior(0.25, None, (None, 1.0), 0.5))
    assert _log_prior(-1.0, None, (0.0, None), 0.5) == -math.inf
    assert math.isfinite(_log_prior(0.25, None, (0.0, None), 0.5))

    default = _log_prior(1.0, None, None, 2.0)
    scale = 20.0
    assert default == pytest.approx(-0.5 * ((1.0 - 2.0) / scale) ** 2 - math.log(scale))

    normal = _log_prior(1.0, {"dist": "normal", "mu": 1.0, "sigma": 2.0}, None, 0.0)
    assert normal == pytest.approx(-math.log(2.0))
    with pytest.raises(ValueError, match="normal prior sigma"):
        _log_prior(1.0, {"dist": "normal", "sigma": 0.0}, None, 0.0)

    assert _log_prior(-1.0, {"dist": "halfnormal", "sigma": 1.0}, None, 0.0) == -math.inf
    assert _log_prior(2.0, {"dist": "halfnormal", "sigma": 2.0}, None, 0.0) == pytest.approx(
        -0.5 * (2.0 / 2.0) ** 2 - math.log(2.0)
    )
    with pytest.raises(ValueError, match="halfnormal prior sigma"):
        _log_prior(1.0, {"dist": "halfnormal", "sigma": -1.0}, None, 0.0)

    assert _log_prior(0.5, {"dist": "uniform", "low": 0.0, "high": 1.0}, None, 0.0) == 0.0
    assert _log_prior(1.5, {"dist": "uniform", "low": 0.0, "high": 1.0}, None, 0.0) == -math.inf
    with pytest.raises(ValueError, match="uniform prior lower"):
        _log_prior(1.0, {"dist": "uniform", "low": 1.0, "high": 1.0}, None, 0.0)

    assert _log_prior(0.0, {"dist": "lognormal"}, None, 0.0) == -math.inf
    assert _log_prior(1.0, {"dist": "lognormal"}, None, 0.0) == pytest.approx(-math.log(1.0))
    with pytest.raises(ValueError, match="lognormal prior sigma"):
        _log_prior(1.0, {"dist": "lognormal", "sigma": 0.0}, None, 0.0)
    with pytest.raises(ValueError, match="unsupported builtin prior"):
        _log_prior(1.0, {"dist": "cauchy"}, None, 0.0)


def test_inference_metadata_and_option_validation():
    base = [ParameterSpec(name="p", value=1.0, fit=True)]

    bad_cfg = ModelIR(
        name="bayes", domain="test", family=ModelFamily.BAYESIAN,
        variables=[], parameters=base, equations=[], metadata={"bayesian": "bad"},
    )
    with pytest.raises(ValueError, match="metadata.bayesian must be an object"):
        _run(bad_cfg)
    with pytest.raises(ValueError, match="bayesian.data must be an object"):
        _run(_model(base, _cfg(data="bad")))
    with pytest.raises(ValueError, match="requires mean_expression"):
        _run(_model(base, {"observations": OBS, "draws": 50, "burn": 0}))
    with pytest.raises(ValueError, match="sigma parameter name is unknown"):
        _run(_model(base, _cfg(sigma="missing")))
    with pytest.raises(ValueError, match="sampler must be"):
        _run(_model(base, _cfg(sampler="hmc")))
    with pytest.raises(ValueError, match="langevin_step must be finite"):
        _run(_model(base, _cfg(sampler="mala", langevin_step=0.0)))
    with pytest.raises(ValueError, match="likelihood-work"): 
        _run(_model(base, _cfg(observations=[1.0] * 300, draws=100000, burn=100000, chains=4)))

    from_equation = ModelIR(
        name="bayes", domain="test", family=ModelFamily.BAYESIAN, variables=[], parameters=base,
        equations=[EquationSpec(target="", expression="p", kind="likelihood")],
        metadata={"bayesian": {"observations": OBS, "draws": 50, "burn": 0, "chains": 2}},
    )
    assert _run(from_equation)["status"] == "PASS"

    with pytest.raises(ValueError, match="student_t df must be a finite number"):
        _run(_model(base, _cfg(likelihood={"dist": "student_t", "df": "abc"})))
    with pytest.raises(ValueError, match="student_t df must be a finite number"):
        _run(_model(base, _cfg(likelihood={"dist": "student_t", "df": -1.0})))
    student = _run(_model(base, _cfg(likelihood={"dist": "student_t", "df": 5.0})))
    assert student["solver"]["likelihood"] == "student_t"

    scalar_predictor = _run(
        _model(base, _cfg(data={"x": 1.5}, mean_expression="p*x", proposal_scale={"p": 0.05}))
    )
    assert scalar_predictor["status"] == "PASS"

    sampled = _run(_model(base, _cfg(return_samples=True, proposal_scale={"p": 0.05})))
    assert len(sampled["samples"]["p"]) == 100
    assert sampled["diagnostics"]["finite"] is True


def test_proposal_scale_branch_matrix():
    parameters = [
        ParameterSpec(name="a", value=1.0, fit=True),
        ParameterSpec(name="b", value=1.0, fit=True, prior={"dist": "halfnormal", "sigma": 1.0}),
        ParameterSpec(name="c", value=1.0, fit=True, bounds=(0.5, 2.0)),
        ParameterSpec(name="d", value=1.0, fit=True),
    ]
    out = _run(
        _model(parameters, _cfg(mean_expression="a+b+c+d", proposal_scale={"a": 0.05}, draws=60)),
        seed=10,
    )
    assert out["status"] == "PASS"
    assert sorted(out["posterior"]) == ["a", "b", "c", "d"]
    assert all(math.isfinite(row["sd"]) for row in out["posterior"].values())

    numeric = _run(
        _model([ParameterSpec(name="p", value=1.0, fit=True)], _cfg(proposal_scale=0.05)),
        seed=11,
    )
    assert numeric["status"] == "PASS"

    with pytest.raises(ValueError, match="proposal scale for p must be finite and positive"):
        _run(_model([ParameterSpec(name="p", value=1.0, fit=True)], _cfg(proposal_scale={"p": 0.0})))


def test_posterior_invalid_density_branches():
    bounded = _run(
        _model(
            [ParameterSpec(name="p", value=1.0, fit=True, bounds=(0.99, 1.01))],
            _cfg(proposal_scale={"p": 0.1}),
        ),
        seed=5,
    )
    assert bounded["status"] == "PASS"
    assert bounded["diagnostics"]["finite"] is True
    assert 0.99 <= bounded["posterior"]["p"]["mean"] <= 1.01

    non_finite_mean = _run(
        _model(
            [ParameterSpec(name="p", value=0.25, fit=True)],
            _cfg(mean_expression="sqrt(p)", proposal_scale={"p": 1.0}),
        ),
        seed=6,
    )
    assert non_finite_mean["status"] == "PASS"
    assert non_finite_mean["diagnostics"]["finite"] is True

    poisson = _run(
        _model(
            [ParameterSpec(name="p", value=1.0, fit=True)],
            _cfg(
                observations=[1, 2, 1, 3],
                likelihood={"dist": "poisson"},
                proposal_scale={"p": 1.0},
            ),
        ),
        seed=7,
    )
    assert poisson["status"] == "PASS"
    assert poisson["solver"]["likelihood"] == "poisson"


def test_mala_sampler_and_fallback_paths():
    plain = _run(
        _model(
            [ParameterSpec(name="p", value=1.0, fit=True)],
            _cfg(sampler="mala", langevin_step=0.1, proposal_scale={"p": 0.05}),
        ),
        seed=3,
    )
    assert plain["solver"]["method"] == "metropolis_adjusted_langevin"
    assert plain["diagnostics"]["sampler"] == "mala"
    assert plain["diagnostics"]["sampler_steps"] == 100

    gradient_non_finite = _run(
        _model(
            [ParameterSpec(name="p", value=1.0, fit=True, bounds=(0.9999, 1.0001))],
            _cfg(sampler="mala", langevin_step=1.0, proposal_scale={"p": 0.001}),
        ),
        seed=1,
    )
    assert gradient_non_finite["status"] == "PASS"
    assert gradient_non_finite["diagnostics"]["langevin_fallback_steps"] == 100

    proposal_outside = _run(
        _model(
            [ParameterSpec(name="p", value=1.0, fit=True, bounds=(0.99, 1.01))],
            _cfg(sampler="mala", langevin_step=1.0, proposal_scale={"p": 0.5}),
        ),
        seed=2,
    )
    assert proposal_outside["status"] == "PASS"
    assert proposal_outside["diagnostics"]["langevin_fallback_steps"] > 0

    gradient_proposal_non_finite = _run(
        _model(
            [ParameterSpec(name="p", value=1.0, fit=True, bounds=(None, 1.0001))],
            _cfg(sampler="mala", langevin_step=1.0, proposal_scale={"p": 1e-6}),
        ),
        seed=4,
    )
    assert gradient_proposal_non_finite["status"] == "PASS"
    assert gradient_proposal_non_finite["diagnostics"]["langevin_fallback_steps"] > 0
