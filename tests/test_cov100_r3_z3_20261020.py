"""Round-3 coverage completion for the Z3 constraint adapter."""

from __future__ import annotations

import ast
import math

import pytest
import z3

from axiomize.tools.logic import z3_tool
from axiomize.validation.status import ValidationStatus


def test_finite_number_rejects_non_numeric_value() -> None:
    with pytest.raises(ValueError, match="n must be numeric"):
        z3_tool._finite_number("not-a-number", name="n")


def test_parse_constraint_rejects_oversized_text() -> None:
    text = "x > 0" + " " * z3_tool.MAX_EXPRESSION_CHARS
    assert len(text) > z3_tool.MAX_EXPRESSION_CHARS
    with pytest.raises(ValueError, match="hard limit of 8192 characters"):
        z3_tool._parse_constraint(text, {})


def test_parse_constraint_rejects_invalid_syntax() -> None:
    with pytest.raises(ValueError, match="invalid Z3 constraint syntax"):
        z3_tool._parse_constraint("x >", {})


def test_parse_constraint_rejects_too_many_ast_nodes() -> None:
    text = "1" + "+1" * 300
    assert len(text) < z3_tool.MAX_EXPRESSION_CHARS
    with pytest.raises(ValueError, match="hard AST-node limit"):
        z3_tool._parse_constraint(text, {})


def test_parse_constraint_rejects_excessive_nesting() -> None:
    text = "-" * 41 + "1"
    with pytest.raises(ValueError, match="hard nesting limit"):
        z3_tool._parse_constraint(text, {})


def test_boolean_literal_constraint_is_satisfiable() -> None:
    result = z3_tool.check_constraints(["True"], {"x": (0.0, 1.0)})
    assert result["sat"] is True
    assert result["status"] is ValidationStatus.PASS
    assert 0.0 <= result["model"]["x"] <= 1.0


def test_string_constant_is_rejected() -> None:
    with pytest.raises(ValueError, match="real numeric or boolean constants"):
        z3_tool.check_constraints(['x == "text"'], {"x": (0.0, 1.0)})


def test_unary_plus_preserves_operand_value() -> None:
    result = z3_tool.check_constraints(["+x > 0"], {"x": (1.0, 2.0)})
    assert result["sat"] is True
    assert result["model"]["x"] > 0


def test_unsupported_unary_operator_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported unary operator: Invert"):
        z3_tool.check_constraints(["~x > 0"], {"x": (0.0, 1.0)})


def test_unsupported_comparison_operator_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported comparison operator: Is"):
        z3_tool.check_constraints(["x is x"], {"x": (0.0, 1.0)})


def test_malformed_comparison_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    tree = ast.Expression(
        body=ast.Compare(left=ast.Name(id="x"), ops=[ast.Lt()], comparators=[])
    )
    monkeypatch.setattr(z3_tool.ast, "parse", lambda *args, **kwargs: tree)
    with pytest.raises(ValueError, match="malformed comparison"):
        z3_tool.check_constraints(["x < 1"], {"x": (0.0, 1.0)})


def test_unsupported_boolean_operator_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    tree = ast.Expression(
        body=ast.BoolOp(
            op=ast.Add(),
            values=[ast.Name(id="x"), ast.Name(id="x")],
        )
    )
    monkeypatch.setattr(z3_tool.ast, "parse", lambda *args, **kwargs: tree)
    with pytest.raises(ValueError, match="unsupported boolean operator: Add"):
        z3_tool.check_constraints(["x and x"], {"x": (0.0, 1.0)})


def test_algebraic_model_value_is_converted_to_float() -> None:
    result = z3_tool.check_constraints(["x**2 == 2"], {"x": (0.0, 2.0)})
    assert result["sat"] is True
    assert result["status"] is ValidationStatus.PASS
    assert result["model"]["x"] == pytest.approx(math.sqrt(2), rel=1e-12)


def test_unknown_solver_verdict_is_inconclusive(monkeypatch: pytest.MonkeyPatch) -> None:
    real_solver = z3.Solver

    class ForcedUnknownSolver:
        def __init__(self, *args, **kwargs):
            self._inner = real_solver(*args, **kwargs)

        def __getattr__(self, item):
            return getattr(self._inner, item)

        def check(self):
            return z3.unknown

        def reason_unknown(self):
            return "forced-unknown-for-test"

    monkeypatch.setattr(z3, "Solver", ForcedUnknownSolver)
    result = z3_tool.check_constraints(["x > 0"], {"x": (0.0, 1.0)})
    assert result["sat"] is None
    assert result["model"] is None
    assert result["status"] is ValidationStatus.INCONCLUSIVE
    assert result["reason"] == "forced-unknown-for-test"
