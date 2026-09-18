"""Numerical reference comparisons: verify engine outputs against analytical
or external-library truth, per roadmap item 2."""
from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize.general_engine import simulate_model
from axiomize.model_ir import ModelIR


def _model(payload: dict) -> ModelIR:
    return ModelIR.from_dict({"schema_version": "1.0", "domain": "general", **payload})


# ---------------------------------------------------------------------------
# Bayesian reference comparisons
# ---------------------------------------------------------------------------

class TestBayesianReference:
    """MCMC posterior summaries should agree with analytical reference values."""

    def test_poisson_posterior_mean_matches_analytical_mle(self) -> None:
        """For y ~ Poisson(a * x) the MLE is sum(y) / sum(x)."""
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]
        model = _model({
            "name": "pois_ref", "family": "bayesian",
            "variables": [{"name": "y", "role": "output", "initial": 0.0}],
            "parameters": [{"name": "a", "value": 2.0, "fit": True,
                            "prior": {"dist": "normal", "mu": 2.0, "sigma": 1.0}}],
            "equations": [{"target": "y", "expression": "a*x", "kind": "observation"}],
            "metadata": {"bayesian": {
                "data": {"x": x}, "observations": y,
                "mean_expression": "a*x",
                "likelihood": {"dist": "poisson"},
                "draws": 400, "burn": 100, "chains": 3,
                "proposal_scale": {"a": 0.03},
            }, "numerical_verification": {"enabled": False}}
        })
        result = simulate_model(model, seed=42, approve_heavy=True)
        # Analytical MLE for Poisson rate = a*x:
        #   d/da log L = sum(y)/a - sum(x) = 0  ->  a = sum(y)/sum(x)
        mle = float(sum(y) / sum(x))  # = 30/15 = 2.0
        assert result["posterior"]["a"]["mean"] == pytest.approx(mle, abs=0.25)

    def test_gaussian_posterior_mean_matches_conjugate_formula(self) -> None:
        """For y ~ N(a*x, sigma) with N(mu0, s0) prior the conjugate posterior is known."""
        x = [0, 1, 2, 3, 4]
        y = [0, 2, 4, 6, 8]
        sigma = 0.2
        model = _model({
            "name": "gauss_ref", "family": "bayesian",
            "variables": [{"name": "y", "role": "output", "initial": 0.0}],
            "parameters": [{"name": "a", "value": 1.8, "fit": True,
                            "prior": {"dist": "normal", "mu": 0.0, "sigma": 3.0}}],
            "equations": [{"target": "y", "expression": "a*x", "kind": "observation"}],
            "metadata": {"bayesian": {
                "data": {"x": x}, "observations": y,
                "mean_expression": "a*x", "sigma": sigma,
                "draws": 300, "burn": 80, "chains": 3,
                "proposal_scale": {"a": 0.08},
            }, "numerical_verification": {"enabled": False}}
        })
        result = simulate_model(model, seed=7, approve_heavy=True)
        # Conjugate Bayesian linear regression with known variance:
        #   prec_post = 1/s0^2 + sum(x^2)/sigma^2
        #   mean_post = prec_post^{-1} * (mu0/s0^2 + sum(x*y)/sigma^2)
        s0 = 3.0; mu0 = 0.0; sig2 = sigma ** 2
        sx2 = sum(v * v for v in x)
        sxy = sum(xi * yi for xi, yi in zip(x, y))
        prec_post = 1.0 / s0 ** 2 + sx2 / sig2
        var_post = 1.0 / prec_post
        mean_post = var_post * (mu0 / s0 ** 2 + sxy / sig2)
        std_post = math.sqrt(var_post)
        assert result["posterior"]["a"]["mean"] == pytest.approx(mean_post, abs=0.15)
        assert result["posterior"]["a"]["sd"] == pytest.approx(std_post, abs=0.015)


# ---------------------------------------------------------------------------
# Causal reference comparisons
# ---------------------------------------------------------------------------

