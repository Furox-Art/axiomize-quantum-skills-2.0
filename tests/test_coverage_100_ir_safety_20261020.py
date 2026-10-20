"""Coverage hardening for Model IR validation and safe-expression parsing."""

from __future__ import annotations

import ast
import math

import pytest

from axiomize import model_ir
from axiomize.model_ir import (
    ConstraintSpec,
    EquationSpec,
    ModelFamily,
    ModelIR,
    ParameterSpec,
    ProvenanceEvent,
    SolverSpec,
    VariableSpec,
    migrate_payload,
    migration_preview,
)
from axiomize.safe_expression import (
    _check_constant,
    _constant_number,
    _to_sympy,
    auto_symbol_map,
    sympy_expression,
    validate_expression,
)


BASE = {
    "schema_version": "1.0",
    "name": "demo",
    "domain": "test",
    "family": "algebraic",
    "variables": [{"name": "x"}],
    "equations": [{"target": "x", "expression": "1", "kind": "algebraic"}],
}


def _payload(**overrides):
    payload = dict(BASE)
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Model IR
# ---------------------------------------------------------------------------

def test_model_family_aliases_and_error():
    assert ModelFamily.parse("SDE") is ModelFamily.STOCHASTIC
    assert ModelFamily.parse("abm") is ModelFamily.AGENT_BASED
    assert ModelFamily.parse("des") is ModelFamily.DISCRETE_EVENT
    assert ModelFamily.parse("differential-algebraic") is ModelFamily.DAE
    assert ModelFamily.parse("multi-physics") is ModelFamily.MULTIPHYSICS
    assert ModelFamily.parse("coupled_physics") is ModelFamily.MULTIPHYSICS
    with pytest.raises(ValueError, match="unsupported model family"):
        ModelFamily.parse("nonsense")


def test_finite_rejects_non_numeric_and_non_finite():
    with pytest.raises(ValueError, match="must be numeric"):
        model_ir._finite(object(), name="value")
    with pytest.raises(ValueError, match="must be finite"):
        model_ir._finite(float("inf"), name="value")


def test_bounds_validation():
    assert model_ir._bounds(None, name="x") is None
    with pytest.raises(ValueError, match="must have length 2"):
        model_ir._bounds([1, 2, 3], name="x")
    with pytest.raises(ValueError, match="lower bound must be <="):
        model_ir._bounds([3, 1], name="x")
    assert model_ir._bounds([None, 5], name="x") == (None, 5.0)


def test_bounded_list_limits():
    assert model_ir._bounded_list(None, name="v", maximum=2) == []
    with pytest.raises(ValueError, match="must be an array"):
        model_ir._bounded_list("abc", name="v", maximum=2)
    with pytest.raises(ValueError, match="exceeds hard safety limit"):
        model_ir._bounded_list([1, 2, 3], name="v", maximum=2)


def test_model_ir_payload_type_errors():
    with pytest.raises(ValueError, match="must be an object"):
        ModelIR.from_dict(["not", "a", "dict"])
    with pytest.raises(ValueError, match="variables must be an array"):
        ModelIR.from_dict(_payload(variables="x"))
    with pytest.raises(ValueError, match="exceeds hard safety limit"):
        ModelIR.from_dict(_payload(variables=[{"name": f"x{i}"} for i in range(1001)]))
    with pytest.raises(ValueError, match="boundary_conditions must be an object"):
        ModelIR.from_dict(_payload(boundary_conditions=[]))
    with pytest.raises(ValueError, match="validity_domain must be an object"):
        ModelIR.from_dict(_payload(validity_domain=[]))
    with pytest.raises(ValueError, match="metadata must be an object"):
        ModelIR.from_dict(_payload(metadata=[]))
    with pytest.raises(ValueError, match="provenance must be an array"):
        ModelIR.from_dict(_payload(provenance={}))
    with pytest.raises(ValueError, match="assumptions must be an array"):
        ModelIR.from_dict(_payload(assumptions={}))


