"""Round-2 coverage hardening for scientific model kernels.

Covers estimator validation/fallbacks, ablation reporting, network epidemic
guards, Bayesian likelihood/replicate branches, FTCS diffusion guards,
numerical-verification-v2 studies, standards export adapters, advanced
diagnostics equilibrium initialization and causal estimator branches.
"""

from __future__ import annotations

import json
import math
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize import advanced_diagnostics as diag
from axiomize import numerical_verification_v2 as nv2
from axiomize import standards_export
from axiomize.causal_engine import _logistic_irls, estimate_causal_model
from axiomize.fitting import estimator
from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.network import epidemic
from axiomize.pde import diffusion
from axiomize.reasoning import ablation
from axiomize.bayesian import likelihoods


# --------------------------------------------------------------------------- #
# fitting.estimator
# --------------------------------------------------------------------------- #

def _xy():
    t = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([1.0, 2.0, 3.0, 5.0])
    return t, y


def test_coerce_xy_rejects_2d_mismatched_and_short_inputs():
    with pytest.raises(ValueError, match="one-dimensional"):
        estimator._coerce_xy(np.zeros((2, 2)), np.zeros(2))
    with pytest.raises(ValueError, match="same length"):
        estimator._coerce_xy(np.zeros(2), np.zeros(3))
    with pytest.raises(ValueError, match="at least two"):
        estimator._coerce_xy(np.zeros(1), np.zeros(1))


def test_validate_fit_spec_rejects_each_invalid_spec():
    t = np.array([0.0, 1.0, 2.0, 3.0])
    with pytest.raises(ValueError, match="p0 must contain"):
        estimator._validate_fit_spec(t, [], [], None)
    with pytest.raises(ValueError, match="same length as p0"):
        estimator._validate_fit_spec(t, [1.0], ["a", "b"], None)
    with pytest.raises(ValueError, match="must be unique"):
        estimator._validate_fit_spec(t, [1.0, 2.0], ["a", "a"], None)
    with pytest.raises(ValueError, match="finite"):
        estimator._validate_fit_spec(t, [float("inf")], ["a"], None)
    with pytest.raises(ValueError, match="at least the number of parameters"):
        estimator._validate_fit_spec(np.array([0.0, 1.0]), [1.0, 1.0, 1.0],
                                     ["a", "b", "c"], None)
    with pytest.raises(ValueError, match="lower/upper arrays"):
        estimator._validate_fit_spec(t, [1.0], ["a"], ([0.0], [1.0, 2.0]))
    with pytest.raises(ValueError, match="must not contain NaN"):
        estimator._validate_fit_spec(t, [1.0], ["a"], ([float("nan")], [1.0]))
    with pytest.raises(ValueError, match="lower bound must be <="):
        estimator._validate_fit_spec(t, [1.0], ["a"], ([2.0], [1.0]))
    with pytest.raises(ValueError, match="must lie within bounds"):
        estimator._validate_fit_spec(t, [5.0], ["a"], ([0.0], [1.0]))


def test_lag1_autocorrelation_degenerate_inputs():
    assert estimator._lag1_autocorrelation(np.array([1.0, 2.0])) == 0.0
    assert estimator._lag1_autocorrelation(np.array([np.nan, 1.0, 2.0])) == 0.0
    assert estimator._lag1_autocorrelation(np.array([1.0, 1.0, 1.0])) == 0.0


def _linear_model(tt, a):
    return a * np.asarray(tt, dtype=float)


def test_fit_curve_falls_back_when_optimizer_raises(monkeypatch):
    import scipy.optimize

    def explode(*args, **kwargs):
        raise RuntimeError("optimizer failed")

    monkeypatch.setattr(scipy.optimize, "curve_fit", explode)
    t, y = _xy()
    result = estimator.fit_curve(_linear_model, t, y, [1.0], ["a"])
    assert result.success is False
    assert result.params["a"][0] == 1.0
    assert math.isinf(result.params["a"][1])
    assert math.isfinite(result.rmse)
    assert result.method == "bounded_least_squares"


