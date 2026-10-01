"""Fail-closed dependency policy for the Axiomize runtime graph.

Motivation
----------
Axiomize's runtime dependency set is declared in ``pyproject.toml`` with open
lower bounds, and the optional ``playground`` extra pulls in ``gradio``. Gradio
is a web-application framework that has accumulated a large advisory history
(SSRF, path traversal, arbitrary file upload/delete, CORS-origin bypass, open
redirect, decompression-bomb DoS). Several of those advisories are still
**unpatched at any released version**, so no upper bound can make an unbounded
``gradio`` requirement safe: the only safe resolution is for Gradio to be absent
from the runtime graph entirely.

This module makes that requirement enforceable from the runtime side, because
a declared floor alone cannot guarantee which version a resolver selects.

Policy
------
``RUNTIME_MINIMUMS``
    Packages the runtime requires, each with the lowest version known to be free
    of the advisories tracked here. A resolved version below the floor is a
    finding.
``FORBIDDEN_IN_RUNTIME``
    Packages that must not be present in the runtime graph at all. Presence is
    a finding regardless of version.
``ADVISORY_NOTES``
    Human-readable provenance for each floor, so the table can be audited
    against an advisory database rather than trusted blindly.

The policy is data-driven and dependency-free: it only uses
``importlib.metadata`` to read what is actually installed, and a small PEP 440
subset comparison so it never has to import the packages it is judging.

Nothing here imports a third-party package, so it is safe to call from
``start_server`` and from CI. It performs no network access; the advisory
floor table is reviewed by hand and refreshed by the tests in
``tests/test_dependency_policy.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata
from typing import Iterable, Mapping

__all__ = [
    "ADVISORY_NOTES",
    "DependencyFinding",
    "FORBIDDEN_IN_RUNTIME",
    "InsecureDependencyGraph",
    "RUNTIME_MINIMUMS",
    "compare_versions",
    "enforce_dependency_policy",
    "is_version_at_least",
    "scan_installed_dependencies",
    "version_at_least",
]


class InsecureDependencyGraph(RuntimeError):
    """Raised when the resolved dependency graph violates the policy."""

    def __init__(self, findings: Iterable["DependencyFinding"]) -> None:
        self.findings = tuple(findings)
        detail = "; ".join(f.message for f in self.findings)
        super().__init__(f"insecure dependency graph: {detail}")


# Packages that must never be part of the Axiomize runtime graph.
#
# ``gradio`` is the reason this table exists. It is only used by the optional
# local playground UI (``playground/app.py``), which is not imported by
# ``axiomize`` and is not installed by the wheel. It is a *user-interface*
# dependency, not a runtime one. See ADVISORY_NOTES["gradio"].
FORBIDDEN_IN_RUNTIME: Mapping[str, str] = {
    "gradio": (
        "Gradio is a local web-UI framework used only by the optional playground "
        "demo and is not imported by the axiomize package. It carries a large "
        "advisory history (SSRF, path traversal, arbitrary file upload and "
        "deletion, CORS-origin validation bypass, open redirect, zip-bomb DoS), "
        "and multiple advisories remain unpatched at every released version, so "
        "no version bound makes it safe to keep in the runtime graph."
    ),
}


# Lowest version accepted for a runtime dependency.
#
# Floors are set to the first release that carries the fix for the advisory
# named in ADVISORY_NOTES. A floor equal to the fix version is safe: the fix is
# included in it.
RUNTIME_MINIMUMS: Mapping[str, str] = {
    "pytest": "9.0.3",
}


ADVISORY_NOTES: Mapping[str, str] = {
    "pytest": (
        "CVE-2025-71176 / GHSA-6w46-j5rx-g56g / PYSEC-2026-1845 - vulnerable "
        "tmpdir handling. Fixed in pytest 9.0.3. "
        "CVSS:3.1/AV:L/AC:L/PR:N/UI:N/S:C/C:L/I:L/A:L"
    ),
    "gradio": (
        "Unbounded advisory set. Unpatched (no fixed release) advisories include "
        "GHSA-prpg-p95c-32fv (path traversal), GHSA-v4q9-qgqf-7jwp (arbitrary file "
        "upload), GHSA-pgfv-gvc5-prfg (arbitrary file deletion), "
        "GHSA-3gf9-wv65-gwh9 and GHSA-973g-55hp-3frw (SSRF), "
        "GHSA-wmjh-cpqj-4v6x (CORS origin validation bypass), "
        "GHSA-7xmc-vhjp-qv5q (zip-bomb DoS). Because at least one has no fixed "
        "release, gradio must be excluded from the runtime graph rather than "
        "version-bounded."
    ),
}


@dataclass(frozen=True)
class DependencyFinding:
    """One policy violation observed in the resolved environment."""

    package: str
    installed: str | None
    severity: str
    message: str

    def as_dict(self) -> dict[str, str | None]:
        return {
            "package": self.package,
            "installed": self.installed,
            "severity": self.severity,
            "message": self.message,
        }


# --- Minimal PEP 440 comparison -------------------------------------------------
#
# Only the release segment is compared. Axiomize floors are plain release
# versions, so pre/post/dev/local labels never need to order against them; a
# version carrying a label is treated as unparsable and reported rather than
# silently accepted.

_RELEASE_RE = re.compile(r"^\s*v?(\d+(?:\.\d+)*)(?:[-_.]?((?:a|b|rc|dev|post)\d*))?\s*$")
_NUMERIC_PART_RE = re.compile(r"\d+")


def _release_tuple(version: str) -> tuple[int, ...] | None:
    match = _RELEASE_RE.match(str(version))
    if match is None:
        return None
    # A pre/post/dev label changes ordering, so refuse to guess.
    if match.group(2):
        return None
    return tuple(int(part) for part in _NUMERIC_PART_RE.findall(match.group(1)))


def _pad(a: tuple[int, ...], b: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    width = max(len(a), len(b))
    return a + (0,) * (width - len(a)), b + (0,) * (width - len(b))


def is_version_at_least(installed: str, minimum: str) -> bool:
    """Return True when ``installed`` is at least ``minimum``.

    An unparsable version returns False so the caller reports a finding instead
    of treating an unknown version as safe.
    """
    left = _release_tuple(installed)
    right = _release_tuple(minimum)
    if left is None or right is None:
        return False
    left_p, right_p = _pad(left, right)
    return left_p >= right_p


# Backwards-friendly alias used by the tests and by callers that read the
# comparison as a predicate on a candidate version.
def compare_versions(candidate: str, minimum: str) -> bool:
    """True when ``candidate`` satisfies the ``minimum`` floor."""
    return is_version_at_least(candidate, minimum)


version_at_least = is_version_at_least


def _installed_version(package: str) -> str | None:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def scan_installed_dependencies(
    *,
    installed: Mapping[str, str | None] | None = None,
    forbidden: Mapping[str, str] | None = None,
    minimums: Mapping[str, str] | None = None,
) -> list[DependencyFinding]:
    """Inspect the resolved environment and return every policy violation.

    ``installed``, ``forbidden`` and ``minimums`` are injection points for the
    regression tests so the policy can be exercised without manipulating the
    real environment.
    """
    if installed is None:
        installed = {
            name: _installed_version(name)
            for name in sorted(set(FORBIDDEN_IN_RUNTIME) | set(RUNTIME_MINIMUMS))
        }
    if forbidden is None:
        forbidden = FORBIDDEN_IN_RUNTIME
    if minimums is None:
        minimums = RUNTIME_MINIMUMS

    findings: list[DependencyFinding] = []

    for package in sorted(forbidden):
        version = installed.get(package)
        if version is None:
            continue
        findings.append(
            DependencyFinding(
                package=package,
                installed=version,
                severity="critical",
                message=(
                    f"{package} {version} is present in the runtime graph but must not be. "
                    f"{forbidden[package]}"
                ),
            )
        )

    for package in sorted(minimums):
        minimum = minimums[package]
        version = installed.get(package)
        if version is None:
            continue
        if not is_version_at_least(version, minimum):
            note = ADVISORY_NOTES.get(package, "")
            findings.append(
                DependencyFinding(
                    package=package,
                    installed=version,
                    severity="high",
                    message=(
                        f"{package} {version} is below the required minimum {minimum}. {note}"
                    ).strip(),
                )
            )

    return findings


def enforce_dependency_policy(
    *,
    installed: Mapping[str, str | None] | None = None,
    forbidden: Mapping[str, str] | None = None,
    minimums: Mapping[str, str] | None = None,
) -> list[DependencyFinding]:
    """Return findings, raising :class:`InsecureDependencyGraph` if any exist.

    Fail-closed: an environment that cannot be proven clean is treated as
    unsafe rather than silently allowed.
    """
    findings = scan_installed_dependencies(
        installed=installed, forbidden=forbidden, minimums=minimums
    )
    if findings:
        raise InsecureDependencyGraph(findings)
    return findings
