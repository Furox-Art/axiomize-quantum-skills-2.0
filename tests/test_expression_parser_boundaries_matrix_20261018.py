"""Adversarial AST, SymPy translation and bounded constant folding contracts."""

from __future__ import annotations

import ast

import pytest
import sympy as sp

from axiomize import safe_expression as safe


def integer_tree(text):
    return ast.parse(text, mode="eval").body


@pytest.mark.parametrize("name, pattern", [
    ("_internal", "ASCII letter"),
    ("x__y", "reserved implementation-style"),
    ("sin", "reserved mathematical"),
    ("None", "reserved mathematical"),
    ("name with spaces", "ASCII letter"),
    ("a.b", "ASCII letter"),
])
def test_symbol_namespace_has_no_implementation_shadowing(name, pattern):
    with pytest.raises(ValueError, match=pattern):
        safe.validate_identifier(name)


@pytest.mark.parametrize("expression, pattern", [
    ("", "non-empty"),
    ("x.__class__", "unsupported expression syntax"),
    ("__import__(\"os\")", "reserved implementation-style|approved"),
    ("x[0]", "unsupported expression syntax"),
    ("(lambda x: x)(3)", "only approved mathematical"),
    ("x if x>0 else 0", "unsupported expression syntax"),
    ("x < 1 < 2", "chained comparisons"),
    ("sin(x=3)", "keyword arguments"),
    ("Piecewise()", "requires at least one"),
    ("Piecewise(x)", "arguments must be"),
    ("unknown+1", "unknown symbol"),
    ("eval(x)", "only approved mathematical"),
    ("1+2j", "only real numeric"),
])
def test_mathematical_input_refuses_host_language_execution(expression, pattern):
    with pytest.raises(ValueError, match=pattern):
        safe.validate_expression(expression, allowed_names={"x"})


def test_expression_evaluation_does_not_execute_python_builtins():
    x = sp.Symbol("x", real=True)
    e = safe.sympy_expression("x**2 + 2*x + 1", {"x": x})
    assert sp.simplify(e - (x + 1)**2) == 0
    with pytest.raises(ValueError):
        safe.sympy_expression("__import__(\"os\").system(\"true\")", {})


def test_piecewise_and_boolean_relations_translate_with_correct_domains():
    x = sp.Symbol("x", real=True)
    converted = safe.sympy_expression("Piecewise((x,x>=0),(-x,True))", {"x": x})
    assert converted.subs(x, -2) == 2
    assert converted.subs(x, 3) == 3
    assert safe.sympy_expression("x < 2", {"x": x}) == sp.Lt(x, 2)


def test_unknown_and_invalid_symbol_maps_do_not_invent_parameters():
    symbols = safe.auto_symbol_map("sin(x) + y**2")
    assert sorted(symbols) == ["x", "y"]
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        safe.auto_symbol_map("exec(x)")
    with pytest.raises(ValueError, match="expression must be a string"):
        safe.auto_symbol_map(None)


def test_top_level_tuple_is_not_equation():
    with pytest.raises(ValueError, match="top-level.*tuple"):
        safe.sympy_expression("(1,2)", {})


def test_non_numeric_constants_are_not_allowed():
    with pytest.raises(ValueError, match="real numeric"):
        safe.validate_expression("\"hello\"", allowed_names=set())
    with pytest.raises(ValueError, match="finite"):
        safe._check_constant(float("inf"))


def test_unsupported_function_namespace_cannot_be_enabled_by_caller():
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        safe.validate_expression("dangerous(x)", allowed_names={"x"}, allowed_functions={"dangerous"})


@pytest.mark.parametrize("text, expected", [
    ("2+3", 5.0),
    ("2*3", 6.0),
    ("3**3", 27.0),
    ("-4", -4.0),
    ("x+1", None),
])
def test_old_parser_bounded_numeric_exponent_folding(text, expected):
    assert safe._constant_number(integer_tree(text)) == expected


def test_old_parser_rejects_oversized_nested_exponent():
    with pytest.raises(ValueError, match="constant exponent magnitude exceeds|invalid or unbounded"):
        safe.validate_expression("x**(10**9)", allowed_names={"x"})