def test_fit_curve_falls_back_when_model_rejects_parameters(monkeypatch):
    import scipy.optimize

    def explode(*args, **kwargs):
        raise ValueError("no fit")

    def model(tt, a):
        raise ValueError("model cannot evaluate")

    monkeypatch.setattr(scipy.optimize, "curve_fit", explode)
    t, y = _xy()
    result = estimator.fit_curve(model, t, y, [1.0], ["a"])
    assert result.success is False
    assert math.isinf(result.rmse)
    assert math.isinf(result.aic)


def test_fit_curve_rejects_malformed_fitted_shape(monkeypatch):
    import scipy.optimize

    monkeypatch.setattr(scipy.optimize, "curve_fit",
                        lambda *args, **kwargs: (np.array([1.0]), np.eye(1)))
    t, y = _xy()
    result = estimator.fit_curve(lambda tt, a: np.ones(2), t, y, [1.0], ["a"])
    assert result.success is False
    assert math.isinf(result.bic)
    assert result.resid_autocorr == 0.0


def test_fit_sir_curve_rejects_invalid_population():
    with pytest.raises(ValueError, match="N must be finite and positive"):
        estimator.fit_sir_curve(np.array([0.0, 1.0]), np.array([1.0, 2.0]), 0.0, 0.0)


def test_compare_fits_reports_all_failed():
    failed = estimator.FitResult(params={}, rmse=math.inf, aic=math.inf, bic=math.inf,
                                 resid_autocorr=0.0, success=False,
                                 method="bounded_least_squares", n=4, k=1)
    assert estimator.compare_fits({"a": failed}) == {
        "ranking": [], "best": None, "reason": "all fits failed"}


# --------------------------------------------------------------------------- #
# reasoning.ablation
# --------------------------------------------------------------------------- #

def test_signals_observe_applies_regime_shift():
    signals = ablation._Signals(qualities=np.array([0.2, 0.3]), truth=1, shift_round=5)
    shifted = signals.observe(np.random.default_rng(0), 1, 5)
    early = signals.observe(np.random.default_rng(0), 1, 4)
    assert 0.0 <= shifted <= 1.0
    assert 0.0 <= early <= 1.0
    # The surged mean (_SHIFT[1]) is far above the pre-shift quality, so the same
    # seeded noise cannot drag the early draw above the shifted draw here.
    assert shifted > early


def _sweep_payload(all_fail=False):
    hard = {
        "0.50": {"premature_wrong_rate": 0.5 if not all_fail else 0.5, "accuracy": 0.99},
        "0.60": {"premature_wrong_rate": 0.0, "accuracy": 0.99},
    }
    if all_fail:
        hard["0.60"] = {"premature_wrong_rate": 0.5, "accuracy": 0.99}
    easy = {"0.50": {"mean_rounds": 5.0}, "0.60": {"mean_rounds": 3.0}}
    return {"grid": ["0.50", "0.60"], "default": "0.50", "table": {"hard": hard, "easy": easy}}


def test_recommend_threshold_skips_unsafe_and_picks_earliest_safe():
    best, why = ablation.recommend_threshold(_sweep_payload())
    assert best == 0.60
    assert "earliest safe exits" in why


def test_recommend_threshold_falls_back_when_no_member_is_safe():
    best, why = ablation.recommend_threshold(_sweep_payload(all_fail=True))
    assert best == ablation.DEFAULT_THRESHOLDS.collapse_score
    assert "no grid member met the safety gate" in why


def test_ablation_main_reference_writes_report_and_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ablation, "run_ablation", lambda seed, trials: {"seed": seed})
    monkeypatch.setattr(ablation, "render_report", lambda results: "# report\n")
    report = tmp_path / "report.md"
    raw = tmp_path / "raw.json"
    monkeypatch.setattr(sys, "argv", ["ablation", "--mode", "reference", "--trials", "2",
                                      "--report-out", str(report), "--json-out", str(raw)])
    ablation.main()
    out = capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == "# report\n"
    assert json.loads(raw.read_text(encoding="utf-8"))["seed"] == 20260927
    assert "ablation report written" in out


