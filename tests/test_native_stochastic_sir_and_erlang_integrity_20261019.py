"""Real deterministic and stochastic epidemic/queue bounds, not proxy fits."""
from __future__ import annotations

import math
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize.tools import validate as v


@pytest.mark.parametrize("raw,answer", [(0,0.0),(1.5,1.5),("2.25",2.25)])
def test_numeric_gate_accepts_exact_finite_inputs(raw,answer):
    assert v._finite(raw,"parameter")==answer


@pytest.mark.parametrize("raw,error",[
    ("invalid","must be numeric"),(None,"must be numeric"),
    (float("inf"),"must be finite"),(float("nan"),"must be finite"),
])
def test_numeric_gate_refuses_unknown_and_nonfinite_evidence(raw,error):
    with pytest.raises(ValueError,match=error):
        v._finite(raw,"parameter")


@pytest.mark.parametrize("value,answer",[(0,0),(7,7),(7.0,7),("07",7)])
def test_exact_integer_gate_does_not_round_fractional_data(value,answer):
    assert v._exact_int(value,"size")==answer


@pytest.mark.parametrize("value,error",[
    (True,"not a boolean"),(1.5,"exact finite integer"),
    (float("inf"),"exact finite integer"),("garbled","must be an integer"),
])
def test_integer_gate_refuses_implicit_truncation(value,error):
    with pytest.raises(ValueError,match=error):
        v._exact_int(value,"size")


def test_integer_hard_minimum_and_maximum_are_real_gates():
    with pytest.raises(ValueError,match=">= 1"):
        v._exact_int(0,"size",minimum=1)
    with pytest.raises(ValueError,match="<= 4"):
        v._exact_int(5,"size",maximum=4)


@pytest.mark.parametrize("input_values,match",[
    ((-0.1,0.1,1,100,10),"beta must"),
    ((0.2,0,1,100,10),"gamma must"),
    ((0.2,0.1,101,100,10),"I0 must"),
    ((0.2,0.1,1,0,10),"N must"),
    ((0.2,0.1,1,100,0),"days must"),
    ((0.2,0.1,1,100,1000001),"days must"),
])
def test_sir_population_rates_and_time_horizon_are_validated(input_values,match):
    with pytest.raises(ValueError,match=match):
        v._validate_sir(*input_values)


def test_stochastic_population_limit_is_stricter_than_deterministic_limit():
    with pytest.raises(ValueError,match="N must"):
        v._validate_sir(0.3,0.1,1,1000001,30,stochastic=True)
    assert v._validate_sir(0.3,0.1,1,1000001,30,stochastic=False)[3]==1000001


def test_sir_vector_field_conserves_total_population():
    rhs=v.sir_rhs(0,[990.0,10.0,0.0],0.3,0.1,1000.0)
    assert sum(rhs)==pytest.approx(0.0,abs=1e-10)
    assert rhs[2]==pytest.approx(1.0)


@pytest.mark.parametrize("beta,gamma",[(0,0.1),(0.05,0.1),(0.1,0.1)])
def test_subcritical_final_size_theory_is_exact_zero(beta,gamma):
    assert v.final_size_theory(beta,gamma)==0.0


def test_supercritical_final_size_satisfies_implicit_physical_equation():
    result=v.final_size_theory(0.3,0.1)
    assert 0.9<result<1.0
    assert result==pytest.approx(1-math.exp(-3*result),abs=1e-9)


def test_real_sir_ode_is_finite_nonnegative_and_population_conserving():
    result=v.run_sir(0.3,0.1,10,1000,days=40)
    assert result.success
    assert result.y.shape[0]==3
    np.testing.assert_allclose(np.sum(result.y,axis=0),1000.0,atol=1e-5)
    assert np.all(result.y >= -1e-6)


def test_failed_native_ode_solver_does_not_report_a_valid_trajectory(monkeypatch):
    def refused(*args,**kwargs):
        return SimpleNamespace(success=False,message="numerical backend failed",y=np.ones((3,2)))
    monkeypatch.setattr(v,"solve_ivp",refused)
    with pytest.raises(RuntimeError,match="SIR solve failed"):
        v.run_sir(0.3,0.1,1,100,days=10)


def test_nonfinite_native_ode_solver_does_not_pass(monkeypatch):
    def nonfinite(*args,**kwargs):
        return SimpleNamespace(success=True,message="nonfinite",y=np.array([[float("nan")]]*3))
    monkeypatch.setattr(v,"solve_ivp",nonfinite)
    with pytest.raises(RuntimeError,match="SIR solve failed"):
        v.run_sir(0.3,0.1,1,100,days=10)