class TestCausalReference:
    """Engine causal estimates should agree with manual numpy calculations."""

    def test_iv_two_stage_least_squares_matches_manual(self) -> None:
        """2SLS: regress T on Z, then Y on predicted T."""
        z = [0, 0, 1, 1, 0, 1, 0, 1]
        t = [1, 1, 3, 3, 1, 3, 1, 3]
        y = [3, 3, 9, 9, 3, 9, 3, 9]
        model = _model({
            "name": "iv_ref", "family": "causal",
            "variables": [{"name": "y", "role": "output", "initial": 0.0}], "parameters": [],
            "equations": [{"target": "y", "expression": "0", "kind": "causal"}],
            "metadata": {"causal": {
                "treatment": "t", "outcome": "y",
                "data": {"z": z, "t": t, "y": y},
                "identification": {"method": "iv", "instrument": "z"},
                "intervention_values": [1, 3]}}
        })
        result = simulate_model(model)
        # Manual 2SLS with numpy lstsq
        n = len(t)
        z_arr = np.array(z, dtype=float)
        t_arr = np.array(t, dtype=float)
        y_arr = np.array(y, dtype=float)
        X1 = np.column_stack([np.ones(n), z_arr])
        b1, _, _, _ = np.linalg.lstsq(X1, t_arr, rcond=None)
        t_hat = X1 @ b1
        X2 = np.column_stack([np.ones(n), t_hat])
        b2, _, _, _ = np.linalg.lstsq(X2, y_arr, rcond=None)
        manual_iv = float(b2[1])
        assert result["causal_effect"]["estimate"] == pytest.approx(manual_iv, abs=1e-10)
        assert result["causal_effect"]["estimate"] == pytest.approx(3.0, abs=1e-10)

    def test_frontdoor_matches_manual_indirect_effect(self) -> None:
        """Front-door: alpha (X->M) * beta (M->Y|X) + gamma (X->Y direct)."""
        t = [0, 0, 0, 0, 1, 1, 1, 1]
        m = [0, 0, 0, 0, 2, 2, 2, 2]
        y = [0, 0, 0, 0, 6, 6, 6, 6]
        model = _model({
            "name": "fd_ref", "family": "causal",
            "variables": [{"name": "y", "role": "output", "initial": 0.0}], "parameters": [],
            "equations": [{"target": "y", "expression": "0", "kind": "causal"}],
            "metadata": {"causal": {
                "treatment": "t", "outcome": "y",
                "data": {"t": t, "m": m, "y": y},
                "identification": {"method": "frontdoor", "mediator": "m"},
                "intervention_values": [0, 1]}}
        })
        result = simulate_model(model)
        # Manual front-door calculation
        n = len(t)
        t_arr = np.array(t, dtype=float)
        m_arr = np.array(m, dtype=float)
        y_arr = np.array(y, dtype=float)
        # Stage 1: M ~ 1 + T
        X1 = np.column_stack([np.ones(n), t_arr])
        b1, _, _, _ = np.linalg.lstsq(X1, m_arr, rcond=None)
        alpha = float(b1[1])
        # Stage 2: Y ~ 1 + T + M
        X2 = np.column_stack([np.ones(n), t_arr, m_arr])
        b2, _, _, _ = np.linalg.lstsq(X2, y_arr, rcond=None)
        beta = float(b2[2])  # coef of M
        gamma = float(b2[1])  # coef of T (direct)
        manual_fd = alpha * beta + gamma
        assert result["causal_effect"]["estimate"] == pytest.approx(manual_fd, abs=1e-10)
        assert result["causal_effect"]["estimate"] == pytest.approx(6.0, abs=1e-10)

    def test_longitudinal_msm_recovers_known_effect(self) -> None:
        """MSM with IPW should recover the true time-varying treatment effect."""
        t = [0, 1, 0, 1, 0, 1, 0, 1]
        time_arr = [0, 1, 2, 3, 4, 5, 6, 7]
        y = [0, 3, 0, 3, 0, 3, 0, 3]
        model = _model({
            "name": "longi_ref", "family": "causal",
            "variables": [{"name": "y", "role": "output", "initial": 0.0}], "parameters": [],
            "equations": [{"target": "y", "expression": "0", "kind": "causal"}],
            "metadata": {"causal": {
                "treatment": "t", "outcome": "y",
                "data": {"t": t, "time": time_arr, "y": y},
                "identification": {"method": "longitudinal", "time": "time"},
                "intervention_values": [0, 1]}}
        })
        result = simulate_model(model)
        # Reference: OLS y ~ 1 + t + time (weights ~uniform for this data)
        n = len(t)
        X = np.column_stack([np.ones(n), np.array(t, float), np.array(time_arr, float)])
        b, _, _, _ = np.linalg.lstsq(X, np.array(y, float), rcond=None)
        ols_effect = float(b[1])
        assert result["causal_effect"]["estimate"] == pytest.approx(ols_effect, abs=0.5)
        assert result["causal_effect"]["estimate"] == pytest.approx(3.0, abs=0.5)
