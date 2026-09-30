"""Tests for advanced_diagnostics: stopping criteria, uncertainty propagation, bifurcation scan.

This module had 4% coverage despite being the home of the project's approval-gated
Monte-Carlo propagation and its bifurcation scan, both of which are advertised
capabilities. The emphasis here is on the contract these functions promise:
explicit, structured evidence, no silently invented criteria, and heavy work that
refuses to run without approval.
"""
from __future__ import annotations

import numpy as np
import pytest

from axiomize import advanced_diagnostics as diag
from axiomize.model_ir import ModelFamily, ModelIR, SolverSpec


def _sir_model() -> ModelIR:
    return ModelIR.from_dict(
        {
            "schema_version": "1.0",
            "domain": "general",
            "name": "sir",
            "family": "ode",
            "independent_variable": "t",
            "variables": [
                {"name": "S", "role": "state", "initial": 990.0},
                {"name": "I", "role": "state", "initial": 10.0},
            ],
            "parameters": [
                {"name": "beta", "value": 0.3},
                {"name": "gamma", "value": 0.1},
            ],
            "equations": [
                {"target": "S", "expression": "-beta*S*I/1000", "kind": "derivative"},
                {"target": "I", "expression": "beta*S*I/1000 - gamma*I", "kind": "derivative"},
            ],
        }
    )


def _pde_model() -> ModelIR:
    # Built through the constructor rather than from_dict: from_dict runs
    # validate_structure(), which rejects the intentionally empty variable and
    # equation lists. This mirrors tests/test_pde_solver_selection.py.
    return ModelIR(
        name="diffusion",
        domain="general",
        family=ModelFamily.PDE,
        variables=[],
        parameters=[],
        equations=[],
        solver=SolverSpec(),
    )


def _criteria(result: dict) -> dict[str, dict]:
    return {check["criterion"]: check for check in result["checks"]}

# ------------------------------------------------------------- stopping_decision
def test_stopping_rejects_an_invalid_patience() -> None:
    with pytest.raises(ValueError, match="patience must be at least 1"):
        diag.stopping_decision([1.0, 0.5, 0.2], patience=0)


def test_stopping_rejects_negative_tolerances() -> None:
    with pytest.raises(ValueError, match="tolerances must be non-negative"):
        diag.stopping_decision([1.0, 0.5], relative_tolerance=-1e-3)
    with pytest.raises(ValueError, match="tolerances must be non-negative"):
        diag.stopping_decision([1.0, 0.5], absolute_tolerance=-1.0)


def test_stopping_rejects_non_finite_or_non_1d_history() -> None:
    with pytest.raises(ValueError, match="finite 1D sequence"):
        diag.stopping_decision([1.0, float("nan")])
    with pytest.raises(ValueError, match="finite 1D sequence"):
        diag.stopping_decision([[1.0, 2.0]])


def test_stopping_reports_insufficient_data_instead_of_guessing() -> None:
    result = diag.stopping_decision([1.0, 0.5], patience=3)
    check = _criteria(result)["incremental_improvement"]
    assert check["status"] == "INSUFFICIENT_DATA"
    assert check["required_history"] == 4
    assert check["available_history"] == 2
    assert result["decision"] == "CONTINUE"


def test_stopping_stops_once_changes_stay_inside_tolerance() -> None:
    result = diag.stopping_decision([10.0, 10.0, 10.0, 10.0001, 10.00005, 10.00002])
    check = _criteria(result)["incremental_improvement"]
    assert check["status"] == "STOP"
    assert result["decision"] == "STOP"
    assert result["reasons"] == ["incremental_improvement"]
    assert check["max_recent_change"] <= check["max_recent_threshold"]


def test_stopping_keeps_going_while_the_objective_is_still_moving() -> None:
    result = diag.stopping_decision([100.0, 50.0, 25.0, 12.0, 6.0, 3.0])
    assert _criteria(result)["incremental_improvement"]["status"] == "CONTINUE"
    assert result["decision"] == "CONTINUE"
    assert result["reasons"] == []


def test_absolute_tolerance_alone_can_stop_a_flat_objective() -> None:
    history = [1e-12, 5e-13, 2e-13, 1e-13, 5e-14]
    result = diag.stopping_decision(history, relative_tolerance=0.0, absolute_tolerance=1e-12)
    assert result["decision"] == "STOP"


def test_stopping_requires_budget_used_when_a_limit_is_given() -> None:
    with pytest.raises(ValueError, match="budget_used is required"):
        diag.stopping_decision([1.0, 1.0, 1.0, 1.0], budget_limit=10.0)


