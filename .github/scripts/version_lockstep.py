#!/usr/bin/env python3
"""Single source of truth for the project version.

Every artefact that advertises a version -- ``pyproject.toml``,
``src/axiomize/__init__.py``, ``package.json``, ``CHANGELOG.md`` and the PyPI
release trigger file -- must agree. This module is the one place that reads
them all, and :mod:`check_release_contract` plus the npm contract test both call
into it, so the rule cannot drift between the Python and Node gates.

The rule is deliberately strict: this is a single product shipped to two
registries, and a version split across ``pyproject.toml`` (``1.2.0``) and
``package.json`` (``2.0.0``) is exactly the drift this exists to prevent.

Usage::

    python .github/scripts/version_lockstep.py            # human readable
    python .github/scripts/version_lockstep.py --json     # machine readable
    python .github/scripts/version_lockstep.py --bump 1.3.0
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")

#: Ordered so the report reads from build metadata outwards.
SOURCES = (
    "pyproject",
    "runtime",
    "package_json",
    "changelog",
    "pypi_trigger",
)

#: The version the release workflows are gated against.
TRIGGER_REL = Path(".github") / "pypi-release-trigger"


class VersionDrift(RuntimeError):
    """Raised when two version sources disagree."""


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _pyproject_version(text: str) -> str:
    """Read ``[project] version`` without a TOML parser dependency.

    ``tomllib`` is stdlib on 3.11+ but this script also runs on 3.10 in the
    matrix, so the ``[project]`` table is extracted textually. The section is
    terminated at the next top-level table, so sibling tables such as
    ``[project.optional-dependencies]`` cannot be mistaken for the version.
    """
    try:
        project = text.split("[project]", 1)[1].split("\n[", 1)[0]
    except IndexError as exc:
        raise VersionDrift("pyproject.toml has no [project] section") from exc
    match = re.search(r'^\s*version\s*=\s*"([^"]+)"\s*$', project, re.MULTILINE)
    if not match:
        raise VersionDrift("pyproject.toml [project] has no literal version")
    return match.group(1).strip()


def _runtime_version(text: str) -> str:
    match = re.search(r'^\s*__version__\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE)
    if not match:
        raise VersionDrift("src/axiomize/__init__.py has no literal __version__")
    return match.group(1).strip()


def _package_json_version(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VersionDrift(f"package.json is not valid JSON: {exc}") from exc
    version = payload.get("version")
    if not isinstance(version, str) or not version:
        raise VersionDrift("package.json has no string version")
    return version.strip()


def _changelog_version(text: str) -> str:
    match = re.search(r"^## \[([^\]]+)\]", text, re.MULTILINE)
    if not match:
        raise VersionDrift("CHANGELOG.md has no '## [version]' release heading")
    return match.group(1).strip()


def _trigger_version(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        raise VersionDrift(f"{TRIGGER_REL.as_posix()} is empty")
    match = re.fullmatch(r"axiomize-quantum-skills-2\.0\s+(\S+)", lines[0].strip())
    if not match:
        raise VersionDrift(
            "first line of "
            f"{TRIGGER_REL.as_posix()} must be: axiomize-quantum-skills-2.0 <version>"
        )
    return match.group(1).strip()


def collect() -> dict[str, str]:
    """Return ``{source: version}`` for every version-bearing file."""
    return {
        "pyproject": _pyproject_version(_read(ROOT / "pyproject.toml")),
        "runtime": _runtime_version(_read(ROOT / "src" / "axiomize" / "__init__.py")),
        "package_json": _package_json_version(_read(ROOT / "package.json")),
        "changelog": _changelog_version(_read(ROOT / "CHANGELOG.md")),
        "pypi_trigger": _trigger_version(_read(ROOT / TRIGGER_REL)),
    }


def assert_lockstep() -> dict[str, str]:
    """Return the versions when they agree, raise :class:`VersionDrift` if not."""
    versions = collect()
    if not SEMVER.fullmatch(versions["pyproject"]):
        raise VersionDrift(
            f"pyproject version {versions['pyproject']!r} is not plain semver"
        )
    distinct = sorted(set(versions.values()))
    if len(distinct) != 1:
        detail = "\n".join(f"  {name:14s} {value}" for name, value in versions.items())
        raise VersionDrift(f"version sources disagree:\n{detail}")
    return versions


def write_all(version: str) -> list[Path]:
    """Rewrite every version-bearing file to ``version``.

    Returns the paths that changed. Used by ``--bump`` so a release is one
    command rather than five coordinated edits.
    """
    if not SEMVER.fullmatch(version):
        raise VersionDrift(f"{version!r} is not plain semver (expected MAJOR.MINOR.PATCH)")

    changed: list[Path] = []

    pyproject_path = ROOT / "pyproject.toml"
    pyproject = _read(pyproject_path)
    project_end = pyproject.index("[project]", 1)
    table_end = pyproject.index("\n[", project_end)
    head, table, tail = pyproject[:project_end], pyproject[project_end:table_end], pyproject[table_end:]
    new_table, count = re.subn(
        r'^(\s*version\s*=\s*)"[^"]+"(\s*)$',
        rf'\g<1>"{version}"\g<2>',
        table,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise VersionDrift("could not rewrite pyproject.toml [project] version")
    if new_table != table:
        pyproject_path.write_text(head + new_table + tail, encoding="utf-8")
        changed.append(pyproject_path)

    init_path = ROOT / "src" / "axiomize" / "__init__.py"
    init = _read(init_path)
    new_init, count = re.subn(
        r'^(__version__\s*=\s*)"[^"]+"',
        rf'\g<1>"{version}"',
        init,
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise VersionDrift("could not rewrite src/axiomize/__init__.py __version__")
    if new_init != init:
        init_path.write_text(new_init, encoding="utf-8")
        changed.append(init_path)

    pkg_path = ROOT / "package.json"
    pkg = json.loads(_read(pkg_path))
    if pkg.get("version") != version:
        pkg["version"] = version
        pkg_path.write_text(json.dumps(pkg, indent=2) + "\n", encoding="utf-8")
        changed.append(pkg_path)

    changelog_path = ROOT / "CHANGELOG.md"
    changelog = _read(changelog_path)
    current = _changelog_version(changelog)
    if current != version:
        # The unreleased heading already carries the date the release was cut.
        changelog, count = re.subn(
            r"^## \[[^\]]+\]",
            f"## [{version}]",
            changelog,
            count=1,
            flags=re.MULTILINE,
        )
        if count != 1:
            raise VersionDrift("could not rewrite CHANGELOG.md release heading")
        changelog_path.write_text(changelog, encoding="utf-8")
        changed.append(changelog_path)

    trigger_path = ROOT / TRIGGER_REL
    trigger_lines = _read(trigger_path).splitlines()
    if trigger_lines and _trigger_version("\n".join(trigger_lines)) != version:
        trigger_lines[0] = f"axiomize-quantum-skills-2.0 {version}"
        trigger_path.write_text("\n".join(trigger_lines) + "\n", encoding="utf-8")
        changed.append(trigger_path)

    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    parser.add_argument(
        "--bump",
        metavar="X.Y.Z",
        help="rewrite every version source to this version, then re-verify",
    )
    args = parser.parse_args(argv)

    if args.bump:
        try:
            changed = write_all(args.bump)
        except VersionDrift as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        for path in changed:
            print(f"updated {path.relative_to(ROOT).as_posix()}")
        if not changed:
            print(f"nothing to update: already at {args.bump}")

    # Collected up front so a failure report can still show what each source
    # currently says, including sources that are themselves unreadable.
    versions = collect()
    try:
        versions = assert_lockstep()
    except VersionDrift as exc:
        if args.json:
            print(json.dumps({"ok": False, "error": str(exc), "versions": versions}, indent=2))
        else:
            print(f"FAIL: {exc}", file=sys.stderr)
            for name in SOURCES:
                print(f"  {name:14s} {versions.get(name, '<unreadable>')}")
        return 1

    if args.json:
        print(json.dumps({"ok": True, "version": versions["pyproject"], "versions": versions}, indent=2))
    else:
        for name in SOURCES:
            print(f"{name:14s} {versions[name]}")
        print(f"PASS: {len(SOURCES)} version sources agree on {versions['pyproject']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