def test_variable_spec_validation():
    with pytest.raises(ValueError, match="variable entry must be an object"):
        VariableSpec.from_dict("x")
    with pytest.raises(ValueError, match="unsupported role"):
        VariableSpec.from_dict({"name": "x", "role": "mystery"})
    with pytest.raises(ValueError, match="initial must be numeric"):
        VariableSpec.from_dict({"name": "x", "initial": object()})
    with pytest.raises(ValueError, match="initial must be finite"):
        VariableSpec.from_dict({"name": "x", "initial": float("nan")})
    with pytest.raises(ValueError, match="bounds must have length 2"):
        VariableSpec.from_dict({"name": "x", "bounds": [0]})
    parsed = VariableSpec.from_dict({"name": "x", "initial": 1, "bounds": [0, 2]})
    assert parsed.initial == 1.0 and parsed.bounds == (0.0, 2.0)


def test_parameter_spec_validation():
    with pytest.raises(ValueError, match="parameter entry must be an object"):
        ParameterSpec.from_dict(3)
    with pytest.raises(ValueError, match="prior must be an object"):
        ParameterSpec.from_dict({"name": "k", "prior": [1]})
    with pytest.raises(ValueError, match="value must be finite"):
        ParameterSpec.from_dict({"name": "k", "value": float("inf")})
    parsed = ParameterSpec.from_dict({"name": "k", "value": 2, "prior": {"dist": "normal"}})
    assert parsed.value == 2.0 and parsed.prior == {"dist": "normal"}


def test_equation_spec_validation():
    with pytest.raises(ValueError, match="equation entry must be an object"):
        EquationSpec.from_dict(None)
    with pytest.raises(ValueError, match="expression must be non-empty"):
        EquationSpec.from_dict({"target": "x", "expression": " "})
    with pytest.raises(ValueError, match="unsupported equation kind"):
        EquationSpec.from_dict({"target": "x", "expression": "1", "kind": "magic"})
    with pytest.raises(ValueError, match="requires a target"):
        EquationSpec.from_dict({"expression": "1", "kind": "derivative"})
    spec = EquationSpec.from_dict({"expression": "x - 1", "kind": "residual"})
    assert spec.target == "" and spec.kind == "residual"


def test_constraint_spec_validation():
    with pytest.raises(ValueError, match="constraint entry must be an object"):
        ConstraintSpec.from_dict("x >= 1")
    with pytest.raises(ValueError, match="unsupported constraint relation"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "relation": "gt"})
    with pytest.raises(ValueError, match="unsupported constraint severity"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "severity": "fatal"})
    with pytest.raises(ValueError, match="tolerance must be non-negative"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "tolerance": -1})
    with pytest.raises(ValueError, match="requires upper"):
        ConstraintSpec.from_dict({"name": "c", "expression": "x", "relation": "between"})
    with pytest.raises(ValueError, match="upper must be >="):
        ConstraintSpec.from_dict(
            {"name": "c", "expression": "x", "relation": "between", "threshold": 5, "upper": 1}
        )
    with pytest.raises(ValueError, match="expression must be non-empty"):
        ConstraintSpec.from_dict({"name": "c", "expression": ""})
    spec = ConstraintSpec.from_dict(
        {"name": "c", "expression": "x", "relation": "between", "threshold": 1, "upper": 2}
    )
    assert spec.upper == 2.0


def test_solver_spec_validation():
    with pytest.raises(ValueError, match="solver must be an object"):
        SolverSpec.from_dict("fast")
    with pytest.raises(ValueError, match="rtol and atol must be positive"):
        SolverSpec.from_dict({"rtol": 0})
    with pytest.raises(ValueError, match="max_steps must be positive"):
        SolverSpec.from_dict({"max_steps": 0})
    with pytest.raises(ValueError, match="fallbacks must be an array"):
        SolverSpec.from_dict({"fallbacks": "rk45"})
    with pytest.raises(ValueError, match="at most 32 entries"):
        SolverSpec.from_dict({"fallbacks": ["a"] * 33})
    parsed = SolverSpec.from_dict({"fallbacks": ["rk45", "bdf"]})
    assert parsed.fallbacks == ("rk45", "bdf")


def test_provenance_event_validation():
    with pytest.raises(ValueError, match="provenance event must be an object"):
        ProvenanceEvent.from_dict("event")
    with pytest.raises(ValueError, match="provenance detail must be an object"):
        ProvenanceEvent.from_dict({"action": "x", "detail": []})
    event = ProvenanceEvent.from_dict({"action": "created", "detail": {"by": "test"}})
    assert event.detail == {"by": "test"}


