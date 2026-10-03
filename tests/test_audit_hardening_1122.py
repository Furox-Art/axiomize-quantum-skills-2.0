"""Regression coverage for the 1.12.2 repository-audit fixes."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from axiomize.limits import (
    MAX_INTEGER_DIGITS,
    bounded_float,
    bounded_int,
    enforce_finite_values,
)
from axiomize.runs.state import RunState

ROOT = Path(__file__).resolve().parents[1]


def _release_contract_module():
    path = ROOT / ".github" / "scripts" / "check_release_contract.py"
    spec = importlib.util.spec_from_file_location("axiomize_release_contract_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shared_numeric_boundaries_reject_booleans_and_huge_integer_text() -> None:
    with pytest.raises(ValueError, match="boolean"):
        bounded_float(True, name="alpha")
    with pytest.raises(ValueError, match="boolean"):
        enforce_finite_values([1.0, False], name="values")
    huge = "9" * (MAX_INTEGER_DIGITS + 1)
    with pytest.raises(ValueError, match="exceeds"):
        bounded_int(huge, name="count", maximum=10)


@pytest.mark.parametrize("declared_version", [True, 1.5, "1.5"])
def test_run_state_rejects_nonexact_manifest_versions(tmp_path: Path, declared_version) -> None:
    RunState(problem_definition="manifest-version-audit").save(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_format_version"] = declared_version
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        RunState.load(tmp_path)


def test_release_contract_keeps_package_trigger_readme_and_changelog_in_lockstep(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _release_contract_module()
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    monkeypatch.delenv("GITHUB_WORKFLOW", raising=False)
    monkeypatch.delenv("GITHUB_REF", raising=False)
    assert module.main() == 0


def test_release_workflow_ref_guard_blocks_feature_branch_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _release_contract_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Release")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/audit/not-main")
    assert module.main() == 1


def test_release_workflow_ref_guard_allows_main(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _release_contract_module()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_WORKFLOW", "Release")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    assert module.main() == 0


@pytest.mark.parametrize(
    "rotting_line",
    [
        "**PyPI and npm are both on `1.2.0`.** The npm package is a shim.",
        "  `npm install axiomize-quantum-skills-2.0` resolves to `1.2.0`. If you pinned it, upgrade.",
        'leads with `"axiomize_version": "1.2.0"`.',
    ],
)
def test_readme_currency_guard_rejects_a_stale_installed_version(rotting_line: str) -> None:
    """Each shape here shipped once and was wrong the moment a release was cut."""
    module = _release_contract_module()
    failures = module._readme_currency_failures(rotting_line, "1.2.1")
    assert len(failures) == 1
    assert "1.2.0" in failures[0]
    assert "1.2.1" in failures[0]


@pytest.mark.parametrize(
    "honest_line",
    [
        # Restated without a pin, which is what the fix for the rot looks like.
        "**PyPI and npm both carry the release named above.**",
        "  `npm install axiomize-quantum-skills-2.0` resolves to the current release.",
        'leads with `"axiomize_version": "1.2.1"`.',
        # Provenance naming a fixed past event must stay allowed forever: bumping
        # these to the current version would make them false, not true.
        "## Quick start (verified against 1.2.0)",
        "Every command above was run against `axiomize-quantum-skills-2.0` 1.2.0 at commit `9c2990c`",
        "(also `axiomize-benchmark`). Re-graded at commit `9c2990c`, axiomize 1.2.0, CPython 3.12.10",
        # A different, deliberately-discussed registry version is not drift.
        "- npm also still holds `2.0.0`, published before the launcher fix.",
    ],
)
def test_readme_currency_guard_allows_truthful_and_historical_claims(honest_line: str) -> None:
    module = _release_contract_module()
    assert module._readme_currency_failures(honest_line, "1.2.1") == []


def test_readme_currency_guard_is_satisfied_by_the_real_readme() -> None:
    """The guard has to pass on the README as committed, not just on samples."""
    module = _release_contract_module()
    text = (module.ROOT / "README.md").read_text(encoding="utf-8")
    current = module._readme_version()
    assert module._readme_currency_failures(text, current) == []


def _workflow(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "workflows"
    directory.mkdir(exist_ok=True)
    (directory / "release.yml").write_text(body, encoding="utf-8")
    return directory


def test_twine_pin_guard_rejects_the_pin_that_failed_the_release(tmp_path: Path) -> None:
    """twine 6.2.0 is the pin that broke run 37159564533 on Metadata 2.5."""
    module = _release_contract_module()
    directory = _workflow(
        tmp_path,
        'jobs:\n  build:\n    steps:\n'
        '      - run: pip install "twine==6.2.0"\n'
        "      - run: python -m twine check --strict dist/*\n",
    )
    failures = module._twine_pin_failures("2.5", directory)
    assert len(failures) == 1
    assert "twine==6.2.0" in failures[0]
    assert "2.5" in failures[0]


def test_twine_pin_guard_rejects_an_unpinned_twine(tmp_path: Path) -> None:
    """The unpinned ci.yml install is how the PR gate passed and release failed."""
    module = _release_contract_module()
    directory = _workflow(
        tmp_path,
        "jobs:\n  build:\n    steps:\n"
        "      - run: python -m pip install build twine\n"
        "      - run: python -m twine check --strict dist/*\n",
    )
    failures = module._twine_pin_failures("2.5", directory)
    assert len(failures) == 1
    assert "without pinning twine" in failures[0]


def test_twine_pin_guard_ignores_a_pin_named_only_in_a_comment(tmp_path: Path) -> None:
    """The comment explaining the bug names the old pin; prose is not a pin."""
    module = _release_contract_module()
    directory = _workflow(
        tmp_path,
        "jobs:\n  build:\n    steps:\n"
        '      - run: pip install "twine==7.0.0"\n'
        "      # it used to pin twine==6.2.0 here\n"
        "      - run: python -m twine check --strict dist/*\n",
    )
    assert module._twine_pin_failures("2.5", directory) == []


def test_twine_pin_guard_allows_the_current_pin_and_real_workflows() -> None:
    module = _release_contract_module()
    assert module._twine_pin_failures(
        module.EMITTED_METADATA_VERSION, module.WORKFLOW_DIR
    ) == []


def test_twine_pin_guard_reports_an_unknown_metadata_version() -> None:
    """An unmapped metadata version must fail loudly, never silently pass."""
    module = _release_contract_module()
    failures = module._twine_pin_failures("9.9", None)
    assert len(failures) == 1
    assert "MIN_TWINE_FOR_METADATA" in failures[0]
