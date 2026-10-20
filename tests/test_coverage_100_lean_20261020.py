"""Coverage hardening for the Lean adapter with a faked elan/lean process."""

from __future__ import annotations

import subprocess

import pytest

from axiomize.formal import lean_adapter
from axiomize.formal.lean_adapter import LeanAdapter
from axiomize.tools.base import ToolMetadata


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _available(version="Lean 4.30.0"):
    return ToolMetadata(name="lean", capabilities=["formal_verification"], version=version, available=True)


def test_lean_cmd_requires_elan(monkeypatch):
    monkeypatch.setattr(lean_adapter.shutil, "which", lambda name: None)
    assert LeanAdapter._lean_cmd() is None
    monkeypatch.setattr(lean_adapter.shutil, "which", lambda name: "C:/bin/elan.exe")
    assert LeanAdapter._lean_cmd() == ["elan", "run", LeanAdapter.TOOLCHAIN, "lean"]


def test_availability_without_elan(monkeypatch):
    monkeypatch.setattr(lean_adapter.shutil, "which", lambda name: None)
    meta = LeanAdapter.availability()
    assert meta.available is False
    assert meta.reason == "elan not found on PATH"


def test_availability_probe_failure(monkeypatch):
    monkeypatch.setattr(lean_adapter.shutil, "which", lambda name: "elan")

    def boom(*args, **kwargs):
        raise OSError("cannot spawn")

    monkeypatch.setattr(lean_adapter.subprocess, "run", boom)
    meta = LeanAdapter.availability()
    assert meta.available is False
    assert "lean probe failed: cannot spawn" in meta.reason


def test_availability_toolchain_missing(monkeypatch):
    monkeypatch.setattr(lean_adapter.shutil, "which", lambda name: "elan")
    monkeypatch.setattr(
        lean_adapter.subprocess, "run",
        lambda *args, **kwargs: _Proc(returncode=1, stderr="  unknown toolchain  "),
    )
    meta = LeanAdapter.availability()
    assert meta.available is False
    assert meta.reason == f"toolchain {LeanAdapter.TOOLCHAIN} unavailable: unknown toolchain"


def test_availability_success_and_unknown_version(monkeypatch):
    monkeypatch.setattr(lean_adapter.shutil, "which", lambda name: "elan")
    monkeypatch.setattr(
        lean_adapter.subprocess, "run",
        lambda *args, **kwargs: _Proc(returncode=0, stdout="Lean 4.30.0\n"),
    )
    meta = LeanAdapter.availability()
    assert meta.available and meta.version == "Lean 4.30.0"

    monkeypatch.setattr(
        lean_adapter.subprocess, "run",
        lambda *args, **kwargs: _Proc(returncode=0, stdout=""),
    )
    assert LeanAdapter.availability().version == "unknown"


def test_probe_version(monkeypatch):
    monkeypatch.setattr(LeanAdapter, "availability", classmethod(lambda cls: _available("v1")))
    assert LeanAdapter._probe_version() == "v1"
    monkeypatch.setattr(
        LeanAdapter, "availability",
        classmethod(lambda cls: ToolMetadata(name="lean", available=False, reason="no lean")),
    )
    with pytest.raises(RuntimeError, match="no lean"):
        LeanAdapter._probe_version()


def test_validate_input_rejections():
    tool = LeanAdapter()
    with pytest.raises(ValueError, match="payload must be a dict"):
        tool.validate_input([])
    with pytest.raises(ValueError, match="non-empty 'theorem'"):
        tool.validate_input({"theorem": "   "})
    with pytest.raises(ValueError, match="hard limit"):
        tool.validate_input({"theorem": "x" * (2 * 1024 * 1024 + 1)})
    with pytest.raises(ValueError, match="timeout_s must be finite"):
        tool.validate_input({"theorem": "theorem t : True := trivial", "timeout_s": 0})
    with pytest.raises(ValueError, match="timeout_s must be finite"):
        tool.validate_input({"theorem": "theorem t : True := trivial", "timeout_s": float("nan")})
    tool.validate_input({"theorem": "theorem t : True := trivial", "timeout_s": 10})


def test_execute_unavailable(monkeypatch):
    monkeypatch.setattr(
        LeanAdapter, "availability",
        classmethod(lambda cls: ToolMetadata(name="lean", available=False, reason="missing")),
    )
    result = LeanAdapter().execute({"theorem": "theorem t : True := trivial"})
    assert result["status"] == "TOOL_UNAVAILABLE"
    assert result["proved"] is False
    assert result["reason"] == "missing"


def test_execute_requires_trust(monkeypatch):
    monkeypatch.setattr(LeanAdapter, "availability", classmethod(lambda cls: _available()))
    result = LeanAdapter().execute({"theorem": "theorem t : True := trivial"})
    assert result["status"] == "INCONCLUSIVE"
    assert result["proved"] is False
    assert "disabled by default" in result["reason"]


def _patch_lean(monkeypatch, run):
    monkeypatch.setattr(LeanAdapter, "availability", classmethod(lambda cls: _available()))
    monkeypatch.setattr(LeanAdapter, "_lean_cmd", classmethod(lambda cls: ["lean"]))
    monkeypatch.setattr(lean_adapter.subprocess, "run", run)


def test_execute_timeout(monkeypatch):
    def run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="lean", timeout=1)

    _patch_lean(monkeypatch, run)
    result = LeanAdapter().execute(
        {"theorem": "theorem t : True := trivial", "allow_unsafe_execution": True, "timeout_s": 1}
    )
    assert result["status"] == "INCONCLUSIVE"
    assert result["proved"] is False
    assert result["reason"] == "lean did not finish within 1s"
    assert result["toolchain"] == LeanAdapter.TOOLCHAIN
    assert result["elapsed_s"] >= 0


def test_execute_pass_and_fail(monkeypatch):
    _patch_lean(monkeypatch, lambda *args, **kwargs: _Proc(returncode=0, stdout="ok"))
    result = LeanAdapter().execute(
        {"theorem": "theorem t : True := trivial", "allow_unsafe_execution": True}
    )
    assert result["status"] == "PASS"
    assert result["proved"] is True
    assert result["proof"] == "theorem t : True := trivial"
    assert result["reason"] == "lean elaborated the file with no errors"

    _patch_lean(
        monkeypatch,
        lambda *args, **kwargs: _Proc(returncode=1, stdout="line 1: ", stderr="error"),
    )
    result = LeanAdapter().execute(
        {"theorem": "theorem t : False := trivial", "allow_unsafe_execution": True}
    )
    assert result["status"] == "FAIL"
    assert result["proved"] is False
    assert result["lean_output"] == "line 1: error"
    assert result["reason"] == "lean rejected the statement"
