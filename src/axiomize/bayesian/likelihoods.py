"""Likelihood families for Bayesian inference (Engine 2.0).

The package-native Metropolis-Hastings sampler was originally Gaussian-only.
This module adds a small, hard-bounded set of additional likelihood families
(Poisson, Bernoulli, Gamma) so that non-Gaussian observations can be fit while
retaining the same approval-gated, dependency-free sampler and diagnostics.

Every function returns ``-inf`` (or a non-finite mask) outside the support of
the distribution rather than raising, so the MCMC sampler can reject proposals
gracefully.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy.special import gammaln

SUPPORTED_FAMILIES = ("normal", "poisson", "bernoulli", "gamma")


def resolve_family(family: Any) -> str:
    """Normalise and validate a likelihood family name.

    ``None`` and empty strings default to ``"normal"`` (Gaussian).
    """
    if family is None or str(family).strip() == "":
        return "normal"
    name = str(family).lower()
    if name == "gaussian":
        name = "normal"
    if name not in SUPPORTED_FAMILIES:
        raise ValueError(
            f"unsupported likelihood family: {family!r}; supported: {SUPPORTED_FAMILIES}"
        )
    return name


def _validate_shape(observed: np.ndarray, mean: np.ndarray) -> bool:
    return mean.shape == observed.shape and np.all(np.isfinite(mean))


def log_likelihood(
    family: Any,
    observed: np.ndarray,
    mean: np.ndarray,
    sigma: float | None = None,
) -> float:
    """Total log-likelihood of *observed* under *family*.

    Parameters
    ----------
    family
        Likelihood name ("normal", "poisson", "bernoulli", "gamma").
    observed
        1-D array of observations.
    mean
        Per-observation mean / rate / probability, same shape as *observed*.
    sigma
        Dispersion parameter for families that use it (``normal``, ``gamma``).
        Ignored by ``poisson`` and ``bernoulli``.
    """
    fam = resolve_family(family)
    observed = np.asarray(observed, dtype=float)
    mean = np.asarray(mean, dtype=float)
    if not _validate_shape(observed, mean):
        return -math.inf

    if fam == "normal":
        if sigma is None or sigma <= 0 or not math.isfinite(sigma):
            return -math.inf
        r = (observed - mean) / sigma
        return -0.5 * float(np.dot(r, r)) - observed.size * math.log(sigma)

    if fam == "poisson":
        if np.any(mean <= 0):
            return -math.inf
        return float(
            np.sum(observed * np.log(mean) - mean - gammaln(observed + 1.0))
        )

    if fam == "bernoulli":
        if np.any(mean < 0.0) or np.any(mean > 1.0):
            return -math.inf
        p = np.clip(mean, 1e-15, 1.0 - 1e-15)
        return float(
            np.sum(observed * np.log(p) + (1.0 - observed) * np.log(1.0 - p))
        )

    # gamma
    if sigma is None or sigma <= 0 or not math.isfinite(sigma):
        return -math.inf
    if np.any(mean <= 0) or np.any(observed < 0):
        return -math.inf
    alpha = mean ** 2 / sigma ** 2
    beta = mean / sigma ** 2
    return float(
        np.sum(
            (alpha - 1.0) * np.log(observed)
            - beta * observed
            + alpha * np.log(beta)
            - gammaln(alpha)
        )
    )


def replicate(
    family: Any,
    means: np.ndarray,
    sigma: float | np.ndarray | None,
    rng: np.random.Generator,
) -> np.ndarray:
    """Generate replicated observations for posterior predictive checks.

    Parameters
    ----------
    family
        Likelihood name.
    means
        Array of expected values with shape ``[n_draws, n_obs]``.
    sigma
        Per-draw dispersion (``normal``/``gamma``).  May be a scalar, a 1-D
        array of length ``n_draws``, or ``None`` for families that ignore it.
    rng
        Seeded NumPy generator.
    """
    fam = resolve_family(family)
    means = np.asarray(means, dtype=float)

    if fam == "normal":
        if sigma is None:
            sigma = 1.0
        sigma = np.asarray(sigma, dtype=float)
        if sigma.ndim == 0:
            return rng.normal(means, float(sigma))
        return rng.normal(means, sigma[:, None])

    if fam == "poisson":
        return rng.poisson(np.maximum(means, 0.0))

    if fam == "bernoulli":
        p = np.clip(means, 0.0, 1.0)
        return rng.binomial(1, p)

    # gamma
    if sigma is None:
        return means.copy()
    sigma = np.asarray(sigma, dtype=float)
    safe = np.maximum(means, 1e-15)
    safe_sigma = sigma if sigma.ndim == 0 else sigma[:, None]
    alpha = safe ** 2 / safe_sigma ** 2
    beta = safe / safe_sigma ** 2
    return rng.gamma(alpha, 1.0 / beta)
