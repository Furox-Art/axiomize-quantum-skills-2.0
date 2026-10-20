"""Round-3 coverage completion for transport, run bundles and workflow surfaces."""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiomize.runs import bundle
from axiomize.server import mcp_server
from axiomize.workflow import intake, policy


# --------------------------------------------------------------------------- #
# mcp_server
# --------------------------------------------------------------------------- #

def test_fit_model_logistic_dispatch() -> None:
    result = mcp_server.call_tool(
        "axiomize.fit_model",
        {"t": [0, 1, 2, 3, 4], "y": [1.0, 1.5, 2.6, 4.4, 7.3], "model": "logistic"},
    )
    assert "error" not in result
    assert result["success"] is True
    assert result["method"] == "bounded_least_squares"
    assert "params" in result


def test_select_tools_dispatch_returns_decision() -> None:
    result = mcp_server.call_tool("axiomize.select_tools", {"signals": ["ode"]})
    assert "error" not in result
    assert "problem_type" in result
    assert set(result) >= {"primary_tools", "verification_tools", "status"}


def test_list_tools_dispatch_returns_inventory() -> None:
    result = mcp_server.call_tool("axiomize.list_tools", {})
    assert "error" not in result
    assert isinstance(result["tools"], dict)
    assert result["tools"]["sympy"]["capabilities"]


def test_get_capabilities_dispatch_returns_contract() -> None:
    result = mcp_server.call_tool("axiomize.get_capabilities", {})
    assert "error" not in result
    assert "axiomize_version" in result
    assert isinstance(result, dict) and len(result) > 1


# --------------------------------------------------------------------------- #
# cli.cmd_serve
# --------------------------------------------------------------------------- #

def test_cmd_serve_prints_generated_token(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    from axiomize import cli
    from axiomize.server import rest_server

    class FakeServer:
        generated_token = "generated-secret"
        server_address = ("127.0.0.1", 4321)

        def __init__(self):
            self.closed = False

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            self.closed = True

    fake_server = FakeServer()

    def fake_start_server(host, port, **kwargs):
        assert host == "127.0.0.1"
        assert port == 0
        assert kwargs["auth_token"] is None
        return fake_server

    monkeypatch.setattr(rest_server, "start_server", fake_start_server)
    args = argparse.Namespace(
        auth_token_env=None,
        auth_token=None,
        host="127.0.0.1",
        port=0,
        run_root=".",
        allow_remote=False,
        max_concurrent_requests=4,
    )
    assert cli.cmd_serve(args) == 0
    captured = capsys.readouterr()
    assert "axiomize REST v1 on http://127.0.0.1:4321" in captured.out
    assert "generated-secret" in captured.err
    assert "Authorization: Bearer generated-secret" in captured.err
    assert fake_server.closed is True


# --------------------------------------------------------------------------- #
# runs/bundle
# --------------------------------------------------------------------------- #

def _write_zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)
    return path


def test_bundle_rejects_oversized_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bundle, "_MAX_MEMBER_BYTES", 4)
    archive = _write_zip(tmp_path / "big.zip", {"data.json": b"0123456789"})
    with pytest.raises(ValueError, match="exceeds hard size limit of 4 bytes"):
        bundle.inspect_bundle_members(archive)


def test_bundle_rejects_oversized_total(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bundle, "_MAX_TOTAL_BYTES", 4)
    archive = _write_zip(tmp_path / "total.zip", {"a.json": b"abc", "b.json": b"def"})
    with pytest.raises(ValueError, match="exceeds hard uncompressed limit of 4 bytes"):
        bundle.inspect_bundle_members(archive)


# --------------------------------------------------------------------------- #
# workflow/policy
# --------------------------------------------------------------------------- #

def test_rigor_parse_rejects_unknown_label() -> None:
    with pytest.raises(ValueError, match="rigor must be weak/medium/strong"):
        policy.RigorLevel.parse("extreme")


def test_permissions_allow_unlisted_action_without_approval() -> None:
    permissions = policy.ExecutionPermissions()
    assert permissions.requires_approval("read_public_dataset") is False
    assert permissions.requires_approval("spawn_subtask") is True


