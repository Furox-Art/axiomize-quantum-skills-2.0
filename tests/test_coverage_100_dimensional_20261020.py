"""Coverage hardening for equation-level dimensional analysis."""

from __future__ import annotations

import ast

import pytest

from axiomize import dimensional_engine
from axiomize.dimensional_engine import (
    _parse_dimension,
    _register_advanced_symbols,
    equation_dimension_checks,
    merge_dimension_checks,
)
from axiomize.model_ir import (
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    VariableSpec,
)


def _model(**overrides):
    values = {
        "name": "dim",
        "domain": "test",
        "family": ModelFamily.ALGEBRAIC,
        "variables": [VariableSpec(name="x", unit="m")],
        "parameters": [],
        "equations": [],
        "independent_variable": "t",
        "independent_unit": "s",
        "metadata": {},
    }
    values.update(overrides)
    return ModelIR(**values)


def test_parse_dimension_basic_operations():
    dims = {"x": {"L": 1.0}, "t": {"T": 1.0}}
    assert _parse_dimension("1", dims) == {}
    assert _parse_dimension("x", dims) == {"L": 1.0}
    assert _parse_dimension("-x", dims) == {"L": 1.0}
    assert _parse_dimension("x + x", dims) == {"L": 1.0}
    assert _parse_dimension("x * t", dims) == {"L": 1.0, "T": 1.0}
    assert _parse_dimension("x / t", dims) == {"L": 1.0, "T": -1.0}
    assert _parse_dimension("x ** 2", dims) == {"L": 2.0}
    assert _parse_dimension("x ** 0", dims) == {}
    assert _parse_dimension("Abs(x)", dims) == {"L": 1.0}
    assert _parse_dimension("Min(x, x)", dims) == {"L": 1.0}
    assert _parse_dimension("Max(x, x)", dims) == {"L": 1.0}
    assert _parse_dimension("sqrt(x)", dims) == {"L": 0.5}
    assert _parse_dimension("sin(x / x)", dims) == {}
    assert _parse_dimension("Heaviside(1)", dims) == {}


def test_parse_dimension_rejections():
    dims = {"x": {"L": 1.0}, "t": {"T": 1.0}}
    with pytest.raises(ValueError, match="only numeric constants"):
        _parse_dimension("True", dims)
    with pytest.raises(ValueError, match="unknown symbol"):
        _parse_dimension("sin", dims)
    with pytest.raises(ValueError, match="additive dimension mismatch"):
        _parse_dimension("x + t", dims)
    with pytest.raises(ValueError, match="dimensional exponent is invalid"):
        _parse_dimension("x ** t", dims)
    with pytest.raises(ValueError, match="exponent must be a numeric constant"):
        _parse_dimension("x ** (1 + 1)", dims)
    with pytest.raises(ValueError, match="Abs expects one argument"):
        _parse_dimension("Abs(x, x)", dims)
    with pytest.raises(ValueError, match="Min arguments must have equal dimensions"):
        _parse_dimension("Min(x, t)", dims)
    with pytest.raises(ValueError, match="sqrt expects one argument"):
        _parse_dimension("sqrt(x, x)", dims)
    with pytest.raises(ValueError, match="requires dimensionless arguments"):
        _parse_dimension("sin(x)", dims)
    with pytest.raises(ValueError, match="unsupported syntax Tuple"):
        _parse_dimension("(x, t)", dims)


def test_parse_dimension_defensive_operator_and_function(monkeypatch):
    def fake_validate(expression, *, allowed_names, allowed_functions):
        return ast.parse(expression, mode="eval")

    monkeypatch.setattr(dimensional_engine, "validate_expression", fake_validate)
    with pytest.raises(ValueError, match="unsupported operator BitOr"):
        _parse_dimension("x | t", {"x": {"L": 1.0}, "t": {"T": 1.0}})
    with pytest.raises(ValueError, match="unsupported function in dimensional expression"):
        _parse_dimension("x.sin(t)", {"x": {"L": 1.0}, "t": {"T": 1.0}})


