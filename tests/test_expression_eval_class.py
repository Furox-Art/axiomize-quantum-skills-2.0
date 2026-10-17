

"""No model expression reaches an evaluator, and the budgets are shared.

The 2.5.0/1.2.3 jax_tool fix closed code execution by delegating to
`safe_expression`. The engine core and the advanced-family engine kept their
own AST whitelists built around `sp.sympify(expr, locals=...)`, so an exponent
bomb or a deep expression still reached sympy's evaluator. These tests pin the
delegation in both places.
"""
from __future__ import annotations

import pytest
import sympy


def test_engine_core_power_bomb_is_rejected() -> None:
    from axiomize.general_engine_core import _sympy_expression
    with pytest.raises(ValueError):
        _sympy_expression("9**9**9**9", {"x": sympy.Symbol("x")})


def test_nested_constant_exponent_cannot_bypass_shared_budget() -> None:
    from axiomize.safe_expression import validate_expression

    for expression in ("9**9**9**9", "x**(9**9 + 0)", "x**(2**10)"):
        with pytest.raises(ValueError):
            validate_expression(expression, allowed_names={"x"})

    # Small nested constant exponents and symbolic powers remain valid.
    validate_expression("x**(2**3)", allowed_names={"x"})
    validate_expression("(x**2)**3", allowed_names={"x"})
    validate_expression("x**y", allowed_names={"x", "y"})


def test_engine_core_import_attempt_is_rejected() -> None:
    from axiomize.general_engine_core import _sympy_expression
    with pytest.raises(ValueError):
        _sympy_expression("__import__('os')", {"x": sympy.Symbol("x")})


def test_engine_core_normal_expression_still_parses() -> None:
    from axiomize.general_engine_core import _sympy_expression
    expr = _sympy_expression("2*x + y", {"x": sympy.Symbol("x"), "y": sympy.Symbol("y")})
    assert expr == 2 * sympy.Symbol("x") + sympy.Symbol("y")


def test_engine_core_delegates_to_safe_expression() -> None:
    from axiomize import general_engine_core
    assert general_engine_core.sympy_expression is not None
    assert general_engine_core.validate_expression is not None


def test_advanced_family_power_bomb_is_rejected() -> None:
    from axiomize.advanced_family_engine import _compile_expression
    with pytest.raises(ValueError):
        _compile_expression("9**9**9**9", ["x"])


def test_advanced_family_normal_expression_compiles() -> None:
    from axiomize.advanced_family_engine import _compile_expression
    fn = _compile_expression("x**2", ["x"])
    assert fn(3.0) == 9.0

def test_serve_fails_loud_on_empty_token_env(monkeypatch) -> None:
    """An empty auth env var must not silently disable authentication.

    `--auth-token-env` pointing at an empty value used to fall through the
    `or` chain, leaving the REST server without a token while the operator
    believed auth was on.
    """
    import argparse
    from axiomize import cli

    monkeypatch.setenv("AXIOMIZE_REST_TOKEN", "")
    monkeypatch.delenv("PLAN_AUDITOR_HMAC_KEY", raising=False)
    import axiomize.server.rest_server as rest_server
    called = {"n": 0}

    def fake_start_server(*args, **kwargs):
        called["n"] += 1
        raise AssertionError("server must not start")

    monkeypatch.setattr(rest_server, "start_server", fake_start_server)
    args = argparse.Namespace(
        host="127.0.0.1", port=0, run_root=None, allow_remote=False,
        auth_token=None, auth_token_env="AXIOMIZE_REST_TOKEN",
        max_concurrent_requests=1,
    )
    with pytest.raises(SystemExit):
        cli.cmd_serve(args)
    assert called["n"] == 0