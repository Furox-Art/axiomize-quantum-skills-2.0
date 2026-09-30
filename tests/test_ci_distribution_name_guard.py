"""Guard CI helper scripts against stale distribution-name references.

Closes issue #7. The distribution in ``pyproject.toml`` and the strings that
``.github/scripts/*.py`` hard-code drift apart easily: renaming a package
leaves ``metadata.version("old-name")`` behind and every platform smoke job
dies with ``PackageNotFoundError``, and the wheel glob keeps matching zero
artifacts because wheel filenames normalise ``-`` (and ``.``) to ``_`` per
PEP 427 / the modern setuptools escaping.

The test therefore never hard-codes the name itself. It reads
``[project] name`` from ``pyproject.toml`` and asserts every distribution
lookup and wheel glob in the CI helper scripts agrees with it.

Runnable both under pytest and as a script for stale-detection checks::

    python tests/test_ci_distribution_name_guard.py --scripts <dir>
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
SCRIPTS_DIRNAME = Path(".github") / "scripts"

# ``metadata.version("x")``, ``importlib.metadata.version('x')``, ``m.version("x")``.
VERSION_LOOKUP = re.compile(r"""\.\s*version\(\s*(?P<q>["'])(?P<name>[^"']+)(?P=q)\s*\)""")
# Any string literal that carries a ``.whl`` suffix, e.g. "pkg_name-1.0-py3-none-any.whl".
WHEEL_LITERAL = re.compile(r"""(?P<q>["'])(?P<literal>[^"']*\.whl)(?P=q)""")
# The escaped wheel filename prefix must precede the version part of the wheel name.
WHEEL_PREFIX = re.compile(r"^(?P<stem>.+?)-\d")


def distribution_name(pyproject: Path = PYPROJECT) -> str:
    """Return ``[project] name`` from pyproject.toml without extra dependencies."""
    text = pyproject.read_text(encoding="utf-8")
    in_project = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_project = stripped == "[project]"
            continue
        if in_project and stripped.startswith("name"):
            key, _, value = stripped.partition("=")
            if key.strip() != "name":
                continue
            return value.strip().strip("\"'").strip()
    raise AssertionError(f"pyproject.toml has no [project] name: {pyproject}")


def wheel_escaped(name: str) -> str:
    """Escape a distribution name the way wheel filenames do (``-`` and ``.`` -> ``_``)."""
    return re.sub(r"[-_.]+", "_", name).lower()


def _script_files(scripts_dir: Path) -> list[Path]:
    return sorted(scripts_dir.glob("*.py"))


def _version_lookup_findings(scripts_dir: Path) -> list[str]:
    dist = distribution_name()
    findings = []
    for path in _script_files(scripts_dir):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in VERSION_LOOKUP.finditer(line):
                found = match.group("name")
                if found != dist:
                    findings.append(
                        f"{path}:{lineno}: metadata.version({found!r}) "
                        f"but the distribution is {dist!r}"
                    )
    return findings


def _wheel_glob_findings(scripts_dir: Path) -> list[str]:
    dist = distribution_name()
    expected = wheel_escaped(dist)
    findings = []
    for path in _script_files(scripts_dir):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for match in WHEEL_LITERAL.finditer(line):
                literal = match.group("literal")
                stem_match = WHEEL_PREFIX.match(literal)
                stem = stem_match.group("stem") if stem_match else literal
                if expected not in stem.lower():
                    findings.append(
                        f"{path}:{lineno}: wheel literal {literal!r} does not match the "
                        f"escaped distribution name {expected!r} (PEP 427: - and . become _)"
                    )
    return findings


def find_all(scripts_dir: Path = REPO_ROOT / SCRIPTS_DIRNAME) -> list[str]:
    if not scripts_dir.is_dir():
        raise AssertionError(f"CI helper script directory not found: {scripts_dir}")
    return _version_lookup_findings(scripts_dir) + _wheel_glob_findings(scripts_dir)


def test_pyproject_declares_distribution_name():
    dist = distribution_name()
    assert dist, "pyproject.toml [project] name must not be empty"
    assert wheel_escaped(dist), "escaped distribution name must not be empty"


def test_wheel_escaping_replaces_dash_and_dot():
    # The subtlety that caused the original bug, pinned explicitly.
    assert wheel_escaped("axiomize-quantum-skills-2.0") == "axiomize_quantum_skills_2_0"
    assert wheel_escaped("some-package") == "some_package"
    assert wheel_escaped("some_package") == "some_package"


def test_ci_scripts_have_no_stale_distribution_name():
    findings = find_all()
    assert not findings, "stale distribution-name references in CI helper scripts:\n  " + "\n  ".join(
        findings
    )


def _copy_scripts_to(tmp_path: Path) -> Path:
    source = REPO_ROOT / SCRIPTS_DIRNAME
    target = tmp_path / "scripts"
    target.mkdir()
    for path in _script_files(source):
        shutil.copy2(path, target / path.name)
    return target


def test_guard_detects_stale_metadata_version_lookup(tmp_path):
    """The original bug: a helper still asking for the pre-rename distribution."""
    target = _copy_scripts_to(tmp_path)
    dist = distribution_name()
    victim = target / "cli_release_smoke.py"
    text = victim.read_text(encoding="utf-8")
    assert f'metadata.version("{dist}")' in text, "fixture drift: expected a real lookup to corrupt"
    victim.write_text(
        text.replace(f'metadata.version("{dist}")', 'metadata.version("axiomize")'), encoding="utf-8"
    )
    findings = find_all(target)
    assert any("cli_release_smoke.py" in f and "'axiomize'" in f for f in findings), findings


def test_guard_detects_stale_wheel_glob(tmp_path):
    """The subtler original bug: wheel filenames escape - and . to _ (PEP 427)."""
    target = _copy_scripts_to(tmp_path)
    expected = wheel_escaped(distribution_name())
    victim = target / "platform_wheel_cli_smoke.py"
    text = victim.read_text(encoding="utf-8")
    assert f"{expected}-*.whl" in text, "fixture drift: expected a real wheel glob to corrupt"
    victim.write_text(
        text.replace(f"{expected}-*.whl", "axiomize-*.whl"), encoding="utf-8"
    )
    findings = find_all(target)
    assert any("platform_wheel_cli_smoke.py" in f and "PEP 427" in f for f in findings), findings


def test_guard_flags_offending_file_and_line_number(tmp_path):
    """A useful failure names the file and the line, per the issue request."""
    target = _copy_scripts_to(tmp_path)
    dist = distribution_name()
    victim = target / "cli_release_smoke.py"
    lines = victim.read_text(encoding="utf-8").splitlines(keepends=True)
    expected_lineno = next(i for i, l in enumerate(lines, 1) if f'metadata.version("{dist}")' in l)
    lines[expected_lineno - 1] = lines[expected_lineno - 1].replace(dist, "wrong-dist")
    victim.write_text("".join(lines), encoding="utf-8")
    findings = find_all(target)
    assert any(f"cli_release_smoke.py:{expected_lineno}:" in f for f in findings), findings


def test_cli_entrypoint_exit_codes(tmp_path):
    assert main(["--scripts", str(REPO_ROOT / SCRIPTS_DIRNAME)]) == 0
    target = _copy_scripts_to(tmp_path)
    dist = distribution_name()
    victim = target / "cli_release_smoke.py"
    victim.write_text(
        victim.read_text(encoding="utf-8").replace(dist, "wrong-dist"), encoding="utf-8"
    )
    assert main(["--scripts", str(target)]) == 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scripts",
        default=str(REPO_ROOT / SCRIPTS_DIRNAME),
        help="directory holding the CI helper scripts to scan",
    )
    args = parser.parse_args(argv)
    findings = find_all(Path(args.scripts))
    if findings:
        print(f"FAIL: {len(findings)} stale distribution-name reference(s):")
        for finding in findings:
            print(f"  {finding}")
        return 1
    print(f"OK: CI helper scripts agree with distribution {distribution_name()!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
