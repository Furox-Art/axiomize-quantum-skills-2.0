"""Coverage hardening for the JAX autodiff adapter (jax faked at import boundary)."""

from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from axiomize.tools.autodiff.jax_tool import JAXTool, _parsed_function, _to_native


def _finite_difference(fn, x, h):
    return (fn(x + h) - fn(x - h)) / (2 * h)


def _fake_jax(version="1.2-fake"):
    module = types.ModuleType("jax")
    if version is not None:
        module.__version__ = version
    module.numpy = np

    def grad(fn):
        return lambda x: _finite_difference(fn, np.asarray(x, dtype=float), 1e-4)

    def jacfwd(fn):
        return lambda x: _finite_difference(fn, np.asarray(x, dtype=float), 1e-4)

    def hessian(fn):
        def second(x):
            arr = np.asarray(x, dtype=float)
            h = 1e-3
            return (fn(arr + h) - 2 * fn(arr) + fn(arr - h)) / h ** 2

        return second

    module.grad = grad
    module.jacfwd = jacfwd
    module.hessian = hessian
    return module


def _install(monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "jax", fake)
    monkeypatch.setitem(sys.modules, "jax.numpy", fake.numpy)


def test_probe_version(monkeypatch):
    _install(monkeypatch, _fake_jax("3.4.5"))
    assert JAXTool._probe_version() == "3.4.5"
    _install(monkeypatch, _fake_jax(None))
    assert JAXTool._probe_version() == "unknown"


def test_validate_input_rejections():
    tool = JAXTool()
    with pytest.raises(ValueError, match="payload must be an object"):
        tool.validate_input([])
    with pytest.raises(ValueError, match="operation must be"):
        tool.validate_input({"operation": "laplacian", "x": 1})
    with pytest.raises(ValueError, match="needs 'x'"):
        tool.validate_input({})
    with pytest.raises(ValueError, match="must not be boolean"):
        tool.validate_input({"x": True})
    with pytest.raises(ValueError, match="must not be empty"):
        tool.validate_input({"x": []})
    with pytest.raises(ValueError, match="must be a number or list"):
        tool.validate_input({"x": {"value": 1}})
    tool.validate_input({"x": [1, 2.0, 3]})


def test_parsed_function_enforces_x_only():
    with pytest.raises(ValueError, match="depend on x only"):
        _parsed_function("x + y")
    symbols, expr = _parsed_function("x**2")
    assert set(symbols) == {"x"}
    assert str(expr) == "x**2"


def test_grad_scalar(monkeypatch):
    _install(monkeypatch, _fake_jax())
    result = JAXTool().execute({"operation": "grad", "x": 3.0, "function": "x**2"})
    assert result["status"] == "PASS"
    assert result["operation"] == "grad"
    assert result["backend"] == "jax-1.2-fake"
    assert result["x"] == 3.0
    assert result["function"] == "x**2"
    assert result["gradient"] == pytest.approx(6.0, rel=1e-4)


def test_grad_vector_and_default_function(monkeypatch):
    _install(monkeypatch, _fake_jax())
    result = JAXTool().execute({"x": [1.0, 2.0]})
    assert result["operation"] == "grad"
    assert result["x"] == [1.0, 2.0]
    assert result["gradient"] == pytest.approx(6.0, rel=1e-4)


def test_jacobian_and_hessian(monkeypatch):
    _install(monkeypatch, _fake_jax())
    jacobian = JAXTool().execute({"operation": "jacobian", "x": 2.0, "function": "x**2"})
    assert jacobian["operation"] == "jacobian"
    assert jacobian["jacobian"] == pytest.approx(4.0, rel=1e-4)

    hessian = JAXTool().execute({"operation": "hessian", "x": 2.0, "function": "x**2"})
    assert hessian["operation"] == "hessian"
    assert hessian["hessian"] == pytest.approx(2.0, rel=1e-2)


def test_unavailable_backend_raises(monkeypatch):
    def fail():
        raise ImportError("No module named 'jax'")

    monkeypatch.setattr(JAXTool, "_probe_version", classmethod(lambda cls: fail()))
    with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
        JAXTool().execute({"x": 1.0})


def test_invalid_function_rejected_before_availability(monkeypatch):
    def fail():
        raise ImportError("No module named 'jax'")

    monkeypatch.setattr(JAXTool, "_probe_version", classmethod(lambda cls: fail()))
    with pytest.raises(ValueError, match="depend on x only"):
        JAXTool().execute({"x": 1.0, "function": "y**2"})


def test_to_native_scalar_and_array():
    assert _to_native(np.float64(2.5)) == 2.5
    assert _to_native(np.array([1.0, 2.0])) == [1.0, 2.0]