def test_ablation_main_sweep_prints_recommendation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(ablation, "sweep_collapse_thresholds",
                        lambda seed, trials: {"seed": seed})
    monkeypatch.setattr(ablation, "render_sweep_report", lambda results: "# sweep\n")
    monkeypatch.setattr(ablation, "recommend_threshold", lambda results: (0.7, "safe"))
    report = tmp_path / "sweep.md"
    monkeypatch.setattr(sys, "argv", ["ablation", "--mode", "sweep",
                                      "--report-out", str(report)])
    ablation.main()
    out = capsys.readouterr().out
    assert report.read_text(encoding="utf-8") == "# sweep\n"
    assert "sweep recommendation: collapse_score=0.70 (safe)" in out


def test_ablation_main_uses_default_report_destination(tmp_path, monkeypatch, capsys):
    here = tmp_path / "a" / "b" / "c" / "d" / "ablation.py"
    here.parent.mkdir(parents=True)
    monkeypatch.setattr(ablation, "__file__", str(here))
    monkeypatch.setattr(ablation, "run_ablation", lambda seed, trials: {"seed": seed})
    monkeypatch.setattr(ablation, "render_report", lambda results: "# default\n")
    monkeypatch.setattr(sys, "argv", ["ablation", "--mode", "reference"])
    ablation.main()
    expected = tmp_path / "a" / "benchmarks" / "reports" / "reasoning-ablation.md"
    assert expected.read_text(encoding="utf-8") == "# default\n"
    assert "ablation report written" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# network.epidemic
# --------------------------------------------------------------------------- #

def test_probability_rejects_non_numeric_and_out_of_range():
    with pytest.raises(ValueError, match="must be numeric"):
        epidemic._probability("not-a-number", name="p")
    with pytest.raises(ValueError, match="finite and in"):
        epidemic._probability(float("nan"), name="p")
    with pytest.raises(ValueError, match="finite and in"):
        epidemic._probability(1.5, name="p")


def test_build_er_graph_rejects_dense_work(monkeypatch):
    monkeypatch.setattr(epidemic, "MAX_NETWORK_EDGES", 0)
    with pytest.raises(ValueError, match="exceeding hard limit"):
        epidemic.build_er_graph(3, 0.5)


def test_graph_size_rejects_bad_objects_and_limits(monkeypatch):
    import networkx as nx

    with pytest.raises(ValueError, match="NetworkX-compatible"):
        epidemic._graph_size(object())
    with pytest.raises(ValueError, match="node count"):
        epidemic._graph_size(nx.Graph())
    monkeypatch.setattr(epidemic, "MAX_NETWORK_EDGES", 0)
    with pytest.raises(ValueError, match="edge count"):
        epidemic._graph_size(nx.path_graph(2))


def test_heterogeneity_rejects_nonfinite_value(monkeypatch):
    import networkx as nx

    monkeypatch.setattr(epidemic.np, "fromiter", lambda *a, **k: np.array([np.inf]))
    with pytest.raises(RuntimeError, match="non-finite"):
        epidemic.heterogeneity_factor(nx.path_graph(2))


def test_sir_on_network_rejects_work_and_handles_zero_seed(monkeypatch):
    import networkx as nx

    graph = nx.path_graph(3)
    monkeypatch.setattr(epidemic, "MAX_RESULT_CELLS", 0)
    with pytest.raises(ValueError, match="worst-case work"):
        epidemic.sir_on_network(graph, 0.1, 0.1, 1, max_steps=1)
    monkeypatch.undo()
    result = epidemic.sir_on_network(graph, 0.0, 0.0, 0, max_steps=0)
    assert result["steps"] == 0
    assert result["peak"] == 0
    assert result["attack_rate"] == 0.0


