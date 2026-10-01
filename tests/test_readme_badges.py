"""Guard the README against download claims that cannot stay true.

``https://img.shields.io/pypi/dm/<package>`` returns HTTP 200 while rendering
``downloads: inaccessible`` or ``downloads: rate limited by upstream service``,
because shields.io scrapes a third-party download API. The image therefore looks
live in the README while showing nothing, and a hand-copied number goes stale the
moment it is written down.

The rule enforced here: download claims are links to the package pages, which
always answer HTTP 200 and always carry the real numbers. The distribution name is
read from ``pyproject.toml`` so the check cannot drift from the package.

Runnable both under pytest and as a script::

    python tests/test_readme_badges.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
README = REPO_ROOT / "README.md"

# Any shields.io download endpoint: /pypi/dm, /pypi/dd, /pypi/dw, /pypi/dy.
DYNAMIC_DOWNLOAD_BADGE = re.compile(r"img\.shields\.io/pypi/d", re.I)
# A hand-copied count, e.g. "1,234 downloads", "500+ installs", "2k weekly downloads".
HAND_COPIED_COUNT = re.compile(
    r"\b\d[\d.,]*[km]?\s*\+?\s*(?:downloads?|installs?|weekly\s+downloads?)\b", re.I
)


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
            if key.strip() == "name":
                return value.strip().strip("\"'").strip()
    raise AssertionError(f"pyproject.toml has no [project] name: {pyproject}")


def findings(readme: Path = README) -> list[str]:
    """Return one message per download claim the README cannot keep true."""
    problems: list[str] = []
    for line_no, line in enumerate(readme.read_text(encoding="utf-8").splitlines(), 1):
        if DYNAMIC_DOWNLOAD_BADGE.search(line):
            problems.append(f"{README.name}:{line_no}: dynamic download badge: {line.strip()}")
        match = HAND_COPIED_COUNT.search(line)
        if match:
            problems.append(f"{README.name}:{line_no}: hand-copied count {match.group(0)!r}")
    return problems


def test_readme_has_no_dynamic_or_hand_copied_download_claims() -> None:
    problems = findings()
    assert not problems, "unreliable download claims in the README:\n  " + "\n  ".join(problems)


def test_readme_points_at_the_pypi_project_page() -> None:
    readme = README.read_text(encoding="utf-8")
    project_page = f"https://pypi.org/project/{distribution_name()}/"
    assert project_page in readme, f"README must link {project_page} for download numbers"
    assert "download numbers live on the package pages" in readme.lower(), (
        "README must state where download numbers come from"
    )


def test_guard_detects_a_reintroduced_dynamic_badge(tmp_path: Path) -> None:
    """The regression this check exists for: the badge came back and nobody noticed."""
    victim = tmp_path / "README.md"
    original = README.read_text(encoding="utf-8")
    victim.write_text(
        original + f"\n[![Downloads](https://img.shields.io/pypi/dm/{distribution_name()})]\n",
        encoding="utf-8",
    )
    problems = findings(victim)
    assert any("dynamic download badge" in p for p in problems), problems


def test_guard_detects_a_hand_copied_download_count(tmp_path: Path) -> None:
    victim = tmp_path / "README.md"
    victim.write_text(
        README.read_text(encoding="utf-8") + "\nUsed by 1,200 developers, 12k downloads.\n",
        encoding="utf-8",
    )
    problems = findings(victim)
    assert any("hand-copied count" in p for p in problems), problems


def main() -> int:
    problems = findings()
    if problems:
        print(f"FAIL: {len(problems)} unreliable download claim(s) in the README:")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print(f"OK: README download claims point at {distribution_name()!r} package pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())