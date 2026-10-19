"""Exercise the shipped fitting CLI with real CSV, ODE and logistic observations."""
from __future__ import annotations

import json
import math
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize.tools import fit as packaged_fit


@pytest.mark.parametrize("bad, message", [
    (None, "numeric"), ("invalid", "numeric"), (float("inf"), "finite"),
    (float("nan"), "finite"),
])
def test_invalid_numeric_parameters_are_rejected(bad, message):
    with pytest.raises(ValueError, match=message):
        packaged_fit._finite_float(bad, "parameter")


@pytest.mark.parametrize("t, y, match", [
    ([[0, 1]], [[1, 2]], "one-dimensional"),
    ([0, 1], [1], "same length"),
    ([0], [1], "at least"),
    ([0, 0, 1], [1, 2, 3], "strictly increasing"),
    ([0, 1, 2], [1, float("inf"), 2], "finite"),
    ([2, 1, 0], [1, 2, 3], "strictly increasing"),
])
def test_real_fitting_grid_refuses_invalid_observations(t, y, match):
    with pytest.raises(ValueError, match=match):
        packaged_fit._validate_xy(t, y)


def test_logistic_fitting_recovers_known_growth_and_carrying_capacity():
    t = np.linspace(0, 20, 23)
    y = packaged_fit._logistic_curve(t, 0.35, 120, 6)
    result = packaged_fit.fit_logistic(t, y)
    assert result["params"]["r"][0] == pytest.approx(0.35, abs=0.015)
    assert result["params"]["K"][0] == pytest.approx(120, abs=0.5)
    assert result["rmse"] < 1e-3
    assert len(result["fitted"]) == len(t)
    assert result["diag"]["n"] == len(t)


def test_native_sir_fitting_recovers_physically_valid_parameters():
    t = np.linspace(0, 12, 18)
    y = packaged_fit._sir_curve(t, 0.4, 0.1, 8, 500)
    result = packaged_fit.fit_sir(t, y, N=500)
    assert result["params"]["beta"][0] == pytest.approx(0.4, abs=0.01)
    assert result["params"]["gamma"][0] == pytest.approx(0.1, abs=0.01)
    assert result["derived"]["R0"][0] == pytest.approx(4, abs=0.3)
    assert result["rmse"] < 0.1


def test_sir_fitting_refuses_inferred_population_and_nonphysical_cases():
    t = [0, 1, 2, 3]
    y = [1, 2, 3, 4]
    with pytest.raises(ValueError, match="N is required"):
        packaged_fit.fit_sir(t, y)
    with pytest.raises(ValueError, match="N must be positive"):
        packaged_fit.fit_sir(t, y, N=0)
    with pytest.raises(ValueError, match="first observed infected"):
        packaged_fit.fit_sir(t, [21, 2, 3, 4], N=20)
    with pytest.raises(ValueError, match="lie in"):
        packaged_fit.fit_sir(t, [1, 2, 21, 4], N=20)


@pytest.mark.parametrize("bad,match", [
    ({"beta": -1, "gamma": 0.2, "I0": 5, "N": 100}, "non-negative"),
    ({"beta": 0.2, "gamma": 0, "I0": 5, "N": 100}, "positive"),
    ({"beta": 0.2, "gamma": 0.1, "I0": 105, "N": 100}, "requires N"),
])
def test_sir_curve_rejects_unphysical_parameters(bad, match):
    with pytest.raises(ValueError, match=match):
        packaged_fit._sir_curve([0, 1, 2], **bad)


def test_perfect_fit_information_criteria_remain_valid_json():
    diag = packaged_fit.diagnostics([1, 2, 3], [1, 2, 3], k=2)
    assert diag["rss"] == 0
    assert diag["perfect_fit_floor_applied"]
    assert math.isfinite(diag["aic"])
    assert math.isfinite(diag["bic"])
    json.dumps(diag, allow_nan=False)


def test_nonfinite_residuals_are_not_accepted_as_valid_diagnostics():
    with pytest.raises(ValueError, match="matching finite"):
        packaged_fit.diagnostics([1, float("nan")], [1, 2], 2)
    with pytest.raises(ValueError, match="non-negative"):
        packaged_fit.diagnostics([1, 2], [1, 2], -1)


def test_reproducibility_preserves_actual_residual_autocorrelation():
    assert packaged_fit._lag1([1, 2]) == 0.0
    assert packaged_fit._lag1([3, 3, 3, 3]) == 0.0
    assert packaged_fit._lag1([1, 2, 3, 4]) == pytest.approx(1.0)


