"""Regression coverage for C2: the import-time patch table is explicit and fails loud.

``axiomize/__init__.py`` applies load-bearing runtime patches (hardened
expression compiler, engine guards, availability-aware solver selection, v120
service bindings).  A rename that missed its target used to leave the caller
on the unhardened path with no signal.  The patch surface is now an explicit
table (:data:`axiomize.v120_runtime._PATCH_SURFACE`,
:func:`axiomize.runtime_guard.install_hardened_compiler`) that is verified in
full before anything is rebound, so a broken surface raises at startup instead
of silently patching.
"""

from __future__ import annotations

import types

import pytest


def test_startup_applies_the_expected_runtime_patches() -> None:
    from axiomize import __version__, advanced_family_engine as afe, general_engine as ge

    assert afe._compile_expression is ge._compile_expression_hardened
    assert ge._AXIOMIZE_112_INSTALLED is True
    assert afe._estimate_causal.__module__ == "axiomize.causal_engine"
    assert getattr(ge._advanced_preflight, "__axiomize_runtime_guard__", False) is True
    assert __version__


def test_install_fails_loudly_when_the_patch_surface_is_broken() -> None:
    """A renamed engine attribute must not become a silent shadow patch."""
    from axiomize.runtime_guard import RuntimePatchError
    from axiomize.v120_runtime import install

    engine = types.SimpleNamespace(
        select_solver=lambda model: {},
        numerical_refinement=lambda **kwargs: {},
        export_model=lambda **kwargs: {},
        _simulate_once=lambda *a, **k: None,
        _validated_span=lambda span: span,
        _validated_points=lambda points, model=None: points,
        _core=types.SimpleNamespace(select_solver=lambda model: {}, export_model=lambda **kwargs: {}),
    )
    # The advanced engine calls ``_infer_bayesian`` as a global; if the patch
    # table still bound it, the engine would keep calling the unpatched
    # original.  A missing attribute must raise, not silently create one.
    advanced = types.SimpleNamespace(
        _estimate_causal=lambda *a, **k: {},
        _compile_expression=lambda *a, **k: None,
    )
    original_select_solver = engine.select_solver
    with pytest.raises(RuntimePatchError, match="_infer_bayesian"):
        install(engine, advanced)
    # Nothing was rebound: the failure is atomic, not a half-applied patch set.
    assert not hasattr(engine, "_AXIOMIZE_112_INSTALLED")
    assert engine.select_solver is original_select_solver


def test_v120_install_is_idempotent_on_the_real_surface() -> None:
    from axiomize import advanced_family_engine as afe
    from axiomize import general_engine as ge
    from axiomize.v120_runtime import install

    before = (ge.select_solver, ge.numerical_refinement, ge.export_model, afe._estimate_causal, afe._infer_bayesian)
    install(ge, afe)
    after = (ge.select_solver, ge.numerical_refinement, ge.export_model, afe._estimate_causal, afe._infer_bayesian)
    assert before == after


def test_install_hardened_compiler_rejects_broken_surfaces() -> None:
    from axiomize.runtime_guard import RuntimePatchError, install_hardened_compiler

    engine = types.SimpleNamespace(_compile_expression_hardened=lambda *a, **k: None)
    advanced = types.SimpleNamespace()
    with pytest.raises(RuntimePatchError, match="_compile_expression"):
        install_hardened_compiler(engine, advanced)

    engine = types.SimpleNamespace()
    advanced = types.SimpleNamespace(_compile_expression=lambda *a, **k: None)
    with pytest.raises(RuntimePatchError, match="_compile_expression_hardened"):
        install_hardened_compiler(engine, advanced)

    # Already installed: no rebinding, no error.
    shared = lambda *args, **kwargs: None  # noqa: E731 - local stand-in
    engine = types.SimpleNamespace(_compile_expression_hardened=shared)
    advanced = types.SimpleNamespace(_compile_expression=shared)
    install_hardened_compiler(engine, advanced)
    assert advanced._compile_expression is shared


def test_mcp_tool_registration_is_explicit_table_data() -> None:
    """The MCP surface is table data, and the table cannot silently go empty."""
    from axiomize.server import mcp_server

    assert isinstance(mcp_server._TOOL_SCHEMAS, dict)
    assert len(mcp_server._TOOL_SCHEMAS) == 34
    response = mcp_server.handle_message({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = {tool["name"] for tool in response["result"]["tools"]}
    assert len(names) == 34
    assert "axiomize.solve" in names
    assert mcp_server.list_tools(), "a zero-tool startup must be impossible"


def test_mcp_unknown_tool_returns_a_structured_error() -> None:
    from axiomize.server import mcp_server

    response = mcp_server.handle_message(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call",
         "params": {"name": "axiomize.not_a_tool", "arguments": {}}}
    )
    assert response["error"]["code"] == -32601
