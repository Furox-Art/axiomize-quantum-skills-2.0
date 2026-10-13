"""Regression coverage for C1: hardened expression parsing in the JAX tool.

``JAXTool`` used to parse its ``function`` argument with
``sympy.sympify(function_expr)``.  ``sympify`` *evaluates* its string
argument, so a tool-supplied expression could execute arbitrary Python.  The
tool now parses through :mod:`axiomize.safe_expression` -- the same hardened
parser the rest of the tool surface uses -- and does so before the availability
gate, so hostile text is rejected as a ``ValueError`` with or without JAX
installed.
"""

from __future__ import annotations

import pytest

from axiomize.tools.autodiff.jax_tool import JAXTool
from axiomize.tools.symbolic.sympy_tool import simplify_expr


def test_jax_tool_rejects_the_sympify_execution_payload() -> None:
    """The payload shape that previously reached an evaluating parser.

    ``sympy.sympify`` evaluates its string argument, so
    ``__import__('os').getcwd()`` used to execute during parsing.  The tool
    must reject it as a ``ValueError`` before the availability gate, meaning
    the rejection holds with or without JAX installed.
    """
    tool = JAXTool()
    with pytest.raises(ValueError, match="unapproved mathematical functions|unknown symbol|unsupported expression"):
        tool.execute({"x": 1.0, "function": "__import__('os').getcwd()"})


def test_jax_tool_expression_cannot_create_a_file(tmp_path, monkeypatch) -> None:
    """The same proof with an observable side effect instead of a return value.

    ``open('canary.txt', 'w')`` is a call expression an evaluating parser
    executes: the file appears.  The hardened parser refuses it, so no file is
    ever created and the error is a plain ValueError, not a backend error.
    """
    monkeypatch.chdir(tmp_path)
    tool = JAXTool()
    with pytest.raises(ValueError, match="unapproved mathematical functions"):
        tool.execute({"x": 1.0, "operation": "grad", "function": "open('canary.txt','w')"})
    assert not (tmp_path / "canary.txt").exists(), "the payload must not execute"


def test_sympify_itself_still_evaluates_the_payload_shape_so_the_guard_matters(tmp_path, monkeypatch) -> None:
    """Document the hazard: why the tool must not hand text to sympify.

    This exercises sympy directly (not the tool) to prove the payload shape is
    genuinely executable under an evaluating parser.  If a future sympy makes
    sympify inert this test fails loudly and the C1 guard can be revisited.
    """
    pytest.importorskip("sympy")
    monkeypatch.chdir(tmp_path)
    import sympy

    sympy.sympify("open('canary.txt','w')")
    assert (tmp_path / "canary.txt").exists()


def test_parsed_function_accepts_benign_expressions_and_rejects_extra_symbols() -> None:
    from axiomize.tools.autodiff.jax_tool import _parsed_function

    symbols, expr = _parsed_function("x**2")
    assert set(symbols) == {"x"}
    assert expr.free_symbols == {symbols["x"]}

    # A constant expression stays accepted, as it was before the hardening.
    symbols, expr = _parsed_function("5")
    assert expr.free_symbols == set()

    for benign in ("sin(x)", "exp(-x) + 1", "sqrt(Abs(x)) / 2"):
        symbols, expr = _parsed_function(benign)
        assert expr.free_symbols <= {symbols["x"]}

    with pytest.raises(ValueError, match="depend on x only"):
        _parsed_function("x**2 + y")


def test_sympy_tool_still_uses_the_hardened_parser_for_user_text() -> None:
    """The shared tool surface keeps its existing safe behaviour."""
    assert simplify_expr("x + x") == "2*x"
    with pytest.raises(ValueError):
        simplify_expr("__import__('os').getcwd()")