def test_actual_csv_parser_roundtrips_known_measurements(tmp_path):
    path = tmp_path / "measurements.csv"
    path.write_text("day,infected\n0,2\n1,3\n2,5\n", encoding="utf-8")
    header, t, y = packaged_fit.load_csv(path)
    assert header == ["day", "infected"]
    np.testing.assert_array_equal(t, [0, 1, 2])
    np.testing.assert_array_equal(y, [2, 3, 5])


@pytest.mark.parametrize("content,pattern", [
    ("", "empty"), ("day\n1\n2\n", "at least two columns"),
    ("day,y\n0,1\n", "at least 2 parseable"),
    ("day,y\n0,1\n1,invalid\n", "cannot parse"),
    ("day,y\n0,1\n1,nan\n", "finite"),
    ("day,y\n0,1\n0,2\n", "strictly increasing"),
])
def test_actual_csv_parser_fails_closed_on_invalid_source(tmp_path, content, pattern):
    path = tmp_path / "invalid.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(SystemExit, match=pattern):
        packaged_fit.load_csv(path)


def test_actual_calibration_cli_prints_valid_json_for_known_logistic_data(tmp_path, monkeypatch, capsys):
    path = tmp_path / "known.csv"
    t = np.linspace(0, 12, 15)
    y = packaged_fit._logistic_curve(t, 0.3, 120, 6)
    path.write_text("time,count\n" + "".join(f"{a},{b}\n" for a, b in zip(t, y, strict=True)), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["axiomize-fit", "--model", "logistic", "--data", str(path), "--json"])
    packaged_fit.main()
    result = json.loads(capsys.readouterr().out)
    assert result["model"] == "logistic"
    assert result["params"]["r"]["value"] == pytest.approx(0.3, abs=0.02)
    assert math.isfinite(result["diagnostics"]["bic"])


def test_comparison_reports_missing_population_instead_of_guessing(tmp_path, monkeypatch, capsys):
    t = np.linspace(0, 12, 15)
    y = packaged_fit._logistic_curve(t, 0.3, 120, 6)
    path = tmp_path / "measurements.csv"
    path.write_text("time,count\n" + "".join(f"{a},{b}\n" for a, b in zip(t, y, strict=True)), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["axiomize-fit", "--data", str(path), "--compare"])
    with pytest.raises(SystemExit) as result:
        packaged_fit.main()
    assert result.value.code == 0
    assert "requires --N" in capsys.readouterr().out