def test_network_gillespie_validates_t_max():
    with pytest.raises(ValueError, match="must be numeric"):
        epidemic.gillespie_sir_once(0.1, 0.1, 1, 10, t_max="soon")
    with pytest.raises(ValueError, match="finite and positive"):
        epidemic.gillespie_sir_once(0.1, 0.1, 1, 10, t_max=0)


def test_network_gillespie_event_bound_and_zero_total_rate(monkeypatch):
    real_bounded_int = epidemic.bounded_int

    def fake_bounded_int(value, *, name, minimum, maximum):
        return {"population size": 0, "seed infections": 1}.get(name, value)

    monkeypatch.setattr(epidemic, "bounded_int", fake_bounded_int)
    with pytest.raises(RuntimeError, match="event bound exceeded"):
        epidemic.gillespie_sir_once(0.1, 0.1, 1, 10)
    monkeypatch.setattr(epidemic, "bounded_int", real_bounded_int)
    result = epidemic.gillespie_sir_once(0.0, 0.0, 1, 10)
    assert result["events"] == 0
    assert result["extinct_early"] is True


# --------------------------------------------------------------------------- #
# bayesian.likelihoods
# --------------------------------------------------------------------------- #

def test_student_t_rejects_invalid_scale_and_df():
    observed = np.array([0.0, 1.0])
    mean = np.array([0.0, 0.0])
    assert likelihoods.log_likelihood("student_t", observed, mean, sigma=0.0) == -math.inf
    assert likelihoods.log_likelihood("student_t", observed, mean, sigma=1.0, df=0.0) == -math.inf
    assert likelihoods.log_likelihood("student_t", observed, mean, sigma=1.0, df=float("nan")) == -math.inf


def test_replicate_defaults_and_array_dispersions():
    rng = np.random.default_rng(0)
    normal = likelihoods.replicate("normal", np.zeros((2, 3)), None, rng)
    assert normal.shape == (2, 3)
    student = likelihoods.replicate("student_t", np.zeros((2, 3)), None, rng)
    assert student.shape == (2, 3)
    gamma = likelihoods.replicate("gamma", np.ones((2, 3)), None, rng)
    assert gamma.shape == (2, 3)
    scaled = likelihoods.replicate("normal", np.zeros((2, 3)), np.array([1.0, 2.0]), rng)
    assert scaled.shape == (2, 3)
    student_scaled = likelihoods.replicate("student_t", np.zeros((2, 3)), np.array([1.0, 2.0]), rng)
    assert student_scaled.shape == (2, 3)


# --------------------------------------------------------------------------- #
# pde.diffusion
# --------------------------------------------------------------------------- #

def test_heat_ftcs_rejects_non_numeric_parameter():
    with pytest.raises(ValueError, match="must be numeric"):
        diffusion.heat_ftcs("alpha", 1.0, 3, 0.1, 1.0)


def test_heat_ftcs_rejects_rounded_step_overflow(monkeypatch):
    monkeypatch.setattr(diffusion, "MAX_FTCS_STEPS", 3)
    with pytest.raises(ValueError, match="step count must be in"):
        diffusion.heat_ftcs(0.0, 1.0, 3, 1.0, 3.5)


def test_heat_ftcs_rejects_non_finite_error(monkeypatch):
    monkeypatch.setattr(diffusion.np, "sqrt", lambda value: float("nan"))
    with pytest.raises(RuntimeError, match="non-finite error"):
        diffusion.heat_ftcs(0.0, 1.0, 3, 1.0, 1.0)


# --------------------------------------------------------------------------- #
# numerical_verification_v2
# --------------------------------------------------------------------------- #

def _model_ir():
    return ModelIR.from_dict({
        "schema_version": "1.0", "name": "n", "domain": "test", "family": "ode",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless", "initial": 1.0}],
        "parameters": [], "equations": [{"target": "x", "expression": "-x", "kind": "derivative"}],
    })


