"""Coverage hardening for the PyMC backend adapter (fully faked at import boundary)."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from axiomize.bayesian.pymc_tool import PyMCTool, _finite


class _Array:
    def __init__(self, values):
        self._values = np.asarray(values, dtype=float)

    def to_numpy(self):
        return self._values


class _Trace:
    def __init__(self, mu_samples):
        self.posterior = {"mu": _Array(mu_samples)}


def _fake_pymc(mu_samples, *, version="9.9-fake"):
    module = types.ModuleType("pymc")
    module.__version__ = version
    module.calls = []

    class Model:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def Normal(name, **kwargs):
        module.calls.append(("Normal", name, kwargs))
        return name

    def sample(**kwargs):
        module.calls.append(("sample", kwargs))
        return _Trace(mu_samples)

    module.Model = Model
    module.Normal = Normal
    module.sample = sample
    return module


def _fake_arviz(*, rhat=1.01, ess=250.0, raises=None):
    module = types.ModuleType("arviz")

    def _rhat(_):
        if raises:
            raise raises
        return _Array([rhat])

    def _ess(_):
        if raises:
            raise raises
        return _Array([ess])

    module.rhat = _rhat
    module.ess = _ess
    return module


def _payload(**overrides):
    payload = {"model": "normal-mean", "y": [1.0, 2.0, 3.0], "draws": 4, "tune": 2, "seed": 7}
    payload.update(overrides)
    return payload


def test_finite_validation():
    assert _finite("2.5", name="x") == 2.5
    with pytest.raises(ValueError, match="must be numeric"):
        _finite(object(), name="x")
    with pytest.raises(ValueError, match="must be finite"):
        _finite(float("inf"), name="x")
    with pytest.raises(ValueError, match="finite and positive"):
        _finite(0, name="x", positive=True)


def test_probe_version_imports_pymc(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc([0.0], version="7.1"))
    assert PyMCTool._probe_version() == "7.1"


def test_validate_input_rejections():
    tool = PyMCTool()
    with pytest.raises(ValueError, match="needs a 'model' description"):
        tool.validate_input([])
    with pytest.raises(ValueError, match="needs observed data"):
        tool.validate_input({"model": "normal-mean"})
    tool.validate_input({"model": "other"})


def test_availability_failure_raises_tool_unavailable(monkeypatch):
    def fail():
        raise ImportError("No module named 'pymc'")

    monkeypatch.setattr(PyMCTool, "_probe_version", classmethod(lambda cls: fail()))
    with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
        PyMCTool().execute(_payload())


def test_unimplemented_model_raises(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc([0.0, 1.0]))
    with pytest.raises(NotImplementedError, match="not implemented"):
        PyMCTool().execute({"model": "hierarchical"})


def test_normal_mean_pass_with_diagnostics(monkeypatch):
    draws = 8
    samples = np.linspace(-1.0, 1.0, 2 * draws).reshape(2, draws)
    fake_pymc = _fake_pymc(samples)
    monkeypatch.setitem(sys.modules, "pymc", fake_pymc)
    monkeypatch.setitem(sys.modules, "arviz", _fake_arviz(rhat=1.01, ess=250.0))

    result = PyMCTool().execute(_payload(draws=draws))
    assert result["status"] == "PASS"
    assert result["backend"] == "pymc-9.9-fake"
    assert result["n_obs"] == 3
    assert result["draws"] == draws
    assert result["tune"] == 2
    assert result["chains"] == 2
    assert result["seed"] == 7
    assert result["posterior_mean"] == pytest.approx(0.0)
    assert result["posterior_sd"] == pytest.approx(np.std(samples))
    assert result["ci95"][0] < result["ci95"][1]
    assert result["r_hat"] == 1.01
    assert result["ess_bulk"] == 250.0
    assert result["diagnostics_note"] == ""
    sample_call = [call for call in fake_pymc.calls if call[0] == "sample"][0][1]
    assert sample_call["chains"] == 2 and sample_call["cores"] == 1
    assert sample_call["progressbar"] is False


def test_normal_mean_warning_for_bad_rhat(monkeypatch):
    samples = np.zeros((2, 4))
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(samples))
    monkeypatch.setitem(sys.modules, "arviz", _fake_arviz(rhat=1.2))
    result = PyMCTool().execute(_payload())
    assert result["status"] == "WARNING"
    assert result["r_hat"] == 1.2


def test_normal_mean_nan_rhat_warns(monkeypatch):
    samples = np.zeros((2, 4))
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(samples))
    monkeypatch.setitem(sys.modules, "arviz", _fake_arviz(rhat=float("nan")))
    result = PyMCTool().execute(_payload())
    assert result["status"] == "WARNING"


def test_normal_mean_diagnostics_missing(monkeypatch):
    samples = np.zeros((2, 4))
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(samples))
    monkeypatch.setitem(sys.modules, "arviz", None)
    result = PyMCTool().execute(_payload())
    assert result["r_hat"] == ""
    assert "diagnostics unavailable" in result["diagnostics_note"]


def test_normal_mean_diagnostics_error(monkeypatch):
    samples = np.zeros((2, 4))
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(samples))
    monkeypatch.setitem(sys.modules, "arviz", _fake_arviz(raises=ValueError("boom")))
    result = PyMCTool().execute(_payload())
    assert "ValueError: boom" in result["diagnostics_note"]


def test_normal_mean_malformed_posterior(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(np.zeros(3)))
    with pytest.raises(RuntimeError, match="malformed/non-finite posterior"):
        PyMCTool().execute(_payload())


def test_normal_mean_nan_posterior(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(np.full((2, 4), np.nan)))
    with pytest.raises(RuntimeError, match="malformed/non-finite posterior"):
        PyMCTool().execute(_payload())


def test_normal_mean_input_validation(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(np.zeros((2, 4))))
    tool = PyMCTool()
    with pytest.raises(ValueError, match="numeric 1D observation array"):
        tool.execute(_payload(y=["not-a-number"]))
    with pytest.raises(ValueError, match="one-dimensional"):
        tool.execute(_payload(y=[[1, 2], [3, 4]]))
    with pytest.raises(ValueError, match="1..200000 observations"):
        tool.execute(_payload(y=[]))
    with pytest.raises(ValueError, match="only finite values"):
        tool.execute(_payload(y=[1.0, float("inf"), 2.0]))
    with pytest.raises(ValueError, match="sigma must be numeric"):
        tool.execute(_payload(sigma="wide"))
    with pytest.raises(ValueError, match="sigma must be finite and positive"):
        tool.execute(_payload(sigma=-1))
    with pytest.raises(ValueError, match="prior_mu must be finite"):
        tool.execute(_payload(prior_mu=float("nan")))
    with pytest.raises(ValueError, match="prior_sigma must be finite and positive"):
        tool.execute(_payload(prior_sigma=0))
    with pytest.raises(ValueError, match="draws"):
        tool.execute(_payload(draws=0))


def test_normal_mean_work_and_seed_limits(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymc", _fake_pymc(np.zeros((2, 4))))
    tool = PyMCTool()
    with pytest.raises(ValueError, match="hard likelihood work limit"):
        tool.execute(_payload(y=[1.0] * 300, draws=100000, tune=100000))
    with pytest.raises(ValueError, match="pymc.seed"):
        tool.execute(_payload(seed=-1))
