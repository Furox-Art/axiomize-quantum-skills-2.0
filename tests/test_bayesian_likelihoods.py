"""Unit tests for Bayesian likelihood families (Engine 2.0)."""
from __future__ import annotations

import math

import numpy as np
import pytest
from scipy.special import gammaln

from axiomize.bayesian.likelihoods import (
    SUPPORTED_FAMILIES,
    log_likelihood,
    replicate,
    resolve_family,
)
from axiomize.bayesian.diagnostics import normal_posterior_predictive, posterior_predictive


class TestResolveFamily:
    def test_normal_is_default(self):
        assert resolve_family(None) == "normal"
        assert resolve_family("") == "normal"

    def test_gaussian_alias(self):
        assert resolve_family("gaussian") == "normal"

    def test_uppercase_normalized(self):
        assert resolve_family("POISSON") == "poisson"

    def test_unsupported_raises(self):
        with pytest.raises(ValueError, match="unsupported likelihood family"):
            resolve_family("cauchy")


class TestLogLikelihood:
    def test_normal_matches_formula(self):
        obs = np.array([0.0, 2.0, 4.0]); mean = np.array([0.0, 2.0, 4.0]); sigma = 0.5
        expected = -0.5 * float(np.dot((obs - mean) / sigma, (obs - mean) / sigma)) - obs.size * math.log(sigma)
        assert log_likelihood("normal", obs, mean, sigma) == pytest.approx(expected)

    def test_normal_rejects_bad_sigma(self):
        obs = np.array([1.0, 2.0]); mean = np.array([1.0, 2.0])
        for bad in (0.0, -1.0, None):
            assert log_likelihood("normal", obs, mean, bad) == -math.inf

    def test_poisson_matches_formula(self):
        obs = np.array([0.0, 2.0, 4.0]); mean = np.array([0.5, 2.0, 4.0])
        expected = float(np.sum(obs * np.log(mean) - mean - gammaln(obs + 1.0)))
        assert log_likelihood("poisson", obs, mean) == pytest.approx(expected)

    def test_poisson_rejects_negative_mean(self):
        obs = np.array([1.0, 2.0]); mean = np.array([-1.0, 2.0])
        assert log_likelihood("poisson", obs, mean) == -math.inf

    def test_bernoulli_matches_formula(self):
        obs = np.array([0.0, 1.0, 0.0, 1.0]); mean = np.array([0.3, 0.3, 0.7, 0.7])
        p = mean
        expected = float(np.sum(obs * np.log(p) + (1 - obs) * np.log(1 - p)))
        assert log_likelihood("bernoulli", obs, mean) == pytest.approx(expected)

    def test_bernoulli_rejects_out_of_range_mean(self):
        obs = np.array([0.0, 1.0]); mean = np.array([-0.1, 0.5])
        assert log_likelihood("bernoulli", obs, mean) == -math.inf
        mean2 = np.array([1.0, 1.5])
        assert log_likelihood("bernoulli", obs, mean2) == -math.inf

    def test_gamma_matches_formula(self):
        obs = np.array([1.0, 2.0, 3.0]); mean = np.array([1.0, 2.0, 3.0]); sigma = 0.5
        alpha = mean ** 2 / sigma ** 2
        beta = mean / sigma ** 2
        expected = float(np.sum(
            (alpha - 1) * np.log(obs) - beta * obs + alpha * np.log(beta) - gammaln(alpha)
        ))
        assert log_likelihood("gamma", obs, mean, sigma) == pytest.approx(expected)

    def test_gamma_rejects_nonpositive_mean(self):
        obs = np.array([1.0, 2.0]); mean = np.array([0.0, 2.0])
        assert log_likelihood("gamma", obs, mean, sigma=0.5) == -math.inf

    def test_gamma_rejects_bad_sigma(self):
        obs = np.array([1.0, 2.0]); mean = np.array([1.0, 2.0])
        assert log_likelihood("gamma", obs, mean, sigma=0.0) == -math.inf
        assert log_likelihood("gamma", obs, mean, sigma=None) == -math.inf

    def test_mismatched_shapes_return_minus_inf(self):
        obs = np.array([1.0, 2.0, 3.0]); mean = np.array([1.0, 2.0])
        assert log_likelihood("poisson", obs, mean) == -math.inf