def test_numeric_leaves_skips_nonfinite_arrays():
    assert nv2._numeric_leaves([1.0, float("inf")]) == {}


def test_terminal_states_handles_missing_empty_and_zero_length():
    assert nv2._terminal_states({"states": None}).size == 0
    assert nv2._terminal_states({"states": {"x": []}}).size == 0
    terminal = nv2._terminal_states({"states": {"x": [1.0, 2.0]}})
    assert terminal.tolist() == [2.0]


def test_relative_rejects_incompatible_arrays():
    with pytest.raises(ValueError, match="incompatible/non-finite"):
        nv2._relative(np.array([1.0]), np.array([1.0, 2.0]))


def test_run_rejects_failed_replay():
    with pytest.raises(RuntimeError, match="verification replay failed"):
        nv2._run(lambda *a, **k: {"status": "FAIL"}, _model_ir(),
                 t_span=(0.0, 1.0), points=3, parameter_overrides=None, seed=0)


def test_resolution_study_degenerate_grid_and_summary_fallback():
    def simulate(model, *, t_span, points, parameter_overrides, seed, approve_heavy):
        return {"status": "PASS", "value": 1.0}

    degenerate = nv2._resolution_study(
        _model_ir(), simulate_once=simulate, t_span=(0.0, 1.0), points=200_000,
        parameter_overrides=None, seed=0, tolerance=1e-3, approve_heavy=True)
    assert degenerate["study"] == "same_seed_reproducibility"

    summary = nv2._resolution_study(
        _model_ir(), simulate_once=simulate, t_span=(0.0, 1.0), points=2,
        parameter_overrides=None, seed=0, tolerance=1e-3, approve_heavy=True)
    assert summary["error_metric"] == "numeric-summary relative difference"
    assert summary["estimated_numerical_error"] == 0.0


def test_refinement_study_validates_tolerance_and_points():
    with pytest.raises(ValueError, match="tolerance must be finite and positive"):
        nv2.numerical_refinement_study_v2(_model_ir(), simulate_once=lambda *a, **k: {},
                                          t_span=(0.0, 1.0), tolerance=0.0)
    with pytest.raises(ValueError, match="points must be at least 2"):
        nv2.numerical_refinement_study_v2(_model_ir(), simulate_once=lambda *a, **k: {},
                                          t_span=(0.0, 1.0), points=1)


# --------------------------------------------------------------------------- #
# standards_export
# --------------------------------------------------------------------------- #

def _export_model(**overrides):
    payload = {
        "schema_version": "1.0", "name": "export-model", "domain": "physics",
        "family": "ode", "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless"}],
        "parameters": [{"name": "k", "unit": "1/day"}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    }
    payload.update(overrides)
    return ModelIR.from_dict(payload)


def test_sbml_omits_absent_initial_and_parameter_values():
    result = standards_export.export_sbml_l3v2(_export_model())
    assert result["status"] == "PASS"
    assert "initialConcentration" not in result["content"]
    assert "value=" not in result["content"]


def test_sbml_accepts_clean_libsbml_document(monkeypatch):
    class Document:
        def getNumErrors(self):
            return 0

    monkeypatch.setitem(sys.modules, "libsbml",
                        SimpleNamespace(readSBMLFromString=lambda content: Document()))
    result = standards_export.export_sbml_l3v2(_export_model())
    assert result["validation"]["schema_validation"] == "PASS"
    assert "messages" not in result["validation"]


def test_cellml_emits_duplicate_custom_units_once():
    model = _export_model(parameters=[
        {"name": "k", "unit": "1/day"},
        {"name": "k1", "unit": "minute"}, {"name": "k2", "unit": "min"}])
    result = standards_export.export_cellml_2(model)
    assert result["status"] == "PASS"
    assert result["content"].count('<units name="minute"') == 1


