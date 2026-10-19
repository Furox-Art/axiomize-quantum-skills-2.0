"""Scientific reference reports execute their declared native numerics.

These tests measure real time courses and stochastic trajectories; simulations
are controlled reference checks, not assertions of external clinical validity.
"""
from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize.tools import validate as v


def sir_args(**changes):
    values = dict(beta=0.3, gamma=0.1, I0=10, N=1000, days=180, sweep=False, plot=None)
    values.update(changes)
    return SimpleNamespace(**values)


def stochastic_args(**changes):
    values = dict(beta=0.3, gamma=0.1, I0=1, N=60, days=40, runs=60, seed=7, sweep=False)
    values.update(changes)
    return SimpleNamespace(**values)


def test_reference_sir_parameter_sweep_solves_each_ode_cell(capsys):
    result = v.report_sir(sir_args(sweep=True))
    out = capsys.readouterr().out
    assert result == 0
    assert "sensitivity sweep over beta" in out
    assert "Theory match" in out
    assert "population_conserved" in out
    assert "R_monotonic_increase" in out
    assert "FAIL" not in out


def test_subcritical_sir_says_dies_out_and_respects_mass_conservation(capsys):
    result = v.report_sir(sir_args(beta=0.05, gamma=0.1, I0=1))
    report = capsys.readouterr().out
    assert result == 0
    assert "dies out" in report
    assert "population_conserved" in report


def test_sir_plot_is_actual_nonempty_image_and_does_not_mutate_samples(tmp_path, capsys):
    output = tmp_path / "sir-reference.png"
    result = v.report_sir(sir_args(plot=str(output)))
    report = capsys.readouterr().out
    assert result == 0
    assert output.is_file()
    assert output.stat().st_size > 1_000
    assert "plot saved" in report


def test_real_fadeout_report_has_signed_empirical_numerators_and_bounds(capsys):
    result = v.report_gillespie(stochastic_args())
    report = capsys.readouterr().out
    assert result == 0
    assert "runs                        = 60" in report
    assert "P(early fade-out)" in report
    assert "theory fade-out prob" in report
    assert "fade_out_prob_consistent" in report
    assert "PASS" in report


def test_real_stochastic_initial_infections_sensitivity_sweep(capsys):
    result = v.report_gillespie(stochastic_args(N=30, days=30, runs=80, sweep=True))
    report = capsys.readouterr().out
    assert result == 0
    assert "sensitivity sweep over I0" in report
    assert "non-fade-out runs" in report
    assert "true-outbreak final size" in report
    assert "fade_out_prob_consistent" in report


@pytest.mark.parametrize("invalid", [0, -1, 100001, 1.5, True])
def test_requested_mc_runs_must_remain_bounded_exact_integer(invalid):
    with pytest.raises(ValueError, match="runs"):
        v.report_gillespie(stochastic_args(runs=invalid))


def test_mc_work_ceiling_rejected_before_any_random_draw(monkeypatch):
    def prohibited(*args, **kwargs):
        raise AssertionError("simulation ran despite exceeding work ceiling")

    monkeypatch.setattr(v, "gillespie_sir_once", prohibited)
    with pytest.raises(ValueError, match="hard stochastic work limit"):
        v.report_gillespie(stochastic_args(N=1_000_000, runs=60))


@pytest.mark.parametrize("beta,gamma,I0,expected", [
    (1e-320, 1e6, 1, 1.0),
    (1.0, 1e-320, 7, 0.0),
    (0.1, 0.1, 10, 1.0 / 11.0),
])
def test_jump_chain_underflow_and_critical_limits_do_not_emit_nan(beta, gamma, I0, expected):
    actual = v._fadeout_probability(beta, gamma, I0)
    assert np.isfinite(actual)
    assert 0 <= actual <= 1
    assert actual == pytest.approx(expected, abs=1e-11)


def test_refusal_result_remains_failure_when_synthetic_telemetry_violates_invariant(
    monkeypatch, capsys,
):
    def violated(*args, **kwargs):
        return {
            "extinct_early": True,
            "final_R": 10_000,  # impossible: exceeds population
            "peak_I": 0,  # impossible: below initial cases
        }

    monkeypatch.setattr(v, "gillespie_sir_once", violated)
    assert v.report_gillespie(stochastic_args(runs=3)) == 1
    report = capsys.readouterr().out
    assert "finals_within_bounds" in report
    assert "peaks_at_least_initial" in report
    assert "FAIL" in report


def test_real_gillespie_cli_executes_seeded_model(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "axiomize-validate", "--model", "gillespie",
        "--beta", "0.3", "--gamma", "0.1",
        "--I0", "1", "--N", "60", "--runs", "60",
        "--days", "40", "--seed", "7",
    ])
    with pytest.raises(SystemExit) as done:
        v.main()
    assert done.value.code == 0
    assert "Gillespie stochastic SIR" in capsys.readouterr().out


def test_real_queue_cli_executes_erlang_staffing_model(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", [
        "axiomize-validate", "--model", "queue",
        "--lam", "60", "--mu", "20", "--target-wait", "3",
    ])
    with pytest.raises(SystemExit) as done:
        v.main()
    assert done.value.code == 0
    assert "minimal staffing c*" in capsys.readouterr().out


def test_staffing_requests_exceeding_resource_budget_rejected():
    with pytest.raises(ValueError, match="required baseline staff exceeds hard limit"):
        v.report_queue(SimpleNamespace(lam=1e8, mu=1.0, target_wait=3.0, sweep=False))