def test_stopping_rejects_a_non_positive_budget_limit() -> None:
    with pytest.raises(ValueError, match="budget_limit must be positive"):
        diag.stopping_decision([1.0, 1.0, 1.0, 1.0], budget_used=1.0, budget_limit=0.0)


def test_stopping_stops_when_the_budget_is_spent_and_not_before() -> None:
    history = [10.0, 5.0, 2.0, 1.0]
    running = diag.stopping_decision(history, budget_used=4.0, budget_limit=10.0)
    spent = diag.stopping_decision(history, budget_used=10.0, budget_limit=10.0)
    over = diag.stopping_decision(history, budget_used=11.0, budget_limit=10.0)

    assert running["decision"] == "CONTINUE"
    assert _criteria(running)["compute_budget"]["fraction"] == pytest.approx(0.4)
    assert spent["decision"] == "STOP"
    assert over["decision"] == "STOP"
    assert "compute_budget" in spent["reasons"]


def test_stopping_requires_uncertainty_when_a_target_is_given() -> None:
    with pytest.raises(ValueError, match="uncertainty is required"):
        diag.stopping_decision([1.0, 1.0, 1.0, 1.0], uncertainty_target=0.1)


def test_stopping_rejects_a_negative_uncertainty_target() -> None:
    with pytest.raises(ValueError, match="uncertainty_target must be non-negative"):
        diag.stopping_decision([1.0] * 4, uncertainty=0.1, uncertainty_target=-1.0)


def test_stopping_stops_once_uncertainty_is_inside_the_target() -> None:
    history = [10.0, 5.0, 2.0, 1.0]
    wide = diag.stopping_decision(history, uncertainty=0.5, uncertainty_target=0.1)
    tight = diag.stopping_decision(history, uncertainty=0.05, uncertainty_target=0.1)

    assert wide["decision"] == "CONTINUE"
    assert tight["decision"] == "STOP"
    assert "uncertainty_target" in tight["reasons"]


def test_stopping_is_an_or_across_configured_criteria() -> None:
    """Only explicitly configured criteria may fire; none may be invented."""
    history = [10.0, 5.0, 2.0, 1.0]
    result = diag.stopping_decision(
        history, budget_used=99.0, budget_limit=10.0, uncertainty=0.001, uncertainty_target=0.01
    )
    assert result["decision"] == "STOP"
    assert set(result["reasons"]) == {"compute_budget", "uncertainty_target"}
    assert "incremental_improvement" not in result["reasons"]
    assert result["rule"] == "stop when any explicitly configured criterion is satisfied"


def test_stopping_never_invents_criteria_when_nothing_is_configured() -> None:
    result = diag.stopping_decision([10.0, 1.0, 0.5])
    assert [check["criterion"] for check in result["checks"]] == ["incremental_improvement"]


# ------------------------------------------------------------- _sample_parameter
def test_sample_parameter_requires_std_for_a_normal_spec() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="requires std"):
        diag._sample_parameter(rng, {"distribution": "normal", "mean": 1.0}, 1.0, None, 5)


def test_sample_parameter_rejects_a_negative_normal_std() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="std must be non-negative"):
        diag._sample_parameter(rng, {"distribution": "normal", "std": -1.0}, 1.0, None, 5)


def test_sample_parameter_normal_uses_the_spec_mean_and_size() -> None:
    rng = np.random.default_rng(0)
    values = diag._sample_parameter(rng, {"distribution": "normal", "mean": 2.0, "std": 0.1}, 9.0, None, 500)
    assert values.shape == (500,)
    assert values.mean() == pytest.approx(2.0, abs=0.05)


def test_sample_parameter_uniform_requires_both_ends() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="requires low and high"):
        diag._sample_parameter(rng, {"distribution": "uniform", "low": 0.0}, 0.0, None, 5)
    with pytest.raises(ValueError, match="requires low and high"):
        diag._sample_parameter(rng, {"distribution": "uniform", "high": 1.0}, 0.0, None, 5)


def test_sample_parameter_uniform_rejects_an_inverted_range() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="high must exceed low"):
        diag._sample_parameter(rng, {"distribution": "uniform", "low": 1.0, "high": 1.0}, 0.0, None, 5)


def test_sample_parameter_uniform_stays_inside_its_range() -> None:
    rng = np.random.default_rng(0)
    values = diag._sample_parameter(rng, {"distribution": "uniform", "low": 3.0, "high": 4.0}, 0.0, None, 300)
    assert values.min() >= 3.0 and values.max() <= 4.0


def test_sample_parameter_fixed_is_deterministic() -> None:
    rng = np.random.default_rng(0)
    explicit = diag._sample_parameter(rng, {"distribution": "fixed", "value": 7.0}, 0.0, None, 4)
    implicit = diag._sample_parameter(rng, {"distribution": "fixed"}, 5.0, None, 4)
    assert np.all(explicit == 7.0)
    assert np.all(implicit == 5.0)