def test_cellml_handles_absent_initial_and_nonderivative_equation():
    model = _export_model(equations=[
        {"target": "x", "expression": "-k*x", "kind": "derivative"},
        {"target": "x", "expression": "x - 1", "kind": "algebraic"},
    ])
    result = standards_export.export_cellml_2(model)
    assert result["status"] == "PASS"
    assert "initial_value" not in result["content"]
    assert "<ci>x</ci>" in result["content"]


def test_cellml_validation_without_parser_result(monkeypatch):
    class Parser:
        def parseModel(self, content):
            return None

        def issueCount(self):
            return 0

    class Validator:
        def validateModel(self, parsed):
            raise AssertionError("validator must not run without a parsed model")

        def issueCount(self):
            return 0

    monkeypatch.setitem(sys.modules, "libcellml",
                        SimpleNamespace(Parser=Parser, Validator=Validator))
    result = standards_export._validate_cellml("<model/>")
    assert result["schema_validation"] == "FAIL"
    assert result["libcellml_errors"] == 0


def test_cellml_validation_collects_parser_and_validator_messages(monkeypatch):
    class Issue:
        def __init__(self, text):
            self.text = text

        def description(self):
            return self.text

    class Parser:
        def parseModel(self, content):
            return object()

        def issueCount(self):
            return 1

        def issue(self, index):
            return Issue("parse issue")

    class Validator:
        def validateModel(self, parsed):
            assert parsed is not None

        def issueCount(self):
            return 2

        def issue(self, index):
            return Issue(f"validate issue {index}")

    monkeypatch.setitem(sys.modules, "libcellml",
                        SimpleNamespace(Parser=Parser, Validator=Validator))
    result = standards_export._validate_cellml("<model/>")
    assert result["schema_validation"] == "FAIL"
    assert result["libcellml_errors"] == 3
    assert result["messages"] == ["parse issue", "validate issue 0", "validate issue 1"]


# --------------------------------------------------------------------------- #
# advanced_diagnostics
# --------------------------------------------------------------------------- #

def test_equilibrium_defaults_missing_initial_state_to_one():
    model = ModelIR.from_dict({
        "schema_version": "1.0", "name": "eq", "domain": "physics", "family": "ode",
        "independent_variable": "t", "independent_unit": "day",
        "variables": [{"name": "x", "unit": "dimensionless"}],
        "parameters": [{"name": "k", "unit": "1/day", "value": 0.5}],
        "equations": [{"target": "x", "expression": "-k*x", "kind": "derivative"}],
    })
    root = diag._equilibrium_for_ode(model, parameter_values={"k": 0.5})
    assert root == {"x": pytest.approx(0.0, abs=1e-12)}


# --------------------------------------------------------------------------- #
# causal_engine
# --------------------------------------------------------------------------- #

def test_logistic_irls_exhausts_iterations_for_separable_data():
    x = np.array([-3.0, -2.0, -1.0, 1.0, 2.0, 3.0])
    design = np.column_stack([np.ones_like(x), x])
    treatment = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    beta, propensity = _logistic_irls(design, treatment)
    assert np.all(np.isfinite(beta))
    assert beta[1] > 0
    assert np.all(propensity >= 1e-4)
    assert np.all(propensity <= 1 - 1e-4)


def test_iv_identification_accepts_string_instrument():
    model = ModelIR(
        name="causal-iv", domain="test", family=ModelFamily.CAUSAL,
        variables=[], parameters=[], equations=[],
        metadata={"causal": {
            "data": {"x": [0, 1, 0, 1, 0, 1], "y": [0, 1, 0, 1, 1, 0],
                     "z": [1, 0, 1, 0, 1, 0]},
            "treatment": "x", "outcome": "y",
            "identification": {"method": "iv", "instrument": "z"},
        }},
    )
    result = estimate_causal_model(model, t_span=(0.0, 1.0), points=10,
                                   parameter_overrides=None, seed=7)
    assert result["causal_effect"]["method"] == "instrumental_variables_2sls"
