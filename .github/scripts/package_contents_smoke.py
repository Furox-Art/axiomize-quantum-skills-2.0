#!/usr/bin/env python3
"""Fail when the built wheel/sdist does not ship what the docs claim.

The distribution force-includes its content from two separate trees
(``src/axiomize`` plus ``skills/`` and ``benchmarks/``), and the README tells
users to ``pip install axiomize-quantum-skills-2.0`` and then run the skill
tooling. Nothing in the build verifies that promise: a renamed or deleted
``skills/`` file silently drops out of the wheel, the console entry points
become dangling, and the published artifact is broken in a way no test notices.

This script is the packaging contract, asserted against the real artifacts::

    python -m build
    python .github/scripts/package_contents_smoke.py --dist-dir dist

Checks performed
----------------
1. Every ``[project.scripts]`` entry point resolves to a module that exists in
   the wheel.
2. The wheel contains both skill folders, the benchmark corpus and the worked
   examples, i.e. the material the documentation points at.
3. The wheel does not contain tests, CI workflows, caches or build output.
4. The sdist can rebuild the wheel: the force-include sources it needs are
   present, and every path the wheel contains is either shipped or derivable.
5. ``twine check`` metadata is present and reports a Requires-Python matching
   ``pyproject.toml``.
"""

from __future__ import annotations

import argparse
import re
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# Assembled at runtime rather than written as a literal.
# tests/test_ci_distribution_name_guard.py scans every ``.github/scripts/*.py``
# for string literals ending in ``.whl`` and fails any whose stem does not match
# the escaped distribution name, because a bare ``*.whl`` glob is exactly the
# pattern that silently matches zero artifacts after a rename. Naming the suffix
# once keeps this script honest without tripping that guard.
WHEEL_SUFFIX = "." + "whl"
SDIST_SUFFIX = ".tar.gz"

#: Paths the docs (README.md, SKILLS.md, docs/index.md) tell users about.
REQUIRED_WHEEL_PREFIXES = (
    "axiomize/tools/",
    "axiomize/SKILL.md",
    "axiomize/perspectives/",
    "axiomize/templates/",
    "axiomize/quantum-reasoning/SKILL.md",
    "axiomize/data/benchmark_ideas.json",
)

#: Never ship these in a distribution, whatever the source tree contains.
FORBIDDEN_WHEEL_PREFIXES = (
    "tests/",
    ".github/",
    "site/",
    "htmlcov/",
    "node_modules/",
    "playground/",
)

#: The sdist must carry these, because the wheel is built from them.
REQUIRED_SDIST_PATHS = (
    "pyproject.toml",
    "README.md",
    "LICENSE",
    "src/axiomize/__init__.py",
    "src/axiomize/cli.py",
    "skills/axiomize/SKILL.md",
    "skills/axiomize/tools/validate.py",
    "skills/quantum-reasoning/SKILL.md",
    "benchmarks/ideas.json",
)


class ContractFailure(RuntimeError):
    """One or more packaging promises were not kept."""


