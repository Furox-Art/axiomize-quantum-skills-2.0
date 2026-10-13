"""Regression coverage for the remaining audit-hardening findings on this repo.

Findings H1, H4, M6, M10 and M12 were verified against the shipped code and
are already satisfied here (see the module notes in the final report); what
remains actionable is pinned below:

* **H2/H3** — REST auth is enforced by explicit raises, never ``assert``
  (which ``python -O`` strips), and the MCP tool surface is explicit table
  data, so a server cannot start with zero tools.
* **M5** — ``version_lockstep.py`` guards all seven version sources,
  including ``codemeta.json`` and ``CITATION.cff``, and the npm publish
  workflow runs it before any upload.
* **M8** — the counts the README/docs assert are pinned against the code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


# --- H2/H3: fail-closed REST auth without assert, no zero-tool startup ---------

def test_remote_bind_requires_a_token_by_explicit_raise_not_assert() -> None:
    from axiomize.server.rest_server import start_server

    with pytest.raises(ValueError, match="non-loopback REST binding requires allow_remote=True"):
        start_server("0.0.0.0", 0, auth_token="a-sufficiently-long-token")
    with pytest.raises(ValueError, match="requires an auth token of at least 16"):
        start_server("0.0.0.0", 0, allow_remote=True, auth_token="short")


def test_auth_enforcement_survives_optimized_python() -> None:
    """``python -O`` strips asserts; the guards must be plain raises.

    Runs the same guard under ``-O`` in a subprocess: ValueError -> exit 0,
    AssertionError -> exit 3 (assert-based guard regressed), clean start ->
    exit 4 (guard removed).  Only exit 0 is acceptable.
    """
    code = (
        "from axiomize.server.rest_server import start_server\n"
        "try:\n"
        "    start_server('0.0.0.0', 0, allow_remote=True, auth_token='short')\n"
        "except ValueError:\n"
        "    raise SystemExit(0)\n"
        "except AssertionError:\n"
        "    raise SystemExit(3)\n"
        "raise SystemExit(4)\n"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"expected ValueError under -O, got exit {result.returncode}: {result.stderr}"
    )


def test_loopback_write_surface_fails_closed_without_a_token() -> None:
    """A directly-constructed server must never serve mutations unauthenticated."""
    from axiomize.server.rest_server import BoundedThreadingHTTPServer, Handler

    server = BoundedThreadingHTTPServer(("127.0.0.1", 0), Handler, run_root=REPO_ROOT,
                                        auth_token=None, max_concurrent_requests=1,
                                        connection_timeout_s=5.0)
    try:
        assert server.auth_token is None
        # The fail-closed branch lives in _require_write_authorized; exercising
        # it through HTTP is covered by test_transport_surface_hardening.py.
        import inspect

        source = inspect.getsource(Handler._require_write_authorized)
        assert "mutating routes require an auth token" in source
    finally:
        server.server_close()


# --- M5: version lockstep covers every version-bearing file --------------------

def _lockstep_module():
    import importlib.util

    path = REPO_ROOT / ".github" / "scripts" / "version_lockstep.py"
    spec = importlib.util.spec_from_file_location("axiomize_version_lockstep_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_version_lockstep_covers_all_seven_sources() -> None:
    module = _lockstep_module()
    versions = module.collect()
    assert set(versions) == {
        "pyproject", "runtime", "package_json", "changelog",
        "pypi_trigger", "codemeta", "citation",
    }
    # The real repository must pass its own gate.
    assert module.assert_lockstep() == versions


def test_version_lockstep_fails_loudly_on_citation_or_codemeta_drift(monkeypatch) -> None:
    module = _lockstep_module()
    locked = module.assert_lockstep()

    drifted_citation = locked["citation"].replace("1", "9", 1) if "1" in locked["citation"] else "9.9.9"
    monkeypatch.setattr(module, "_citation_version", lambda text: drifted_citation)
    with pytest.raises(module.VersionDrift, match="version sources disagree"):
        module.assert_lockstep()

    drifted_codemeta = locked["codemeta"].replace("1", "9", 1) if "1" in locked["codemeta"] else "9.9.9"
    monkeypatch.setattr(module, "_codemeta_version", lambda text: drifted_codemeta)
    with pytest.raises(module.VersionDrift):
        module.assert_lockstep()


def test_version_lockstep_extractors_reject_malformed_files() -> None:
    module = _lockstep_module()
    with pytest.raises(module.VersionDrift, match="codemeta.json"):
        module._codemeta_version("{not json")
    with pytest.raises(module.VersionDrift, match="codemeta.json"):
        module._codemeta_version(json.dumps({"name": "no version here"}))
    with pytest.raises(module.VersionDrift, match="CITATION.cff"):
        module._citation_version("title: something without a version\n")
    assert module._citation_version("cff-version: 1.2.0\nversion: 1.2.2\n") == "1.2.2"


def test_npm_publish_workflow_runs_the_lockstep_guard_before_publishing() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "npm-publish.yml").read_text(encoding="utf-8")
    guard_at = workflow.find("python .github/scripts/version_lockstep.py")
    publish_at = workflow.find("npm publish --access public")
    assert guard_at != -1 and publish_at != -1
    assert guard_at < publish_at, "the lockstep guard must run before either publish step"


# --- M8: verified count claims stay accurate ------------------------------------

def test_verified_repository_counts_match_the_docs() -> None:
    """Pin the counts the README/docs assert, so drift fails the suite."""
    packs = sorted((REPO_ROOT / "packs").glob("*.md"))
    # domain-packs.md is the index, not a domain pack.
    domain_packs = [p for p in packs if p.name != "domain-packs.md"]
    assert len(domain_packs) == 12
    assert len(list((REPO_ROOT / "skills" / "axiomize" / "perspectives").glob("*.md"))) == 15
    assert len(list((REPO_ROOT / "skills" / "axiomize" / "templates").glob("*.md"))) == 5
    assert len([p for p in (REPO_ROOT / "examples").iterdir() if p.is_file()]) == 18
    assert len(list((REPO_ROOT / "docs").glob("*.md"))) == 15

    ideas = json.loads((REPO_ROOT / "benchmarks" / "ideas.json").read_text(encoding="utf-8"))
    assert len(ideas["cases"]) == 25
    cases = (REPO_ROOT / "src" / "axiomize" / "reasoning" / "benchmark" / "cases.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([line for line in cases if line.strip()]) == 6