def test_single_escalation_signal_recommends_medium_with_reasons() -> None:
    recommendation = policy.recommend_rigor({"high_stakes": True})
    assert recommendation["level"] == "medium"
    assert recommendation["reasons"] == [
        "high-stakes consequence",
        "one escalation signal is present; medium keeps cost bounded while adding checks",
    ]


# --------------------------------------------------------------------------- #
# workflow/intake
# --------------------------------------------------------------------------- #

def test_non_string_context_value_counts_as_answered() -> None:
    response = intake.build_intake_response({"idea": "model a pendulum", "context": {"goal": 42}})
    fields = [question["field"] for question in response["questions"]]
    assert "goal" not in fields
    assert response["status"] == "NEEDS_INPUT"
    assert response["mechanism_uncertain"] is True


# --------------------------------------------------------------------------- #
# tools/__init__ package path extension
# --------------------------------------------------------------------------- #

def test_tools_package_path_is_not_extended_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    import axiomize.tools as tools_package

    module_path = Path(tools_package.__file__).resolve()
    source_dir = str(module_path.parent)
    skill_dir = str(module_path.parents[3] / "skills" / "axiomize" / "tools")
    assert Path(skill_dir).is_dir()

    spec = importlib.util.spec_from_file_location(
        "axiomize_tools_path_probe_r3",
        module_path,
        submodule_search_locations=[source_dir, skill_dir],
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)

    assert list(module.__path__) == [source_dir, skill_dir]
    assert module.__file__ == str(module_path)


# --------------------------------------------------------------------------- #
# portable_export_compat
# --------------------------------------------------------------------------- #

def test_notebook_schema_alias_handles_optional_metadata_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiomize import portable_export_compat, standards_export

    payloads = {
        "a": {"notebook": {"metadata": {}}},
        "b": {"notebook": "raw-not-a-dict"},
        "c": {"notebook": {"metadata": []}},
        "d": {"notebook": {"metadata": {"axiomize": []}}},
        "e": {"notebook": {"metadata": {"axiomize": {}}}},
    }
    calls: list[str] = []

    def fake_export(model):
        calls.append(model.key)
        return copy.deepcopy(payloads[model.key])

    monkeypatch.setattr(standards_export, "export_notebook", fake_export)
    portable_export_compat.install_notebook_schema_alias()
    wrapper = standards_export.export_notebook
    assert wrapper is not fake_export
    assert calls == []

    out_a = wrapper(SimpleNamespace(key="a", schema_version=7))
    metadata_a = out_a["notebook"]["metadata"]["axiomize"]
    assert metadata_a["schema_version"] == 7
    assert out_a["content"] == json.dumps(out_a["notebook"], indent=2)

    out_b = wrapper(SimpleNamespace(key="b"))
    assert out_b["notebook"] == "raw-not-a-dict"
    assert "content" not in out_b

    out_c = wrapper(SimpleNamespace(key="c"))
    assert out_c["notebook"]["metadata"] == []
    assert json.loads(out_c["content"]) == out_c["notebook"]

    out_d = wrapper(SimpleNamespace(key="d"))
    assert out_d["notebook"]["metadata"]["axiomize"] == []
    assert "schema_version" not in out_d["notebook"]["metadata"]["axiomize"]

    out_e = wrapper(SimpleNamespace(key="e"))
    assert out_e["notebook"]["metadata"]["axiomize"] == {}
    assert "content" in out_e
    assert calls == ["a", "b", "c", "d", "e"]


def test_notebook_schema_alias_install_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from axiomize import portable_export_compat, standards_export

    monkeypatch.setattr(standards_export, "export_notebook", lambda model: {"notebook": {}})
    portable_export_compat.install_notebook_schema_alias()
    first = standards_export.export_notebook
    portable_export_compat.install_notebook_schema_alias()
    assert standards_export.export_notebook is first
    assert getattr(first, "__axiomize_schema_alias__", False) is True