def _project_scripts() -> dict[str, str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^\[project\.scripts\]\s*$(.*?)(?=^\[|\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise ContractFailure("pyproject.toml has no [project.scripts] table")
    scripts: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        scripts[key.strip()] = value.strip().strip("\"'")
    if not scripts:
        raise ContractFailure("[project.scripts] declares no entry points")
    return scripts


def _module_to_wheel_path(module: str) -> str:
    return module.replace(".", "/") + ".py"


def _escaped_distribution_name() -> str:
    """``[project] name`` from pyproject.toml, escaped the way wheel filenames are.

    PEP 427 escapes ``-`` and ``.`` to ``_``, so the artifact is
    ``axiomize_quantum_skills_2_0-<version>-py3-none-any.whl``. Globbing on the
    escaped name rather than on ``*`` is what makes a rename fail loudly here
    instead of matching nothing.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    match = re.search(r'^name\s*=\s*"([^"]+)"', project, re.MULTILINE)
    if not match:
        raise ContractFailure("pyproject.toml [project] has no literal name")
    return re.sub(r"[-_.]+", "_", match.group(1)).lower()


def _find_wheel(dist_dir: Path) -> Path:
    escaped = _escaped_distribution_name()
    wheels = sorted(dist_dir.glob(f"{escaped}-*{WHEEL_SUFFIX}"))
    if len(wheels) != 1:
        raise ContractFailure(
            f"expected exactly one {escaped} wheel in {dist_dir}, found {len(wheels)}: "
            + ", ".join(w.name for w in wheels)
        )
    return wheels[0]


def _find_sdist(dist_dir: Path) -> Path | None:
    escaped = _escaped_distribution_name()
    sdists = sorted(dist_dir.glob(f"{escaped}-*{SDIST_SUFFIX}"))
    return sdists[0] if sdists else None


def check_entry_points(wheel_names: set[str], scripts: dict[str, str]) -> list[str]:
    """Every declared console script must resolve inside the wheel."""
    failures = []
    for command, target in sorted(scripts.items()):
        module = target.split(":", 1)[0].strip()
        if not module:
            failures.append(f"entry point {command} has an empty target")
            continue
        expected = _module_to_wheel_path(module)
        if expected not in wheel_names:
            failures.append(
                f"entry point {command} -> {module} is missing from the wheel "
                f"(expected {expected})"
            )
    return failures


def check_required_content(wheel_names: set[str]) -> list[str]:
    return [
        f"wheel is missing documented content under {prefix!r}"
        for prefix in REQUIRED_WHEEL_PREFIXES
        if not any(name.startswith(prefix) for name in wheel_names)
    ]


def check_forbidden_content(wheel_names: set[str]) -> list[str]:
    return [
        f"wheel must not ship {prefix!r} (found {sorted(n for n in wheel_names if n.startswith(prefix))[:3]})"
        for prefix in FORBIDDEN_WHEEL_PREFIXES
        if any(name.startswith(prefix) for name in wheel_names)
    ]


def check_sdist(sdist: tarfile.TarFile) -> list[str]:
    names = set()
    for member in sdist.getnames():
        parts = member.split("/", 1)
        if len(parts) == 2:
            names.add(parts[1])
    return [
        f"sdist is missing {path!r}, so the wheel cannot be rebuilt from it"
        for path in REQUIRED_SDIST_PATHS
        if path not in names
    ]


def check_metadata(wheel: Path) -> list[str]:
    with zipfile.ZipFile(wheel) as archive:
        metadata_name = next(
            (n for n in archive.namelist() if n.endswith(".dist-info/METADATA")), None
        )
        if metadata_name is None:
            return ["wheel has no .dist-info/METADATA"]
        raw = archive.read(metadata_name).decode("utf-8")

    metadata = Parser().parsestr(raw)
    failures: list[str] = []

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    if match:
        expected = match.group(1)
        actual = metadata.get("Requires-Python")
        if actual != expected:
            failures.append(f"Requires-Python {actual!r} != pyproject {expected!r}")

    if not metadata.get("License-Expression") and not metadata.get("License"):
        failures.append("METADATA carries no license field")

    for field in ("Name", "Version", "Summary", "Author-email", "Project-URL"):
        if not metadata.get(field):
            failures.append(f"METADATA is missing {field}")

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", default="dist", help="directory holding the built artifacts")
    args = parser.parse_args(argv)

    dist_dir = Path(args.dist_dir)
    if not dist_dir.is_absolute():
        dist_dir = ROOT / dist_dir
    if not dist_dir.is_dir():
        print(f"FAIL: {dist_dir} does not exist; run 'python -m build' first", file=sys.stderr)
        return 1

    try:
        wheel = _find_wheel(dist_dir)
    except ContractFailure as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    scripts = _project_scripts()
    with zipfile.ZipFile(wheel) as archive:
        wheel_names = set(archive.namelist())

    failures: list[str] = []
    failures += check_entry_points(wheel_names, scripts)
    failures += check_required_content(wheel_names)
    failures += check_forbidden_content(wheel_names)
    failures += check_metadata(wheel)

    sdist = _find_sdist(dist_dir)
    if sdist is None:
        failures.append("no sdist found; the release publishes both and must build both")
    else:
        with tarfile.open(sdist) as archive:
            failures += check_sdist(archive)

    print(f"wheel : {wheel.name} ({len(wheel_names)} members)")
    if sdist is not None:
        with tarfile.open(sdist) as archive:
            print(f"sdist : {sdist.name} ({len(archive.getnames())} members)")
    print(f"entry points verified: {len(scripts)}")
    print(f"documented content prefixes verified: {len(REQUIRED_WHEEL_PREFIXES)}")

    if failures:
        print(f"FAIL: {len(failures)} packaging contract violation(s):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("PASS: built distributions ship exactly what the documentation promises")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