def test_reference_report_contains_measured_conservation_checks(capsys):
    args=SimpleNamespace(beta=0.3,gamma=0.1,I0=10,N=1000,days=180,sweep=False,plot=None)
    assert v.report_sir(args)==0
    stdout=capsys.readouterr().out
    assert "population_conserved" in stdout
    assert "compartments_nonnegative" in stdout
    assert "Theory match" in stdout


def test_zero_initial_infectious_population_never_creates_events():
    result=v.gillespie_sir_once(0.3,0.1,0,1000,rng=np.random.default_rng(17))
    assert result["peak_I"]==0
    assert result["events"]==0
    assert result["final_R"]==0


def test_gillespie_trajectory_is_reproducible_under_frozen_seed():
    first=v.gillespie_sir_once(0.3,0.1,1,1000,rng=np.random.default_rng(5))
    second=v.gillespie_sir_once(0.3,0.1,1,1000,rng=np.random.default_rng(5))
    assert first==second
    assert 0<=first["final_R"]<=1000
    assert 0<=first["events"]<=2000


@pytest.mark.parametrize("beta,gamma,I0,expected",[
    (0.0,0.1,1,1.0), (0.3,0.1,0,1.0),
    (0.1,0.1,1,0.5), (0.1,0.1,4,0.2),
])
def test_jump_chain_fadeout_probability_has_exact_boundary_values(beta,gamma,I0,expected):
    assert v._fadeout_probability(beta,gamma,I0)==pytest.approx(expected)


def test_fadeout_probability_stays_in_physical_interval_for_extreme_ratios():
    for beta,gamma in [(0.3,0.1),(0.1,0.3),(1e-300,1.0),(1.0,1e-300)]:
        p=v._fadeout_probability(beta,gamma,5)
        assert 0<=p<=1


@pytest.mark.parametrize("lam,mu,c,expected",[
    (0.0,10.0,2,(0.0,0.0)),
    (60.0,20.0,2,(1.0,float("inf"))),
])
def test_erlang_c_zero_arrival_or_unstable_capacity_is_explicit(lam,mu,c,expected):
    result=v.erlang_c(lam,mu,c)
    assert result==expected


def test_real_erlang_c_returns_finite_wait_for_stable_capacity():
    p,wait=v.erlang_c(60,20,5)
    assert 0<p<1
    assert wait>0
    assert math.isfinite(wait)


@pytest.mark.parametrize("lam,mu,staff",[
    (-1,10,1),(1,0,1),(1,10,0),(1,10,2.5),
])
def test_invalid_staffing_inputs_never_report_a_feasible_queue(lam,mu,staff):
    with pytest.raises(ValueError):
        v.erlang_c(lam,mu,staff)


def test_queue_report_finds_minimum_staff_under_real_erlang_model(capsys):
    args=SimpleNamespace(lam=60.0,mu=20.0,target_wait=3.0,sweep=False)
    assert v.report_queue(args)==0
    stdout=capsys.readouterr().out
    assert "minimal staffing c*" in stdout
    assert "target_met_at_c*" in stdout


def test_queue_report_rejects_impossible_zero_wait_target(capsys):
    args=SimpleNamespace(lam=60.0,mu=20.0,target_wait=0.0,sweep=False)
    assert v.report_queue(args)==1
    assert "No staffing level meets" in capsys.readouterr().out


def test_queue_staffing_sweep_is_real_analytic_computation(capsys):
    args=SimpleNamespace(lam=60.0,mu=20.0,target_wait=3.0,sweep=True)
    assert v.report_queue(args)==0
    assert "sensitivity sweep" in capsys.readouterr().out


def test_validate_cli_dispatches_real_sir_model(monkeypatch,capsys):
    monkeypatch.setattr(sys,"argv",[
        "axiomize-validate","--model","sir","--N","1000","--I0","10",
        "--days","180",
    ])
    with pytest.raises(SystemExit) as stop:
        v.main()
    assert stop.value.code==0
    assert "SIR validation" in capsys.readouterr().out


def test_validate_cli_refuses_invalid_physical_rates(monkeypatch):
    monkeypatch.setattr(sys,"argv",[
        "axiomize-validate","--model","sir","--gamma","0"
    ])
    with pytest.raises(SystemExit) as stop:
        v.main()
    assert stop.value.code==2