def test_legacy_migration_preview_and_payload():
    preview = migration_preview({"schema_version": "0.9", "model_family": "ode", "states": {}, "rhs": {}})
    assert preview["required"] and preview["supported"]
    assert "rename model_family -> family" in preview["changes"]
    assert migration_preview({"schema_version": "2.0"})["supported"] is False
    assert migration_preview({"schema_version": "1.0"})["required"] is False

    migrated = migrate_payload(
        {
            "schema_version": "0.9",
            "model_family": "ode",
            "states": {"x": {"initial": 1}},
            "rhs": {"x": "-x"},
        },
        allow_migration=True,
    )
    assert migrated["family"] == "ode"
    assert migrated["variables"] == [{"name": "x", "initial": 1}]
    assert migrated["equations"] == [{"target": "x", "expression": "-x", "kind": "derivative"}]
    assert migrated["schema_version"] == model_ir.CURRENT_SCHEMA_VERSION
    assert migrated["provenance"][-1]["action"] == "model_ir_migration"

    migrated_list = migrate_payload(
        {"schema_version": "0.9", "states": ["x"], "family": "algebraic", "equations": []},
        allow_migration=True,
    )
    assert migrated_list["variables"] == ["x"]

    with pytest.raises(ValueError, match="legacy rhs must be a mapping"):
        migrate_payload(
            {"schema_version": "0.9", "rhs": ["x"], "family": "ode", "variables": []},
            allow_migration=True,
        )


def test_model_ir_end_to_end_roundtrip():
    model = ModelIR.from_dict(_payload())
    assert model.family is ModelFamily.ALGEBRAIC
    assert model.to_dict()["family"] == "algebraic"


# ---------------------------------------------------------------------------
# Safe expression parsing
# ---------------------------------------------------------------------------

def test_check_constant_rejects_huge_integer():
    with pytest.raises(ValueError, match="integer literal exceeds"):
        _check_constant(10 ** 64)
    _check_constant(True)
    _check_constant(1.5)


def test_constant_number_arithmetic_and_errors():
    def node(expression):
        return ast.parse(expression, mode="eval").body

    assert _constant_number(node("-2")) == -2.0
    assert _constant_number(node("+2")) == 2.0
    assert _constant_number(node("1 - 3")) == -2.0
    assert _constant_number(node("1 / 2")) == 0.5
    assert _constant_number(node("5 % 2")) == 1.0
    assert _constant_number(node("2 ** 3")) == 8.0
    assert _constant_number(node("'text'")) is None
    assert _constant_number(node("True")) is None
    with pytest.raises(ValueError, match="invalid or unbounded constant exponent"):
        _constant_number(node("1 / 0"))
    with pytest.raises(ValueError, match="invalid or unbounded constant exponent"):
        _constant_number(node("10 ** 1000"))


def test_validate_expression_rejections():
    with pytest.raises(ValueError, match="expression must be a string"):
        validate_expression(5, allowed_names={"x"})
    assert validate_expression("x + 1", allowed_names={"x"}) is not None
    with pytest.raises(ValueError, match="hard limit"):
        validate_expression("x" * 9000, allowed_names={"x"})
    with pytest.raises(ValueError, match="invalid mathematical expression"):
        validate_expression("x +", allowed_names={"x"})
    with pytest.raises(ValueError, match="AST-node limit"):
        validate_expression("+".join(["x"] * 300), allowed_names={"x"})
    with pytest.raises(ValueError, match="nesting limit"):
        validate_expression("+" * 45 + "x", allowed_names={"x"})
    with pytest.raises(ValueError, match="too many arguments"):
        validate_expression("sin(" + ",".join(["x"] * 33) + ")", allowed_names={"x"})
    with pytest.raises(ValueError, match="constant exponent magnitude"):
        validate_expression("x ** 5000", allowed_names={"x"})
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        validate_expression("x", allowed_names={"x"}, allowed_functions={"evil"})


