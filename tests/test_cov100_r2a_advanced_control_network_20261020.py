"""Coverage hardening round 2a: advanced engines (control, network)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from axiomize import advanced_family_engine as adv
from axiomize.model_ir import EquationSpec, ModelFamily, ModelIR, ParameterSpec, VariableSpec


def _model(family, *, variables=None, parameters=None, equations=None, metadata=None):
    return ModelIR(
        name=f"{family.value}-model",
        domain="test",
        family=family,
        variables=list(variables or []),
        parameters=list(parameters or []),
        equations=list(equations or []),
        metadata=dict(metadata or {}),
    )


def _control(cfg, *, variables=None) -> ModelIR:
    return _model(
        ModelFamily.CONTROL,
        variables=variables or [VariableSpec(name="x", initial=1.0)],
        parameters=[],
        equations=[EquationSpec(target="x", expression="0", kind="state_space")],
        metadata={"control": cfg},
    )


def _run_control(model, points=6):
    return adv._simulate_control(
        model, t_span=(0.0, 1.0), points=points, parameter_overrides=None, seed=0
    )


def test_control_configuration_errors():
    with pytest.raises(ValueError, match="metadata.control must be an object"):
        adv._simulate_control(
            _model(
                ModelFamily.CONTROL,
                variables=[VariableSpec(name="x", initial=1.0)],
                equations=[],
                metadata={"control": "bad"},
            ),
            t_span=(0.0, 1.0), points=4, parameter_overrides=None, seed=0,
        )
    with pytest.raises(ValueError, match="control.state_space must be an object"):
        _run_control(_control({"state_space": 5}))
    with pytest.raises(ValueError, match="control state-space matrix missing: B"):
        _run_control(_control({"A": [[-1.0]]}))
    with pytest.raises(ValueError, match="control A must be square"):
        _run_control(_control({"A": [[1.0, 0.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]]}))
    with pytest.raises(ValueError, match="needs 1 state variables"):
        _run_control(
            _control(
                {"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]], "input": 0.0},
                variables=[VariableSpec(name="z", role="latent")],
            )
        )


def test_control_input_shapes_and_vector_output_matrix():
    # D given as a 1-D vector is reshaped onto the output matrix.
    vector_d = _control({"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [0.0], "input": 0.0})
    out = _run_control(vector_d)
    assert out["status"] == "PASS"
    assert out["outputs"]["y0"][-1] == pytest.approx(np.exp(-1.0), rel=2e-3)

    # Dict input without a time base uses the raw values array.
    no_time = _control({"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
                        "input": {"values": 0.0}})
    assert _run_control(no_time)["status"] == "PASS"

    # Per-sample input vector is reshaped when it matches the time length.
    samples = _control({"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
                        "input": {"values": [0.0] * 6}})
    out = _run_control(samples)
    assert out["status"] == "PASS"

    # Single-input vector is tiled across time.
    tiled = _control({"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
                      "input": {"values": [0.0]}})
    assert _run_control(tiled)["status"] == "PASS"

    ambiguous = _control({"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
                          "input": {"values": [0.0, 0.0]}})
    with pytest.raises(ValueError, match="input vector shape is ambiguous"):
        _run_control(ambiguous)

    wrong_shape = _control({"A": [[-1.0]], "B": [[0.0]], "C": [[1.0]], "D": [[0.0]],
                            "input": [[0.0, 0.0]] * 6})
    with pytest.raises(ValueError, match="input must have shape"):
        _run_control(wrong_shape)


def test_control_multistate_input_time_and_default_outputs():
    model = _control(
        {
            "A": [[-1.0, 0.0], [0.0, -2.0]],
            "B": [[0.0], [0.0]],
            "C": [[1.0, 1.0]],
            "D": [[0.0]],
            "input": {"time": [0.0, 1.0], "values": [[0.0], [1.0]]},
        },
        variables=[
            VariableSpec(name="x1", initial=1.0),
            VariableSpec(name="x2", initial=0.0),
        ],
    )
    out = _run_control(model)
    assert out["status"] == "PASS"
    assert list(out["outputs"]) == ["y0"]
    assert len(out["outputs"]["y0"]) == 6
    assert np.asarray(out["states"]["x1"]).shape == (6,)
    assert out["diagnostics"]["stability"] == "stable"


def test_control_multi_output_matrix_keeps_declared_names():
    model = _control(
        {
            "A": [[-1.0, 0.0], [0.0, -2.0]],
            "B": [[0.0], [0.0]],
            "C": [[1.0, 0.0], [0.0, 1.0]],
            "D": [[0.0], [0.0]],
            "input": 0.0,
        },
        variables=[
            VariableSpec(name="x1", initial=1.0),
            VariableSpec(name="x2", initial=0.5),
            VariableSpec(name="meas1", role="output"),
            VariableSpec(name="meas2", role="output"),
        ],
    )
    out = _run_control(model)
    assert out["status"] == "PASS"
    assert list(out["outputs"]) == ["meas1", "meas2"]
    assert np.asarray(out["outputs"]["meas1"]).shape == (6,)
    assert np.asarray(out["outputs"]["meas1"])[-1] == pytest.approx(math.exp(-1.0), rel=5e-3)
    assert np.asarray(out["outputs"]["meas2"])[-1] == pytest.approx(0.5 * math.exp(-2.0), rel=5e-3)


def _network(metadata, *, variables=None, equations=None) -> ModelIR:
    return _model(
        ModelFamily.NETWORK,
        variables=variables or [VariableSpec(name="x", initial=1.0)],
        parameters=[ParameterSpec(name="k", value=1.0)],
        equations=equations or [EquationSpec(target="x", expression="-x", kind="derivative")],
        metadata=metadata,
    )


def _run_network(model, points=5):
    return adv._simulate_network(
        model, t_span=(0.0, 0.5), points=points, parameter_overrides=None, seed=0
    )


def test_network_config_and_state_requirements():
    with pytest.raises(ValueError, match="metadata.network must be an object"):
        _run_network(_network({"network": "bad"}))
    with pytest.raises(ValueError, match="requires state variables"):
        _run_network(
            _model(
                ModelFamily.NETWORK,
                variables=[],
                equations=[],
                metadata={"network": {"nodes": ["a"], "edges": []}},
            )
        )


def test_network_duplicate_edge_discovery_and_scalar_initial():
    model = _network(
        {
            "network": {
                "nodes": None,
                "edges": [
                    {"source": "a", "target": "b"},
                    {"source": "a", "target": "c"},
                ],
            }
        }
    )
    out = _run_network(model)
    assert out["status"] == "PASS"
    assert out["coordinates"]["node"] == ["a", "b", "c"]
    assert out["diagnostics"]["nodes"] == 3
    assert np.asarray(out["states"]["x"]).shape == (5, 3)
    assert np.asarray(out["states"]["x"])[0].tolist() == [1.0, 1.0, 1.0]


def test_network_missing_initial_value_raises():
    model = _network(
        {"network": {"nodes": ["a"], "edges": []}},
        variables=[VariableSpec(name="x")],
    )
    with pytest.raises(ValueError, match="needs an initial value"):
        _run_network(model)