def test_script_fitting_failures_must_return_nonzero_exit(monkeypatch, tmp_path):
    p = tmp_path / "data.csv"
    p.write_text("time,infected\n0,1\n1,2\n2,3\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["axiomize-fit", "--model", "sir", "--data", str(p)])
    with pytest.raises(SystemExit) as failed:
        packaged_fit.main()
    assert failed.value.code == 2


def test_direct_selftests_recover_controlled_ground_truth(capsys):
    assert packaged_fit.selftest_logistic() == 0
    assert packaged_fit.selftest_sir() == 0
    shown = capsys.readouterr().out
    assert shown.count("PASS") >= 2


def test_cli_plain_text_rejects_numerically_invalid_missing_data(tmp_path, monkeypatch, capsys):
    data = tmp_path / "observed.csv"
    t = np.linspace(0, 9, 12)
    y = packaged_fit._logistic_curve(t, 0.3, 100, 6)
    data.write_text(
        "time,observed\n" + "".join(f"{x},{v}\n" for x, v in zip(t, y, strict=True)),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["axiomize-fit", "--model", "logistic", "--data", str(data)])
    packaged_fit.main()
    output = capsys.readouterr().out
    assert "calibration: logistic" in output
    assert "RMSE" in output and "AIC" in output and "BIC" in output
    assert "diagnostics" in output


def test_plain_text_calibration_cli_records_actual_sir_diagnostics(tmp_path, monkeypatch, capsys):
    path = tmp_path / "infected.csv"
    t = np.linspace(0, 10, 15)
    y = packaged_fit._sir_curve(t, 0.35, 0.12, 10, 1000)
    path.write_text(
        "t,I\n" + "".join(f"{x},{v}\n" for x, v in zip(t, y, strict=True)),
        encoding="utf-8",
    )
    monkeypatch.setattr(sys, "argv", ["axiomize-fit", "--data", str(path), "--N", "1000"])
    packaged_fit.main()
    output = capsys.readouterr().out
    assert "calibration: sir" in output
    assert "beta" in output and "gamma" in output and "R0" in output


def test_actual_comparison_with_known_population_executes_both_models(capsys):
    t = np.linspace(0, 12, 15)
    y = packaged_fit._sir_curve(t, 0.35, 0.1, 8, 500)
    rc = packaged_fit.compare(t, y, SimpleNamespace(N=500))
    out = capsys.readouterr().out
    assert rc == 0
    assert "BIC prefers" in out
    assert "sir" in out and "logistic" in out


def test_actual_comparison_does_not_claim_success_if_every_fitter_fails(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise RuntimeError("numerical integrator refused")

    monkeypatch.setattr(packaged_fit, "fit_logistic", fail)
    monkeypatch.setattr(packaged_fit, "fit_sir", fail)
    result = packaged_fit.compare([0, 1, 2], [1, 2, 3], SimpleNamespace(N=100))
    assert result == 1
    assert "No model produced a valid fit" in capsys.readouterr().out


def test_user_supplied_plot_path_writes_real_figure(tmp_path):
    t = np.linspace(0, 10, 15)
    y = packaged_fit._logistic_curve(t, 0.25, 100, 7)
    result = packaged_fit.fit_logistic(t, y)
    figure = tmp_path / "fitted-curve.png"
    args = SimpleNamespace(plot=str(figure))
    assert packaged_fit.maybe_plot(args, t, y, result, announce=False) == str(figure)
    assert figure.stat().st_size > 1000


def test_plot_is_optional_and_does_not_require_backends():
    assert packaged_fit.maybe_plot(
        SimpleNamespace(plot=None), [0, 1], [1, 2], {"fitted": [1, 2]}
    ) is None


def test_csv_input_bounded_before_allocation(tmp_path, monkeypatch):
    p = tmp_path / "rows.csv"
    p.write_text("time,observed\n0,1\n1,2\n2,3\n", encoding="utf-8")
    monkeypatch.setattr(packaged_fit, "MAX_CSV_BYTES", 10)
    with pytest.raises(SystemExit, match="hard CSV size limit"):
        packaged_fit.load_csv(p)


def test_csv_length_guard_refuses_excess_rows(tmp_path, monkeypatch):
    p = tmp_path / "rows.csv"
    p.write_text("time,observed\n0,1\n1,2\n2,3\n", encoding="utf-8")
    monkeypatch.setattr(packaged_fit, "MAX_DATA_ROWS", 2)
    with pytest.raises(SystemExit, match="hard row limit"):
        packaged_fit.load_csv(p)


def test_missing_csv_file_is_distinct_from_an_empty_csv(tmp_path):
    with pytest.raises(SystemExit, match="cannot stat"):
        packaged_fit.load_csv(tmp_path / "missing.csv")


def test_csv_parser_skips_incomplete_rows_but_retains_explicit_valid_values(tmp_path):
    path = tmp_path / "measurements.csv"
    path.write_text(
        "time,count\n0,1\n1\n2,3\n3\n4,5\n", encoding="utf-8",
    )
    header, t, y = packaged_fit.load_csv(path)
    assert header == ["time", "count"]
    np.testing.assert_array_equal(t, [0, 2, 4])
    np.testing.assert_array_equal(y, [1, 3, 5])


def test_csv_input_must_not_infer_sir_population(monkeypatch, tmp_path):
    p = tmp_path / "infected.csv"
    p.write_text("time,infected\n0,1\n1,2\n2,3\n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["axiomize-fit", "--data", str(p), "--model", "sir"]
    )
    with pytest.raises(SystemExit) as result:
        packaged_fit.main()
    assert result.value.code == 2


def test_main_cli_refuses_implicit_data_when_not_in_selftest_mode(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["axiomize-fit", "--model", "logistic"])
    with pytest.raises(SystemExit) as out:
        packaged_fit.main()
    assert out.value.code == 2


def test_negative_observations_are_not_fitted_to_positive_logistic_model():
    with pytest.raises(ValueError, match="non-negative"):
        packaged_fit.fit_logistic([0, 1, 2, 3], [1, -2, 3, 4])


def test_reject_fractional_or_nonfinite_telemetry():
    with pytest.raises(ValueError, match="matching finite"):
        packaged_fit.diagnostics([1, 2], [float("inf"), 2], k=1)
    with pytest.raises(ValueError, match="observations"):
        packaged_fit.diagnostics([], [], k=1)


def test_scientific_report_writer_formats_observed_values_not_new_predictions(capsys):
    packaged_fit.report("evidence", 3.14, err=0.25, unit="kg")
    actual = capsys.readouterr().out
    assert "3.14" in actual
    assert "+/- 0.25" in actual
    assert "kg" in actual


def test_low_level_array_length_limit_checked_independently_of_csv(monkeypatch):
    monkeypatch.setattr(packaged_fit, "MAX_DATA_ROWS", 2)
    with pytest.raises(ValueError, match="dataset exceeds hard row limit"):
        packaged_fit._validate_xy([0, 1, 2], [1, 2, 3])


def test_actual_file_permission_denial_has_distinct_reason(tmp_path, monkeypatch):
    import builtins

    p = tmp_path / "exists.csv"
    p.write_text("time,value\n0,1\n1,2\n", encoding="utf-8")
    actual_open = builtins.open

    def reject_file(candidate, *args, **kwargs):
        if str(candidate) == str(p):
            raise PermissionError("explicitly unreadable scientific input")
        return actual_open(candidate, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", reject_file)
    with pytest.raises(SystemExit, match="cannot open"):
        packaged_fit.load_csv(p)


def test_failed_sir_integrator_cannot_report_a_calibration(monkeypatch):
    monkeypatch.setattr(
        packaged_fit, "solve_ivp",
        lambda *args, **kwargs: SimpleNamespace(success=False, message="solver step failed"),
    )
    with pytest.raises(RuntimeError, match="SIR integration failed"):
        packaged_fit._sir_curve([0, 1, 2], 0.3, 0.1, 3, 100)


def test_absent_plotting_backend_is_reported_not_a_success(tmp_path, monkeypatch, capsys):
    import builtins

    original = builtins.__import__

    def missing_plot(name, *args, **kwargs):
        if name == "matplotlib.pyplot":
            raise ImportError("plotting backend intentionally unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_plot)
    actual = packaged_fit.maybe_plot(
        SimpleNamespace(plot=str(tmp_path / "out.png")),
        [0, 1], [1, 2], {"fitted": [1, 2]},
    )
    assert actual is None
    assert "matplotlib not installed" in capsys.readouterr().out


def test_native_plotting_reports_real_artifact_path(tmp_path, capsys):
    path = tmp_path / "plot.png"
    t = np.linspace(0, 9, 12)
    y = packaged_fit._logistic_curve(t, 0.25, 100, 6)
    actual = packaged_fit.maybe_plot(
        SimpleNamespace(plot=str(path)), t, y, {"fitted": y},
    )
    assert actual == str(path)
    assert "plot saved ->" in capsys.readouterr().out
    assert path.stat().st_size > 500


@pytest.mark.parametrize("model", ["logistic", "sir"])
def test_real_selftest_cli_dispatches_only_selected_scientific_model(model, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["axiomize-fit", "--selftest", "--model", model])
    with pytest.raises(SystemExit) as done:
        packaged_fit.main()
    assert done.value.code == 0
    assert f"selftest: {model}" in capsys.readouterr().out


def test_cli_cannot_report_success_after_fitter_failure(tmp_path, monkeypatch):
    p = tmp_path / "measurements.csv"
    p.write_text("time,value\n0,1\n1,2\n2,3\n", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["axiomize-fit", "--model", "logistic", "--data", str(p)],
    )

    def model_refused(*args, **kwargs):
        raise RuntimeError("identifiability failure")

    monkeypatch.setattr(packaged_fit, "fit_logistic", model_refused)
    with pytest.raises(SystemExit) as failed:
        packaged_fit.main()
    assert failed.value.code == 2


def test_json_cli_includes_actual_saved_fitted_plot(tmp_path, monkeypatch, capsys):
    p = tmp_path / "measurements.csv"
    t = np.linspace(0, 9, 12)
    y = packaged_fit._logistic_curve(t, 0.25, 100, 6)
    p.write_text(
        "time,count\n" + "".join(f"{a},{b}\n" for a, b in zip(t, y, strict=True)),
        encoding="utf-8",
    )
    plot = tmp_path / "observed.png"
    monkeypatch.setattr(
        sys, "argv", [
            "axiomize-fit", "--model", "logistic", "--data", str(p), "--json",
            "--plot", str(plot),
        ],
    )
    packaged_fit.main()
    observed = json.loads(capsys.readouterr().out)
    assert observed["plot"] == str(plot)
    assert plot.stat().st_size > 500


class HugeNumeric:
    def __float__(self):
        raise OverflowError("unrepresentable numeric")


def test_numeric_conversion_overflow_is_explicitly_refused():
    with pytest.raises(ValueError, match="must be numeric"):
        packaged_fit._finite_float(HugeNumeric(), "parameter")


def test_quiet_json_mode_without_plotting_backend_has_no_false_artifact(
    tmp_path, monkeypatch, capsys,
):
    import builtins

    original = builtins.__import__

    def missing_plot(name, *args, **kwargs):
        if name == "matplotlib.pyplot":
            raise ImportError("plotting backend deliberately unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing_plot)
    output = tmp_path / "unavailable-plot.png"
    result = packaged_fit.maybe_plot(
        SimpleNamespace(plot=str(output)),
        [0, 1], [1, 2], {"fitted": [1, 2]}, announce=False,
    )
    assert result is None
    assert not output.exists()
    assert capsys.readouterr().out == ""
