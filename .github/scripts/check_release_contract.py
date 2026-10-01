#!/usr/bin/env python3
"""Fail CI when package/release metadata drift or release provenance is unsafe."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _project_version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    try:
        project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    except IndexError as exc:
        raise RuntimeError("pyproject.toml has no [project] section") from exc
    match = re.search(r'^version\s*=\s*"([^"]+)"\s*$', project, re.MULTILINE)
    if not match:
        raise RuntimeError("[project] has no literal version")
    return match.group(1)


def _runtime_version() -> str:
    text = (ROOT / "src" / "axiomize" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise RuntimeError("src/axiomize/__init__.py has no __version__")
    return match.group(1)


def _trigger_version() -> str:
    lines = (ROOT / ".github" / "pypi-release-trigger").read_text(encoding="utf-8").splitlines()
    if not lines:
        raise RuntimeError(".github/pypi-release-trigger is empty")
    match = re.fullmatch(r"axiomize-quantum-skills-2\.0\s+([^\s]+)", lines[0].strip())
    if not match:
        raise RuntimeError("first trigger line must be: axiomize-quantum-skills-2.0 <version>")
    return match.group(1)


def _requirement_markers() -> dict[str, str]:
    """Return ``{package: full requirement line}`` from requirements-test.txt.

    The file and pyproject.toml must agree on environment markers. They did not:
    pyproject capped ``z3-solver`` at ``<5`` on darwin (no macOS wheel exists for
    5.x) while requirements-test.txt said only ``>=4.12``, so a macOS runner
    resolved a version the installed distribution itself rejects, and
    ``pip check`` failed in the validate matrix. Duplicating the pins is
    unavoidable -- a requirements file cannot import from pyproject -- so the
    duplication is checked instead of trusted.
    """
    text = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
    requirements: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "-")):
            continue
        if ";" in stripped:
            name = stripped.split(";", 1)[0].strip()
            name = re.split(r"[<>=!~\[]", name, 1)[0].strip().lower()
            requirements[name] = re.sub(r"\s+", " ", stripped)
    return requirements


def _pyproject_dependencies() -> dict[str, list[str]]:
    """Return ``{package: [requirement line, ...]}`` from [project.dependencies]."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^dependencies\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise RuntimeError("pyproject.toml has no [project] dependencies list")
    grouped: dict[str, list[str]] = {}
    for raw in match.group(1).splitlines():
        entry = raw.strip().strip(",").strip('"')
        if not entry:
            continue
        name = re.split(r"[<>=!~\[; ]", entry, 1)[0].strip().lower()
        grouped.setdefault(name, []).append(re.sub(r"\s+", " ", entry))
    return grouped


def _version_specifiers_match(left: str, right: str) -> bool:
    """Compare two requirement strings ignoring the package name and spacing.

    Only the version constraints and environment markers are compared: the point
    is to catch a bound that exists in one file and not the other, which is what
    breaks ``pip check`` on one platform only.
    """

    def parts(requirement: str) -> tuple[str, str]:
        body, _, marker = requirement.partition(";")
        specs = ",".join(
            sorted(
                token.strip()
                for token in re.split(r"[,<>!=~\[ ]", body)
                if token.strip() and not token.strip().isidentifier()
            )
        )
        return specs, re.sub(r"\s+", "", marker)

    return parts(left) == parts(right)


def _dependency_markers_are_consistent() -> list[str]:
    """Report requirements whose pyproject markers differ from the test file."""
    requirements = _requirement_markers()
    declared = _pyproject_dependencies()
    failures: list[str] = []
    for name, entries in sorted(declared.items()):
        if name not in requirements:
            # Only a problem for markers: a plain pin is covered by the lower
            # bound in this file already, and adding every runtime dependency
            # to a *test* manifest would be wrong.
            if any(";" in entry for entry in entries):
                failures.append(
                    f"{name}: pyproject declares a platform marker but requirements-test.txt does not"
                )
            continue
        declared_markers = sorted(
            entry for entry in entries if ";" in entry
        )
        if not declared_markers:
            continue
        if not any(
            _version_specifiers_match(declared_entry, requirements[name])
            for declared_entry in declared_markers
        ):
            failures.append(
                f"{name}: pyproject {declared_markers} but requirements-test.txt "
                f"has {requirements[name]!r}"
            )
    return failures


def _readme_version() -> str:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    match = re.search(r"^Current package line:\s*\*\*([^*]+)\*\*", text, re.MULTILINE)
    if not match:
        raise RuntimeError("README.md has no 'Current package line' version")
    return match.group(1).strip()


def _changelog_version() -> str:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(r"^## \[([^\]]+)\]", text, re.MULTILINE)
    if not match:
        raise RuntimeError("CHANGELOG.md has no release heading")
    return match.group(1).strip()


#: Workflows that publish to a registry. Matched by prefix because the names
#: carry the target ("Release (PyPI)", "Release (npm)"); the previous single
#: string comparison silently stopped matching the moment a name was extended,
#: which is exactly the failure mode a provenance guard must not have.
RELEASE_WORKFLOW_PREFIX = "Release"


def _release_ref_is_allowed() -> bool:
    """Block release-workflow execution from any branch but ``main``.

    ``workflow_dispatch`` is a legitimate way to retry a failed publish, but
    without this guard GitHub lets a user dispatch a release workflow against an
    arbitrary branch and publish unreviewed content. Both release workflows are
    also restricted to push-on-main triggers, so this is the second of two
    independent guards rather than the only one.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return True
    workflow = os.environ.get("GITHUB_WORKFLOW", "")
    if not workflow.startswith(RELEASE_WORKFLOW_PREFIX):
        return True
    ref = os.environ.get("GITHUB_REF", "")
    if ref != "refs/heads/main":
        print(
            f"FAIL: '{workflow}' may run only from refs/heads/main; got {ref or '<missing>'}",
            file=sys.stderr,
        )
        return False
    return True


def main() -> int:
    # The version sources are read by version_lockstep so the release gate and
    # the version-lockstep gate cannot disagree about what the version is. The
    # README line is checked here and only here: it is documentation, so it is
    # required to track the release but is not a source the --bump helper writes.
    versions = {
        "pyproject": _project_version(),
        "runtime": _runtime_version(),
        "pypi_trigger": _trigger_version(),
        "readme": _readme_version(),
        "changelog": _changelog_version(),
    }
    for name, value in versions.items():
        print(f"{name:12s} {value}")
    if len(set(versions.values())) != 1:
        print("FAIL: release versions differ; update package, trigger and public docs together", file=sys.stderr)
        return 1
    if not _release_ref_is_allowed():
        return 1

    marker_failures = _dependency_markers_are_consistent()
    if marker_failures:
        print("FAIL: dependency environment markers differ between pyproject and requirements-test", file=sys.stderr)
        for failure in marker_failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print("dependency markers: pyproject and requirements-test.txt agree")

    # Cross-check against the shared helper so both gates read one definition.
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from version_lockstep import VersionDrift, assert_lockstep  # noqa: PLC0415

        assert_lockstep()
    except VersionDrift as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    print("PASS: release version contract is synchronized and release ref is authorized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
