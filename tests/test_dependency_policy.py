"""Regression tests for the fail-closed dependency policy.

Covers the runtime dependency policy added in
``src/axiomize/dependency_policy.py``: the Gradio exposure and the pytest
vulnerable-tmpdir advisory (CVE-2025-71176 / GHSA-6w46-j5rx-g56g).
"""

from __future__ import annotations

import pytest

from axiomize.dependency_policy import (
    ADVISORY_NOTES,
    FORBIDDEN_IN_RUNTIME,
    RUNTIME_MINIMUMS,
    DependencyFinding,
    InsecureDependencyGraph,
    compare_versions,
    enforce_dependency_policy,
    is_version_at_least,
    scan_installed_dependencies,
)


# --- version comparison -------------------------------------------------------

@pytest.mark.parametrize(
    ("candidate", "minimum", "expected"),
    [
        ("9.0.3", "9.0.3", True),      # exactly the fixed release: the fix is in it
        ("9.0.4", "9.0.3", True),
        ("9.1.1", "9.0.3", True),
        ("10.0.0", "9.0.3", True),
        ("9.0.2", "9.0.3", False),
        ("8.4.2", "9.0.3", False),
        ("9.0", "9.0.3", False),
        ("9", "9.0.3", False),
        ("1.24", "1.24", True),
        ("2.5.3", "1.24", True),
        ("1.23.9", "1.24", False),
        ("0.14.0", "0.14", True),
        ("0.13.9", "0.14", False),
    ],
)
def test_version_floor_comparison(candidate: str, minimum: str, expected: bool) -> None:
    assert is_version_at_least(candidate, minimum) is expected
    assert compare_versions(candidate, minimum) is expected


def test_comparison_normalizes_a_leading_v() -> None:
    assert is_version_at_least("v9.0.3", "9.0.3") is True


@pytest.mark.parametrize("candidate", ["9.0.3rc1", "9.0.3.dev1", "unknown", "", "9.0.3.post1"])
def test_unparsable_versions_fail_closed(candidate: str) -> None:
    """An unknown version must never be treated as satisfying a floor."""
    assert is_version_at_least(candidate, "9.0.3") is False


# --- Gradio must not be in the runtime graph ---------------------------------

def test_gradio_is_forbidden_in_the_runtime_graph() -> None:
    assert "gradio" in FORBIDDEN_IN_RUNTIME
    assert "advisory" in FORBIDDEN_IN_RUNTIME["gradio"].lower()


def test_gradio_in_the_runtime_graph_is_a_critical_finding() -> None:
    findings = scan_installed_dependencies(installed={"gradio": "4.44.1"})
    assert len(findings) == 1
    finding = findings[0]
    assert finding.package == "gradio"
    assert finding.severity == "critical"
    assert "must not be" in finding.message


def test_gradio_at_the_newest_release_is_still_forbidden() -> None:
    """No version bound makes gradio safe, so even latest is a finding."""
    findings = scan_installed_dependencies(installed={"gradio": "6.29.0"})
    assert [f.severity for f in findings] == ["critical"]


def test_absent_gradio_produces_no_finding() -> None:
    assert scan_installed_dependencies(installed={"gradio": None}) == []


# --- pytest floor ------------------------------------------------------------

def test_pytest_below_the_fixed_release_is_a_high_finding() -> None:
    findings = scan_installed_dependencies(installed={"pytest": "8.4.2"})
    assert len(findings) == 1
    finding = findings[0]
    assert finding.package == "pytest"
    assert finding.severity == "high"
    assert "9.0.3" in finding.message
    assert "CVE-2025-71176" in finding.message


def test_pytest_at_or_above_the_fixed_release_is_clean() -> None:
    assert scan_installed_dependencies(installed={"pytest": "9.0.3"}) == []
    assert scan_installed_dependencies(installed={"pytest": "9.1.1"}) == []


def test_pytest_cve_is_named_in_the_policy_table() -> None:
    assert RUNTIME_MINIMUMS["pytest"] == "9.0.3"
    assert "CVE-2025-71176" in ADVISORY_NOTES["pytest"]


# --- enforcement -------------------------------------------------------------

def test_enforce_raises_on_a_vulnerable_graph() -> None:
    with pytest.raises(InsecureDependencyGraph) as exc:
        enforce_dependency_policy(installed={"gradio": "4.0.0", "pytest": "8.0.0"})
    packages = {f.package for f in exc.value.findings}
    assert packages == {"gradio", "pytest"}
    assert "insecure dependency graph" in str(exc.value)


def test_enforce_returns_empty_list_on_a_clean_graph() -> None:
    assert enforce_dependency_policy(installed={"gradio": None, "pytest": "9.1.1"}) == []


def test_finding_serialises_for_ci_reporting() -> None:
    finding = DependencyFinding(
        package="gradio", installed="4.0.0", severity="critical", message="m"
    )
    assert finding.as_dict() == {
        "package": "gradio",
        "installed": "4.0.0",
        "severity": "critical",
        "message": "m",
    }


# --- the policy tables themselves --------------------------------------------

def test_every_policy_entry_has_an_advisory_note() -> None:
    """A floor with no provenance cannot be audited, so require a note."""
    for package in set(FORBIDDEN_IN_RUNTIME) | set(RUNTIME_MINIMUMS):
        assert package in ADVISORY_NOTES, f"{package} has no ADVISORY_NOTES entry"
        assert ADVISORY_NOTES[package].strip()


def test_every_advisory_note_names_a_tracked_identifier() -> None:
    for package, note in ADVISORY_NOTES.items():
        assert any(
            token in note for token in ("CVE-", "GHSA-", "PYSEC-")
        ), f"{package} note cites no advisory identifier"


# --- the real environment ----------------------------------------------------

def test_this_environment_satisfies_the_policy() -> None:
    """The policy must actually pass on a correctly provisioned environment."""
    findings = scan_installed_dependencies()
    assert findings == [], [f.message for f in findings]