def test_sample_parameter_accepts_kind_as_an_alias_for_distribution() -> None:
    rng = np.random.default_rng(0)
    values = diag._sample_parameter(rng, {"kind": "fixed", "value": 2.0}, 0.0, None, 3)
    assert np.all(values == 2.0)


def test_sample_parameter_rejects_an_unknown_distribution() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="unsupported uncertainty distribution"):
        diag._sample_parameter(rng, {"distribution": "poisson"}, 1.0, None, 5)


def test_sample_parameter_clamps_to_parameter_bounds() -> None:
    rng = np.random.default_rng(0)
    spec = {"distribution": "normal", "mean": 0.0, "std": 5.0}
    clamped = diag._sample_parameter(rng, spec, 0.0, (-1.0, 1.0), 2000)
    assert clamped.min() >= -1.0 and clamped.max() <= 1.0


def test_sample_parameter_honours_one_sided_bounds() -> None:
    rng = np.random.default_rng(0)
    spec = {"distribution": "uniform", "low": -10.0, "high": 10.0}
    lower_only = diag._sample_parameter(rng, spec, 0.0, (0.0, None), 2000)
    upper_only = diag._sample_parameter(rng, spec, 0.0, (None, 0.0), 2000)
    assert lower_only.min() >= 0.0
    assert upper_only.max() <= 0.0


# --------------------------------------------------- propagate_parameter_uncertainty
def test_uncertainty_routes_unsupported_families_to_a_tool() -> None:
    result = diag.propagate_parameter_uncertainty(
        _pde_model(), t_span=(0, 1), parameter_uncertainty={}, approve_heavy=True
    )
    assert result["status"] == "TOOL_ROUTE_REQUIRED"
    assert result["family"] == "pde"
    assert "requires a native executor for this family" in result["detail"]


def test_uncertainty_refuses_unsafe_sample_counts() -> None:
    model = _sir_model()
    with pytest.raises(ValueError, match="samples must be at least 2"):
        diag.propagate_parameter_uncertainty(model, t_span=(0, 1), parameter_uncertainty={}, samples=1)
    with pytest.raises(ValueError, match="hard safety limit"):
        diag.propagate_parameter_uncertainty(
            model, t_span=(0, 1), parameter_uncertainty={}, samples=100_001
        )


def test_uncertainty_rejects_quantiles_outside_the_unit_interval() -> None:
    model = _sir_model()
    with pytest.raises(ValueError, match=r"probabilities in \[0, 1\]"):
        diag.propagate_parameter_uncertainty(
            model, t_span=(0, 1), parameter_uncertainty={}, quantiles=(0.1, 1.5)
        )
    with pytest.raises(ValueError, match=r"probabilities in \[0, 1\]"):
        diag.propagate_parameter_uncertainty(
            model, t_span=(0, 1), parameter_uncertainty={}, quantiles=()
        )


def test_uncertainty_is_approval_gated() -> None:
    result = diag.propagate_parameter_uncertainty(
        _sir_model(), t_span=(0, 5), parameter_uncertainty={}, samples=4
    )
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["cost"]
    assert "approve explicitly" in result["detail"]


def test_uncertainty_rejects_specs_for_unknown_parameters() -> None:
    with pytest.raises(ValueError, match="unknown parameters"):
        diag.propagate_parameter_uncertainty(
            _sir_model(),
            t_span=(0, 5),
            parameter_uncertainty={"not_a_parameter": {"distribution": "fixed", "value": 1.0}},
            samples=4,
            approve_heavy=True,
        )


def test_uncertainty_propagation_reports_quantiles_and_sampled_parameters() -> None:
    result = diag.propagate_parameter_uncertainty(
        _sir_model(),
        t_span=(0, 10),
        parameter_uncertainty={"beta": {"distribution": "uniform", "low": 0.25, "high": 0.35}},
        points=15,
        samples=8,
        seed=3,
        approve_heavy=True,
    )
    assert result["status"] == "PASS"
    assert result["method"] == "monte_carlo_parameter_propagation"
    assert result["requested_samples"] == 8
    assert result["successful_samples"] + result["failed_samples"] == 8
    assert result["success_fraction"] == pytest.approx(result["successful_samples"] / 8)
    assert result["seed"] == 3

    summary = result["parameter_draw_summary"]
    assert set(summary) == {"beta", "gamma"}
    assert 0.25 <= summary["beta"]["mean"] <= 0.35
    # gamma had no spec, so it must be held fixed at its baseline value.
    assert summary["gamma"]["std"] == pytest.approx(0.0, abs=1e-12)

    states = result["states"]
    assert states, "at least one state must be summarised"
    for summary_out in states.values():
        assert len(summary_out["mean"]) == 15
        assert len(summary_out["std"]) == 15
        assert set(summary_out["quantiles"]) == {"q0.025", "q0.5", "q0.975"}