def test_register_advanced_symbols_network_and_agent():
    network = _model(
        family=ModelFamily.NETWORK,
        variables=[VariableSpec(name="x", unit="m")],
    )
    dimensions, units = {"x": {"L": 1.0}}, {"x": "m"}
    _register_advanced_symbols(network, dimensions, units)
    assert dimensions["mean_x"] == {"L": 1.0}
    assert dimensions["neighbor_x_sum"] == {"L": 1.0}
    assert dimensions["neighbor_x_mean"] == {"L": 1.0}
    assert dimensions["laplacian_x"] == {"L": 1.0}
    assert dimensions["degree"] == {}
    assert units["degree"] == "dimensionless"
    assert units["neighbor_x_mean"] == "m"

    agent = _model(
        family=ModelFamily.AGENT_BASED,
        variables=[VariableSpec(name="x", unit="m")],
    )
    dimensions, units = {"x": {"L": 1.0}}, {"x": "m"}
    _register_advanced_symbols(agent, dimensions, units)
    assert "mean_x" in dimensions
    assert "degree" not in dimensions
    assert "neighbor_x_sum" not in dimensions


def test_register_advanced_symbols_declared_and_bayesian():
    model = _model(
        family=ModelFamily.BAYESIAN,
        metadata={
            "symbol_units": {"alpha": "m/s"},
            "bayesian": {
                "data": {"x": {}, "y": {}, "z": {}},
                "data_units": {"y": "kg"},
            },
        },
    )
    dimensions = {"x": {"L": 1.0}}
    units = {"x": "m"}
    _register_advanced_symbols(model, dimensions, units)
    assert dimensions["alpha"] == {"L": 1.0, "T": -1.0}
    assert units["alpha"] == "m/s"
    assert dimensions["y"] == {"M": 1.0}
    assert units["y"] == "kg"
    assert dimensions["z"] == {}
    assert units["z"] == "dimensionless"

    no_units = _model(
        family=ModelFamily.BAYESIAN,
        metadata={"bayesian": {"data": {"q": [1]}, "data_units": "kg"}},
    )
    dimensions, units = {}, {}
    _register_advanced_symbols(no_units, dimensions, units)
    assert dimensions["q"] == {}
    assert units["q"] == "dimensionless"

    malformed = _model(family=ModelFamily.BAYESIAN, metadata={"bayesian": [], "symbol_units": []})
    dimensions, units = {}, {}
    _register_advanced_symbols(malformed, dimensions, units)
    assert dimensions == {} and units == {}

    non_dict_data = _model(
        family=ModelFamily.BAYESIAN,
        metadata={"bayesian": {"data": "nope", "data_units": {"q": "kg"}}},
    )
    dimensions, units = {}, {}
    _register_advanced_symbols(non_dict_data, dimensions, units)
    assert dimensions == {} and units == {}


def test_equation_dimension_checks_pass_and_fail():
    model = _model(
        variables=[VariableSpec(name="x", unit="m")],
        parameters=[ParameterSpec(name="k", unit="kg")],
        equations=[
            EquationSpec(target="x", expression="x", kind="algebraic"),
            EquationSpec(target="x", expression="x / t", kind="derivative"),
            EquationSpec(target="x", expression="x", kind="algebraic", unit="m"),
            EquationSpec(target="", expression="1", kind="residual"),
        ],
    )
    checks = equation_dimension_checks(model)
    assert checks[0]["status"] == "PASS"
    assert checks[1]["status"] == "PASS"
    assert checks[2]["status"] == "PASS"
    assert checks[3]["status"] == "UNVERIFIED"

    failing = _model(
        equations=[
            EquationSpec(target="x", expression="x + t", kind="algebraic"),
            EquationSpec(target="missing", expression="1", kind="derivative"),
            EquationSpec(target="missing", expression="1", kind="algebraic"),
        ]
    )
    checks = equation_dimension_checks(failing)
    assert all(check["status"] == "FAIL" for check in checks)
    assert "unknown derivative target" in checks[1]["detail"]
    assert "unknown target" in checks[2]["detail"]


def test_merge_dimension_checks_marks_failure():
    model = _model(equations=[EquationSpec(target="x", expression="x", kind="algebraic")])
    merged = merge_dimension_checks({"status": "PASS", "checks": [{"status": "PASS"}]}, model)
    assert merged["status"] == "PASS"
    assert len(merged["checks"]) == 2
    assert merged["equation_dimension_checks"][0]["status"] == "PASS"

    bad = _model(equations=[EquationSpec(target="x", expression="x + t", kind="algebraic")])
    merged = merge_dimension_checks({"status": "PASS", "checks": []}, bad)
    assert merged["status"] == "FAIL"
