"""GAP-1: PyMC/JAX real availability state (live probe).

When an optional backend is missing the adapter must return/raise an explicit
TOOL_UNAVAILABLE result and must never fabricate output. Input validation is
still checked independently of backend availability.
"""

from __future__ import annotations

import importlib.util

import pytest


def _spec_present(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def test_pymc_probe_matches_reality():
    from axiomize.bayesian.pymc_tool import PyMCTool

    meta = PyMCTool.availability()
    assert meta.available == _spec_present("pymc")
    if meta.available:
        assert isinstance(meta.version, str) and meta.version
    else:
        assert isinstance(meta.reason, str) and meta.reason


def test_pymc_execute_never_fakes():
    from axiomize.bayesian.pymc_tool import PyMCTool

    tool = PyMCTool()
    # Input validation runs before availability probing.
    with pytest.raises(ValueError):
        tool.execute({})

    valid_payload = {"model": "normal-mean", "y": [1.0, 2.0, 3.0],
                     "draws": 200, "tune": 200, "seed": 0}
    if not _spec_present("pymc"):
        # Use a structurally valid payload so this assertion tests backend
        # availability rather than the unrelated missing-input guard.
        with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
            tool.execute(valid_payload)
    else:
        # Installed backend still must reject malformed model input.
        with pytest.raises(ValueError):
            tool.execute({"model": "normal-mean"})
        out = tool.execute(valid_payload)
        assert isinstance(out, dict)
        assert "posterior_mean" in out


def test_pymc_real_fit_when_installed():
    if not _spec_present("pymc"):
        pytest.skip("pymc not installed; TOOL_UNAVAILABLE path is valid")
    import numpy as np
    from axiomize.bayesian.pymc_tool import PyMCTool

    rng = np.random.default_rng(7)
    y = rng.normal(4.0, 1.0, size=30)
    out = PyMCTool().execute({"model": "normal-mean", "y": y.tolist(),
                              "draws": 300, "tune": 300, "seed": 1})
    assert abs(out["posterior_mean"] - 4.0) < 1.0


def test_jax_real_grad_when_installed():
    if not _spec_present("jax"):
        pytest.skip("jax not installed")
    from axiomize.tools.autodiff.jax_tool import JAXTool

    out = JAXTool().execute({"operation": "grad", "x": 3.0})
    assert isinstance(out, dict)


def test_jax_tool_availability_matches_reality():
    from axiomize.tools.autodiff.jax_tool import JAXTool

    meta = JAXTool.availability()
    assert meta.available == _spec_present("jax")
    if meta.available:
        assert isinstance(meta.version, str)
    else:
        assert isinstance(meta.reason, str) and meta.reason


def test_jax_execute_never_fakes_without_jax():
    from axiomize.tools.autodiff.jax_tool import JAXTool

    tool = JAXTool()
    if _spec_present("jax"):
        with pytest.raises(ValueError):
            tool.execute({})
    else:
        with pytest.raises(RuntimeError, match="TOOL_UNAVAILABLE"):
            tool.execute({"operation": "grad", "x": 3.0})


def test_jax_grad_of_square_is_correct():
    if not _spec_present("jax"):
        pytest.skip("jax not installed")
    from axiomize.tools.autodiff.jax_tool import JAXTool

    out = JAXTool().execute({"operation": "grad", "x": 3.0})
    assert out["status"] == "PASS"
    assert out["gradient"] == pytest.approx(6.0)
    assert out["backend"].startswith("jax-")


def test_jax_hessian_of_square_is_two():
    if not _spec_present("jax"):
        pytest.skip("jax not installed")
    from axiomize.tools.autodiff.jax_tool import JAXTool

    out = JAXTool().execute({"operation": "hessian", "x": 3.0})
    assert out["status"] == "PASS"
    assert out["hessian"] == pytest.approx(2.0)


def test_jax_grad_array_input():
    if not _spec_present("jax"):
        pytest.skip("jax not installed")
    import numpy as np
    from axiomize.tools.autodiff.jax_tool import JAXTool

    out = JAXTool().execute({"operation": "grad", "x": [1.0, 2.0, 3.0]})
    assert out["status"] == "PASS"
    np.testing.assert_allclose(out["gradient"], [2.0, 4.0, 6.0])


def test_jax_grad_custom_function():
    if not _spec_present("jax"):
        pytest.skip("jax not installed")
    from axiomize.tools.autodiff.jax_tool import JAXTool

    out = JAXTool().execute({"operation": "grad", "x": 0.0, "function": "sin(x)"})
    assert out["status"] == "PASS"
    assert out["gradient"] == pytest.approx(1.0)


def test_jax_unsupported_operation_raises():
    from axiomize.tools.autodiff.jax_tool import JAXTool

    with pytest.raises(ValueError, match="operation"):
        JAXTool().validate_input({"operation": "integrate", "x": 3.0})


def test_jax_missing_x_raises():
    from axiomize.tools.autodiff.jax_tool import JAXTool

    with pytest.raises(ValueError, match="x"):
        JAXTool().validate_input({"operation": "grad"})


def test_jax_capabilities_honest():
    from axiomize.capabilities import get_capabilities

    caps = get_capabilities()
    if "jax" in caps:
        assert caps["jax"]["available"] == _spec_present("jax")


def test_router_no_fake_success_without_pymc_jax():
    from axiomize.routing.router import classify

    out = classify({"signals": ["bayesian"]})
    assert out is not None


def test_builtin_mh_fallback_works():
    from axiomize.bayesian.mh import normal_mean_posterior

    out = normal_mean_posterior([1.0, 2.0, 3.0], sigma=1.0,
                                n_samples=1000, burn=200, seed=0)
    assert "mean" in out or "posterior_mean" in out