def test_uncertainty_propagation_is_reproducible_for_a_fixed_seed() -> None:
    kwargs = {
        "t_span": (0, 6),
        "parameter_uncertainty": {"beta": {"distribution": "normal", "mean": 0.3, "std": 0.02}},
        "points": 10,
        "samples": 6,
        "seed": 11,
        "approve_heavy": True,
    }
    first = diag.propagate_parameter_uncertainty(_sir_model(), **kwargs)
    second = diag.propagate_parameter_uncertainty(_sir_model(), **kwargs)
    assert first["states"] == second["states"]
    assert first["parameter_draw_summary"] == second["parameter_draw_summary"]


def test_uncertainty_quantile_keys_follow_the_requested_probabilities() -> None:
    result = diag.propagate_parameter_uncertainty(
        _sir_model(),
        t_span=(0, 5),
        parameter_uncertainty={},
        points=8,
        samples=5,
        quantiles=(0.1, 0.9),
        approve_heavy=True,
    )
    state = next(iter(result["states"].values()))
    assert set(state["quantiles"]) == {"q0.1", "q0.9"}


# ------------------------------------------------------------- bifurcation_scan
def test_bifurcation_routes_non_ode_families_to_a_tool() -> None:
    result = diag.bifurcation_scan(_pde_model(), parameter="alpha", values=[1.0, 2.0], approve_heavy=True)
    assert result["status"] == "TOOL_ROUTE_REQUIRED"
    assert result["family"] == "pde"


def test_bifurcation_requires_at_least_two_parameter_values() -> None:
    with pytest.raises(ValueError, match="at least two parameter values"):
        diag.bifurcation_scan(_sir_model(), parameter="beta", values=[0.2])


def test_bifurcation_is_approval_gated() -> None:
    result = diag.bifurcation_scan(_sir_model(), parameter="beta", values=[0.2, 0.4])
    assert result["status"] == "APPROVAL_REQUIRED"
    assert result["cost"]
    assert "explicit approval" in result["detail"]


def test_bifurcation_rejects_an_unknown_parameter() -> None:
    with pytest.raises(ValueError, match="unknown parameter"):
        diag.bifurcation_scan(
            _sir_model(), parameter="nope", values=[0.2, 0.4], approve_heavy=True
        )


def test_bifurcation_returns_one_row_per_value_with_stability_evidence() -> None:
    values = [0.1, 0.3, 0.6]
    result = diag.bifurcation_scan(_sir_model(), parameter="beta", values=values, approve_heavy=True)

    assert result["status"] == "PASS"
    assert result["parameter"] == "beta"
    assert [row["parameter_value"] for row in result["rows"]] == values
    for row in result["rows"]:
        assert row["status"] == "PASS"
        assert set(row["equilibrium"]) == {"S", "I"}
        assert "max_real_part" in row["stability"]
    assert "not proof of a specific bifurcation type" in result["interpretation"]
    assert isinstance(result["transition_candidates"], list)


def test_bifurcation_captures_per_value_failures_without_aborting_the_scan() -> None:
    result = diag.bifurcation_scan(
        _sir_model(),
        parameter="beta",
        values=[0.2, 0.4],
        equilibrium_guess={"S": -5.0, "I": -5.0},
        approve_heavy=True,
    )
    rows = result["rows"]
    assert len(rows) == 2
    failed = [row for row in rows if row["status"] == "FAIL"]
    if failed:
        assert "error" in failed[0]
        assert failed[0]["error"].split(":")[0] in {"RuntimeError", "ValueError", "TypeError", "KeyError"}
    assert result["status"] == "FAIL" or result["status"] == "PASS"


def test_bifurcation_transition_candidates_only_span_adjacent_successful_rows() -> None:
    result = diag.bifurcation_scan(
        _sir_model(), parameter="gamma", values=[0.05, 0.1, 0.2], approve_heavy=True
    )
    candidates = result["transition_candidates"]
    successful_values = [row["parameter_value"] for row in result["rows"] if row["status"] == "PASS"]
    for candidate in candidates:
        left, right = candidate["between"]
        assert left in successful_values and right in successful_values
        assert abs(successful_values.index(right) - successful_values.index(left)) == 1
        assert candidate["classification"] == "local_stability_transition_candidate"
        assert len(candidate["max_real_part"]) == 2