def test_to_sympy_defensive_branches():
    import sympy as sp

    symbols = {"x": sp.Symbol("x")}
    functions = {"sin": sp.sin}

    with pytest.raises(ValueError, match="unsupported constant"):
        _to_sympy(ast.Constant("text"), symbols, functions)
    with pytest.raises(ValueError, match="unknown symbol"):
        _to_sympy(ast.Name(id="y", ctx=ast.Load()), symbols, functions)
    with pytest.raises(ValueError, match="unsupported unary operator"):
        _to_sympy(ast.UnaryOp(op=ast.Invert(), operand=ast.Name(id="x", ctx=ast.Load())), symbols, functions)
    with pytest.raises(ValueError, match="unsupported binary operator"):
        _to_sympy(
            ast.BinOp(
                left=ast.Name(id="x", ctx=ast.Load()),
                op=ast.BitOr(),
                right=ast.Name(id="x", ctx=ast.Load()),
            ),
            symbols,
            functions,
        )
    with pytest.raises(ValueError, match="unsupported comparison operator"):
        _to_sympy(
            ast.Compare(
                left=ast.Name(id="x", ctx=ast.Load()),
                ops=[ast.In()],
                comparators=[ast.Name(id="x", ctx=ast.Load())],
            ),
            symbols,
            functions,
        )
    with pytest.raises(ValueError, match="unsupported boolean operator"):
        _to_sympy(
            ast.BoolOp(op=ast.Add(), values=[ast.Name(id="x", ctx=ast.Load())]),
            symbols,
            functions,
        )
    with pytest.raises(ValueError, match="unsupported expression syntax"):
        _to_sympy(ast.List(elts=[], ctx=ast.Load()), symbols, functions)

    assert _to_sympy(ast.parse("x + 1", mode="eval"), symbols, functions) == symbols["x"] + 1
    assert _to_sympy(ast.parse("+x", mode="eval"), symbols, functions) == symbols["x"]
    assert _to_sympy(ast.parse("x % 2", mode="eval"), symbols, functions) == sp.Mod(symbols["x"], 2)
    assert str(_to_sympy(ast.parse("x == 1", mode="eval"), symbols, functions)) == "Eq(x, 1)"
    assert str(_to_sympy(ast.parse("x != 1", mode="eval"), symbols, functions)) == "Ne(x, 1)"
    assert str(_to_sympy(ast.parse("x > 1", mode="eval"), symbols, functions)) == "x > 1"
    assert str(_to_sympy(ast.parse("x >= 1", mode="eval"), symbols, functions)) == "x >= 1"
    assert str(_to_sympy(ast.parse("x < 1", mode="eval"), symbols, functions)) == "x < 1"
    assert str(_to_sympy(ast.parse("x <= 1", mode="eval"), symbols, functions)) == "x <= 1"
    assert _to_sympy(ast.parse("x > 0 and x < 2", mode="eval"), symbols, functions) == sp.And(
        symbols["x"] > 0, symbols["x"] < 2
    )
    assert _to_sympy(ast.parse("x > 0 or x < -2", mode="eval"), symbols, functions) == sp.Or(
        symbols["x"] > 0, symbols["x"] < -2
    )
    assert _to_sympy(ast.parse("(x, 1)", mode="eval"), symbols, functions) == (symbols["x"], sp.Integer(1))
    assert _to_sympy(ast.parse("sin(x)", mode="eval"), symbols, functions) == sp.sin(symbols["x"])
    assert _to_sympy(ast.parse("True", mode="eval"), {}, {}) is sp.true
    assert _to_sympy(ast.parse("False", mode="eval"), {}, {}) is sp.false


def test_sympy_expression_rejects_top_level_tuple():
    import sympy as sp

    with pytest.raises(ValueError, match="cannot be a tuple"):
        sympy_expression("(x, 1)", {"x": sp.Symbol("x")})


def test_auto_symbol_map_validation():
    with pytest.raises(ValueError, match="expression must be a string"):
        auto_symbol_map(None)
    with pytest.raises(ValueError, match="hard limit"):
        auto_symbol_map("x" * 9000)
    with pytest.raises(ValueError, match="invalid mathematical expression"):
        auto_symbol_map("x +")
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        auto_symbol_map("evil(x)")
    with pytest.raises(ValueError, match="reserved implementation-style name"):
        auto_symbol_map("x__y + 1")
    mapping = auto_symbol_map("a + b * 2")
    assert set(mapping) == {"a", "b"}
    assert all(symbol.is_real for symbol in mapping.values())