class TestReplicateObservations:
    def test_replicate_normal_scalar_sigma(self):
        rng = np.random.default_rng(0)
        means = np.array([1.0, 2.0, 3.0])
        rep = replicate("normal", means, sigma=0.5, rng=rng)
        assert rep.shape == (3,)
        assert np.all(np.isfinite(rep))

    def test_replicate_normal_array_sigma(self):
        rng = np.random.default_rng(0)
        means = np.array([[1.0, 2.0], [3.0, 4.0]])
        sigma = np.array([0.5, 0.5])
        rep = replicate("normal", means, sigma=sigma, rng=rng)
        assert rep.shape == (2, 2)

    def test_replicate_poisson(self):
        rng = np.random.default_rng(0)
        means = np.array([2.0, 5.0, 10.0])
        rep = replicate("poisson", means, sigma=None, rng=rng)
        assert rep.shape == (3,)
        assert np.all(np.isfinite(rep))

    def test_replicate_bernoulli(self):
        rng = np.random.default_rng(0)
        means = np.array([0.3, 0.7, 0.5])
        rep = replicate("bernoulli", means, sigma=None, rng=rng)
        assert rep.shape == (3,)
        assert set(np.unique(rep)).issubset({0.0, 1.0})

    def test_replicate_gamma(self):
        rng = np.random.default_rng(0)
        means = np.array([1.0, 2.0, 3.0])
        rep = replicate("gamma", means, sigma=0.5, rng=rng)
        assert rep.shape == (3,)
        assert np.all(np.isfinite(rep))
        assert np.all(rep > 0)


class TestPosteriorPredictive:
    def test_ppc_poisson(self):
        observed = np.array([2.0, 4.0, 6.0])
        means = np.tile([2.0, 4.0, 6.0], (20, 1))
        result = posterior_predictive(family="poisson", observed=observed, means=means,
                                      sigmas=None, seed=42)
        assert result["family"] == "poisson"
        assert result["status"] == "PASS"
        assert "predictive_rmse" in result
        assert "coverage95" in result
        assert result["replications"] >= 10

    def test_ppc_bernoulli(self):
        observed = np.array([0.0, 1.0, 0.0, 1.0])
        means = np.tile([0.3, 0.7, 0.3, 0.7], (20, 1))
        result = posterior_predictive(family="bernoulli", observed=observed, means=means,
                                      sigmas=None, seed=42)
        assert result["family"] == "bernoulli"
        assert result["status"] == "PASS"
        assert "predictive_rmse" in result

    def test_ppc_gamma(self):
        observed = np.array([1.0, 2.0, 3.0])
        means = np.tile([1.0, 2.0, 3.0], (20, 1))
        result = posterior_predictive(family="gamma", observed=observed, means=means,
                                      sigmas=np.full(20, 0.5), seed=42)
        assert result["family"] == "gamma"
        assert result["status"] == "PASS"

    def test_normal_ppc_wrapper_backward_compat(self):
        observed = np.array([0.0, 2.0, 4.0])
        means = np.tile([0.0, 2.0, 4.0], (20, 1))
        sigmas = np.full(20, 0.5)
        via_wrapper = normal_posterior_predictive(observed=observed, means=means,
                                                  sigmas=sigmas, seed=42)
        via_dispatch = posterior_predictive(family="normal", observed=observed, means=means,
                                            sigmas=sigmas, seed=42)
        assert via_wrapper["family"] == "normal"
        assert via_dispatch["family"] == "normal"
        assert via_wrapper["predictive_rmse"] == pytest.approx(via_dispatch["predictive_rmse"])

    def test_ppc_rejects_insufficient_draws(self):
        observed = np.array([1.0, 2.0])
        means = np.tile([1.0, 2.0], (5, 1))
        with pytest.raises(ValueError, match="at least 10"):
            posterior_predictive(family="poisson", observed=observed, means=means,
                                 sigmas=None, seed=42)

    def test_ppc_rejects_bad_sigma_shape(self):
        observed = np.array([1.0, 2.0])
        means = np.tile([1.0, 2.0], (20, 1))
        bad_sigmas = np.array([[0.5, 0.5], [0.5, 0.5]])  # 2D, should be 1D
        with pytest.raises(ValueError, match="sigma vector"):
            posterior_predictive(family="normal", observed=observed, means=means,
                                 sigmas=bad_sigmas, seed=42)
