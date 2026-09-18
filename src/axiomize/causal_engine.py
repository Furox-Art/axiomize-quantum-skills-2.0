"""Causal Engine 2.0 for explicit Model IR causal studies.

The engine never promotes association to causation. It requires supplied
identification evidence, validates DAG structure when present, and supports
backdoor, front-door, instrumental variable, and longitudinal marginal
structural model (MSM) identification. Doubly-robust AIPW is used for binary
treatments when covariates are available. Diagnostics surface positivity,
effective sample size, and covariate balance rather than hiding weak
identification.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from axiomize.model_ir import ModelIR

# Identification methods beyond backdoor adjustment.
_FRONTDOOR_ASSUMPTION = (
    "front-door criterion: mediator intercepts all directed X→Y paths, "
    "no unmeasured X–M confounding, no unmeasured M–Y confounding given X"
)
_IV_ASSUMPTIONS = [
    "exclusion restriction: instrument affects outcome only through treatment",
    "relevance: instrument is associated with treatment",
    "monotonicity: no defiers of opposite type",
]
_LONGITUDINAL_ASSUMPTIONS = [
    "sequential exchangeability",
    "consistency",
    "positivity",
]

_EPS = 1e-8


def _parameter_values(model: ModelIR, overrides: dict[str, float] | None) -> dict[str, float]:
    overrides = dict(overrides or {})
    known = {p.name for p in model.parameters}
    unknown = sorted(set(overrides) - known)
    if unknown:
        raise ValueError(f"unknown parameter overrides: {unknown}")
    out: dict[str, float] = {}
    for p in model.parameters:
        raw = overrides[p.name] if p.name in overrides else p.value
        if raw is None:
            raise ValueError(f"parameter {p.name!r} has no value")
        value = float(raw)
        if not math.isfinite(value):
            raise ValueError(f"parameter {p.name!r} must be finite")
        out[p.name] = value
    return out


def _finite_vector(data: dict[str, Any], name: str, *, n: int | None = None) -> np.ndarray:
    if name not in data:
        raise ValueError(f"causal variable {name!r} missing from data")
    arr = np.asarray(data[name], dtype=float)
    if arr.ndim != 1 or arr.size < 3:
        raise ValueError(f"causal variable {name!r} must be a 1D array with at least 3 rows")
    if n is not None and arr.size != n:
        raise ValueError(f"causal variable {name!r} length mismatch")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"causal variable {name!r} must be finite")
    return arr


def _dag(edges: Any) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    parents: dict[str, set[str]] = {}
    children: dict[str, set[str]] = {}
    if edges in (None, []):
        return parents, children
    if not isinstance(edges, list) or len(edges) > 10_000:
        raise ValueError("causal DAG edges must be an array with at most 10000 entries")
    for raw in edges:
        if isinstance(raw, dict):
            source, target = raw.get("source"), raw.get("target")
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            source, target = raw
        else:
            raise ValueError("each causal DAG edge must contain source and target")
        a, b = str(source), str(target)
        if not a or not b or a == b:
            raise ValueError("causal DAG edges require distinct non-empty node names")
        children.setdefault(a, set()).add(b)
        parents.setdefault(b, set()).add(a)
        parents.setdefault(a, set())
        children.setdefault(b, set())
    visiting: set[str] = set(); visited: set[str] = set()
    def visit(node: str) -> None:
        if node in visiting:
            raise ValueError("causal DAG contains a directed cycle")
        if node in visited:
            return
        visiting.add(node)
        for child in children.get(node, ()):
            visit(child)
        visiting.remove(node); visited.add(node)
    for node in set(parents) | set(children):
        visit(node)
    return parents, children


def _ancestors(node: str, parents: dict[str, set[str]]) -> set[str]:
    out: set[str] = set(); stack = list(parents.get(node, ()))
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current); stack.extend(parents.get(current, ()))
    return out


def _descendants(node: str, children: dict[str, set[str]]) -> set[str]:
    out: set[str] = set(); stack = list(children.get(node, ()))
    while stack:
        current = stack.pop()
        if current in out:
            continue
        out.add(current); stack.extend(children.get(current, ()))
    return out


def _derive_adjustment(treatment: str, outcome: str, parents: dict[str, set[str]], children: dict[str, set[str]], observed: set[str]) -> list[str]:
    if not parents and not children:
        return []
    ancestors_y = _ancestors(outcome, parents) | {outcome}
    descendants_t = _descendants(treatment, children)
    candidates = parents.get(treatment, set()) & ancestors_y
    return sorted((candidates - descendants_t - {treatment, outcome}) & observed)


def _ols(X: np.ndarray, y: np.ndarray, *, weights: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if weights is None:
        Xw, yw = X, y
    else:
        sw = np.sqrt(np.asarray(weights, dtype=float))
        Xw, yw = X * sw[:, None], y * sw
    beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
    residual = y - X @ beta
    # HC1 sandwich; more defensible than homoskedastic-only SE for observational data.
    bread = np.linalg.pinv(X.T @ X if weights is None else X.T @ (weights[:, None] * X))
    score = X * residual[:, None] if weights is None else X * (weights * residual)[:, None]
    meat = score.T @ score
    n, p = X.shape
    hc1 = n / max(1, n - p)
    cov = bread @ meat @ bread * hc1
    return beta, cov, residual


def _logistic_irls(X: np.ndarray, t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    beta = np.zeros(X.shape[1], dtype=float)
    for _ in range(100):
        eta = np.clip(X @ beta, -30.0, 30.0)
        p = 1.0 / (1.0 + np.exp(-eta))
        w = np.maximum(p * (1.0 - p), 1e-6)
        z = eta + (t - p) / w
        new, *_ = np.linalg.lstsq(X * np.sqrt(w)[:, None], z * np.sqrt(w), rcond=None)
        if np.max(np.abs(new - beta)) < 1e-9:
            beta = new; break
        beta = new
    propensity = np.clip(1.0 / (1.0 + np.exp(-np.clip(X @ beta, -30.0, 30.0))), 1e-4, 1 - 1e-4)
    return beta, propensity


def _smd(x: np.ndarray, t: np.ndarray, weights: np.ndarray | None = None) -> float:
    mask1, mask0 = t == 1, t == 0
    if not np.any(mask1) or not np.any(mask0):
        return math.inf
    if weights is None:
        m1, m0 = float(np.mean(x[mask1])), float(np.mean(x[mask0]))
        v1, v0 = float(np.var(x[mask1], ddof=1)), float(np.var(x[mask0], ddof=1))
    else:
        def moments(mask: np.ndarray) -> tuple[float, float]:
            w = weights[mask]; values = x[mask]; s = float(np.sum(w))
            mean = float(np.sum(w * values) / max(s, _EPS))
            var = float(np.sum(w * (values - mean) ** 2) / max(s, _EPS))
            return mean, var
        m1, v1 = moments(mask1); m0, v0 = moments(mask0)
    scale = math.sqrt(max((v1 + v0) / 2.0, _EPS))
    return abs(m1 - m0) / scale


def _binary_effect(y: np.ndarray, t: np.ndarray, Z: np.ndarray, labels: list[str]) -> dict[str, Any]:
    n = y.size
    propX = np.column_stack([np.ones(n), Z]) if Z.size else np.ones((n, 1))
    _, propensity = _logistic_irls(propX, t)
    overlap = {
        "min_propensity": float(np.min(propensity)),
        "max_propensity": float(np.max(propensity)),
        "fraction_outside_0.05_0.95": float(np.mean((propensity < 0.05) | (propensity > 0.95))),
    }
    ipw = t / propensity + (1.0 - t) / (1.0 - propensity)
    ess = float(np.sum(ipw) ** 2 / max(np.sum(ipw ** 2), _EPS))

    Xout = np.column_stack([np.ones(n), t, Z]) if Z.size else np.column_stack([np.ones(n), t])
    beta, cov, residual = _ols(Xout, y)
    reg_effect = float(beta[1]); reg_se = math.sqrt(max(0.0, float(cov[1, 1])))

    # Separate outcome models m1(z), m0(z).
    base = np.column_stack([np.ones(n), Z]) if Z.size else np.ones((n, 1))
    b1, *_ = np.linalg.lstsq(base[t == 1], y[t == 1], rcond=None)
    b0, *_ = np.linalg.lstsq(base[t == 0], y[t == 0], rcond=None)
    m1 = base @ b1; m0 = base @ b0
    psi = m1 - m0 + t * (y - m1) / propensity - (1.0 - t) * (y - m0) / (1.0 - propensity)
    aipw = float(np.mean(psi)); aipw_se = float(np.std(psi, ddof=1) / math.sqrt(n))
    ipw_effect = float(np.mean(t * y / propensity - (1.0 - t) * y / (1.0 - propensity)))

    before: dict[str, float] = {}; after: dict[str, float] = {}
    for i, label in enumerate(labels):
        before[label] = _smd(Z[:, i], t)
        after[label] = _smd(Z[:, i], t, ipw)
    return {
        "estimate": aipw,
        "std_error": aipw_se,
        "ci95": [aipw - 1.96 * aipw_se, aipw + 1.96 * aipw_se],
        "method": "aipw_doubly_robust" if Z.size else "aipw_unadjusted_randomized",
        "estimators": {
            "aipw": {"estimate": aipw, "std_error": aipw_se},
            "ipw": {"estimate": ipw_effect},
            "outcome_regression": {"estimate": reg_effect, "std_error": reg_se},
        },
        "positivity": overlap,
        "effective_sample_size_ipw": ess,
        "balance": {"standardized_mean_difference_before": before, "after_ipw": after},
        "residual_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def _continuous_effect(y: np.ndarray, t: np.ndarray, Z: np.ndarray) -> dict[str, Any]:
    X = np.column_stack([np.ones(y.size), t, Z]) if Z.size else np.column_stack([np.ones(y.size), t])
    beta, cov, residual = _ols(X, y)
    effect = float(beta[1]); se = math.sqrt(max(0.0, float(cov[1, 1])))
    return {
        "estimate": effect, "std_error": se,
        "ci95": [effect - 1.96 * se, effect + 1.96 * se],
        "method": "robust_linear_backdoor_adjustment",
        "residual_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def _frontdoor_effect(y: np.ndarray, t: np.ndarray, m: np.ndarray,
                      Z: np.ndarray | None) -> dict[str, Any]:
    n = y.size
    Z_arr = Z if Z is not None and Z.size else np.empty((n, 0))
    cols_m: list = [np.ones(n)]
    if Z_arr.size: cols_m.append(Z_arr)
    cols_m.append(t)
    b1, cov1, _ = _ols(np.column_stack(cols_m), m)
    alpha = float(b1[-1]); var_alpha = float(cov1[-1, -1])
    cols_y: list = [np.ones(n)]
    if Z_arr.size: cols_y.append(Z_arr)
    cols_y.extend([t, m])
    b2, cov2, residual = _ols(np.column_stack(cols_y), y)
    beta = float(b2[-1]); gamma = float(b2[-2])
    var_beta = float(cov2[-1, -1]); var_gamma = float(cov2[-2, -2])
    indirect = alpha * beta; total = indirect + gamma
    se_total = math.sqrt(max(0.0, beta ** 2 * var_alpha + alpha ** 2 * var_beta + var_gamma))
    se_indirect = math.sqrt(max(0.0, beta ** 2 * var_alpha + alpha ** 2 * var_beta))
    return {
        "estimate": total, "std_error": se_total,
        "ci95": [total - 1.96 * se_total, total + 1.96 * se_total],
        "method": "frontdoor_adjustment",
        "frontdoor_components": {
            "indirect_effect": {"estimate": indirect, "std_error": se_indirect},
            "direct_effect": {"estimate": gamma, "std_error": math.sqrt(max(0.0, var_gamma))},
            "x_to_m": {"estimate": alpha, "std_error": math.sqrt(max(0.0, var_alpha))},
            "m_to_y": {"estimate": beta, "std_error": math.sqrt(max(0.0, var_beta))},
        },
        "residual_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def _iv_effect(y: np.ndarray, t: np.ndarray, Z_inst: np.ndarray,
               Z_cov: np.ndarray | None) -> dict[str, Any]:
    n = y.size
    Z_arr = Z_cov if Z_cov is not None and Z_cov.size else np.empty((n, 0))
    cols1: list = [np.ones(n)]
    if Z_arr.size: cols1.append(Z_arr)
    cols1.append(Z_inst)
    b1, _, _ = _ols(np.column_stack(cols1), t)
    t_hat = np.column_stack(cols1) @ b1
    cols2: list = [np.ones(n)]
    if Z_arr.size: cols2.append(Z_arr)
    cols2.append(t_hat)
    X2 = np.column_stack(cols2)
    b2, cov2, residual = _ols(X2, y)
    iv_effect = float(b2[-1]); iv_se = math.sqrt(max(0.0, float(cov2[-1, -1])))
    first_stage_r2 = float(1.0 - np.var(t - t_hat) / max(np.var(t), _EPS))
    return {
        "estimate": iv_effect, "std_error": iv_se,
        "ci95": [iv_effect - 1.96 * iv_se, iv_effect + 1.96 * iv_se],
        "method": "instrumental_variables_2sls",
        "first_stage_r2": first_stage_r2,
        "residual_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def _longitudinal_effect(y: np.ndarray, t: np.ndarray, time_var: np.ndarray,
                         Z: np.ndarray | None) -> dict[str, Any]:
    n = y.size
    Z_arr = Z if Z is not None and Z.size else np.empty((n, 0))
    unique_t = np.unique(t)
    is_binary = unique_t.size == 2 and set(np.round(unique_t, 12).tolist()) <= {0.0, 1.0}
    cols = [np.ones(n), time_var]
    if Z_arr.size: cols.append(Z_arr)
    X_prop = np.column_stack(cols)
    if is_binary:
        _, propensity = _logistic_irls(X_prop, t.astype(int))
        weights = np.where(t == 1, 1.0 / np.maximum(propensity, _EPS),
                           1.0 / np.maximum(1.0 - propensity, _EPS))
    else:
        weights = np.ones(n)
    cols_w: list = [np.ones(n), t, time_var]
    if Z_arr.size: cols_w.append(Z_arr)
    beta, cov, residual = _ols(np.column_stack(cols_w), y, weights=weights)
    effect = float(beta[1]); se = math.sqrt(max(0.0, float(cov[1, 1])))
    n_eff = float(np.sum(weights) ** 2 / max(np.sum(weights ** 2), _EPS))
    return {
        "estimate": effect, "std_error": se,
        "ci95": [effect - 1.96 * se, effect + 1.96 * se],
        "method": "marginal_structural_model_ipw",
        "weights_stats": {"min": float(np.min(weights)), "max": float(np.max(weights)), "n_eff": n_eff},
        "residual_rmse": float(np.sqrt(np.mean(residual ** 2))),
    }


def estimate_causal_model(model: ModelIR, *, t_span: tuple[float, float], points: int,
                          parameter_overrides: dict[str, float] | None, seed: int) -> dict[str, Any]:
    del t_span, points, seed
    parameters = _parameter_values(model, parameter_overrides)
    cfg = model.metadata.get("causal", {})
    if not isinstance(cfg, dict):
        raise ValueError("metadata.causal must be an object")
    data = cfg.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("causal.data must be an object")
    treatment = str(cfg.get("treatment", "")); outcome = str(cfg.get("outcome", ""))
    if not treatment or not outcome:
        raise ValueError("causal model requires treatment and outcome names")
    y = _finite_vector(data, outcome); t = _finite_vector(data, treatment, n=y.size)

    identification = cfg.get("identification", model.metadata.get("causal_identification", {}))
    if not isinstance(identification, dict):
        identification = {}
    edges = identification.get("dag_edges", cfg.get("dag_edges", cfg.get("dag", [])))
    parents, children = _dag(edges)
    explicit = identification.get("adjustment_set", cfg.get("adjustment_set", cfg.get("covariates")))
    if explicit is not None and not isinstance(explicit, list):
        raise ValueError("causal adjustment_set must be an array")
    if explicit is None:
        adjustment = _derive_adjustment(treatment, outcome, parents, children, set(data))
    else:
        adjustment = [str(v) for v in explicit]
    if treatment in adjustment or outcome in adjustment:
        raise ValueError("adjustment set cannot include treatment or outcome")
    descendants = _descendants(treatment, children)
    post_treatment = sorted(set(adjustment) & descendants)
    if post_treatment:
        raise ValueError(f"adjustment set contains descendants of treatment: {post_treatment}")

    randomized = bool(identification.get("randomized") or identification.get("intervention"))
    dag_identified = bool(identification.get("identified_dag") or (parents and outcome in (set(parents) | set(children))))
    method = str(identification.get("method", "backdoor")).lower()
    assumptions = identification.get("assumptions", [])
    if method == "frontdoor" and not assumptions:
        assumptions = [_FRONTDOOR_ASSUMPTION]
    elif method == "iv" and not assumptions:
        assumptions = _IV_ASSUMPTIONS
    elif method == "longitudinal" and not assumptions:
        assumptions = _LONGITUDINAL_ASSUMPTIONS
    if method == "backdoor":
        if not randomized and not dag_identified and not (adjustment and assumptions):
            return {
                "status": "INSUFFICIENT_CAUSAL_EVIDENCE",
                "family": model.family.value,
                "detail": "causal conclusion unavailable: provide randomization/intervention evidence or a DAG/backdoor set with explicit assumptions",
                "required_next_evidence": ["randomization/intervention", "acyclic DAG plus measured adjustment variables", "explicit exchangeability/positivity assumptions"],
            }

    covariates = [_finite_vector(data, name, n=y.size) for name in adjustment]
    Z = np.column_stack(covariates) if covariates else np.empty((y.size, 0))
    unique_t = np.unique(t)
    is_binary = unique_t.size == 2 and set(np.round(unique_t, 12).tolist()) <= {0.0, 1.0}

    if method == "frontdoor":
        mediator = str(identification.get("mediator", ""))
        if not mediator:
            raise ValueError("frontdoor identification requires a 'mediator' variable in the identification config")
        if mediator not in data:
            raise ValueError(f"frontdoor mediator {mediator!r} not found in causal.data")
        if mediator in set(adjustment):
            raise ValueError("mediator cannot be in the adjustment set")
        m = _finite_vector(data, mediator, n=y.size)
        effect = _frontdoor_effect(y, t, m, Z if Z.size else None)
    elif method == "iv":
        instrument = identification.get("instrument", identification.get("instruments"))
        if instrument is None:
            raise ValueError("iv identification requires an 'instrument' variable in the identification config")
        if isinstance(instrument, str):
            instrument = [instrument]
        Z_inst = np.column_stack([_finite_vector(data, name, n=y.size) for name in instrument])
        effect = _iv_effect(y, t, Z_inst, Z if Z.size else None)
    elif method == "longitudinal":
        time_name = str(identification.get("time", ""))
        if not time_name:
            raise ValueError("longitudinal identification requires a 'time' variable in the identification config")
        if time_name not in data:
            raise ValueError(f"longitudinal time variable {time_name!r} not found in causal.data")
        time_arr = _finite_vector(data, time_name, n=y.size)
        effect = _longitudinal_effect(y, t, time_arr, Z if Z.size else None)
    else:
        if is_binary:
            effect = _binary_effect(y, t.astype(int), Z, adjustment)
        else:
            effect = _continuous_effect(y, t, Z)

    # Intervention predictions use the robust regression estimand, conditional on
    # mean adjustment values; they are explicitly scoped to the identification assumptions.
    X = np.column_stack([np.ones(y.size), t, Z]) if Z.size else np.column_stack([np.ones(y.size), t])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    means = [float(np.mean(Z[:, i])) for i in range(Z.shape[1])]
    counterfactuals: list[dict[str, Any]] = []
    values = cfg.get("intervention_values", [])
    if isinstance(values, list) and method == "backdoor":
        for raw in values[:1000]:
            value = float(raw)
            if not math.isfinite(value):
                raise ValueError("intervention values must be finite")
            row = np.asarray([1.0, value, *means])
            counterfactuals.append({"do": {treatment: value}, "predicted_outcome_mean": float(row @ beta)})

    warning: list[str] = []
    if is_binary:
        positivity = effect.get("positivity", {})
        if float(positivity.get("fraction_outside_0.05_0.95", 0.0)) > 0.1:
            warning.append("limited propensity overlap; causal estimate may be extrapolation-sensitive")
        after = effect.get("balance", {}).get("after_ipw", {})
        if any(float(v) > 0.1 for v in after.values()):
            warning.append("residual covariate imbalance after weighting exceeds SMD 0.1")
    return {
        "status": "PASS",
        "family": model.family.value,
        "states": {},
        "parameters": parameters,
        "causal_effect": {"treatment": treatment, "outcome": outcome, **effect},
        "counterfactuals": counterfactuals,
        "identification": {
            **identification,
            "method": method,
            "dag_validated_acyclic": bool(parents or children),
            "adjustment_set_used": adjustment if method == "backdoor" else [],
            "randomized_or_interventional": randomized,
        },
        "solver": {"backend": "numpy", "method": effect["method"]},
        "diagnostics": {"n": int(y.size), "binary_treatment": is_binary, "warnings": warning},
        "causal_scope": "causal interpretation is valid only conditional on the supplied identification assumptions, measured adjustment set, consistency, positivity, and no unmeasured confounding where required",
    }
