#!/usr/bin/env python3
"""Fail when a page under ``docs/`` cannot be reached from the mkdocs navigation.

``mkdocs build --strict`` promotes link, reference and heading problems to
errors, but a page that exists and is simply absent from ``nav`` is only an
``INFO`` line, so the build succeeds and the page ships unreachable. Fourteen
pages were in that state on ``main``, including every security document, the
tutorial and the benchmark results.

This script closes that hole and runs after ``mkdocs build --strict``, so a new
page has to be either linked from the navigation or moved out of ``docs/``.

Usage::

    python .github/scripts/check_docs_nav.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "docs"

#: Pages staged into docs/ by the Pages workflow from skills/ and examples/.
#: Gitignored, never committed, and listed in nav because they are part of the
#: built site.
GENERATED = frozenset(
    {
        "rigor.md",
        "archetypes.md",
        "adaptive-workflow.md",
        "skill.md",
        "examples.md",
    }
)


def _nav_targets(node: object, found: set[str]) -> None:
    """Collect every page path referenced by a ``nav`` tree.

    A nav entry is either a bare path (``- index.md``) or a mapping whose values
    are either a path, a nested list of entries, or ``None`` for a pure grouping
    label. Strings are the leaves, so a nested list has to be walked rather than
    iterated blindly.
    """
    if isinstance(node, str):
        found.add(node)
    elif isinstance(node, list):
        for entry in node:
            _nav_targets(entry, found)
    elif isinstance(node, dict):
        for value in node.values():
            _nav_targets(value, found)


def main() -> int:
    config_path = ROOT / "mkdocs.yml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        print(f"FAIL: {config_path.name} did not parse into a mapping", file=sys.stderr)
        return 1

    nav_targets: set[str] = set()
    _nav_targets(config.get("nav"), nav_targets)

    if not nav_targets:
        print("FAIL: mkdocs.yml declares an empty nav", file=sys.stderr)
        return 1

    if not DOCS_DIR.is_dir():
        print(f"FAIL: {DOCS_DIR} does not exist", file=sys.stderr)
        return 1

    pages = sorted(p.name for p in DOCS_DIR.glob("*.md"))
    orphans = [
        name
        for name in pages
        if name not in nav_targets and name not in GENERATED
    ]

    # A nav entry that does not exist is the inverse error and just as broken:
    # mkdocs would build a link to a page that was never written.
    dangling = sorted(
        target
        for target in nav_targets
        if target.endswith(".md")
        and not (DOCS_DIR / target).is_file()
        and target not in GENERATED
    )

    print(f"docs pages       : {len(pages)}")
    print(f"nav page targets : {len({t for t in nav_targets if t.endswith('.md')})}")

    if dangling:
        print(f"FAIL: mkdocs nav points at {len(dangling)} page(s) that do not exist:", file=sys.stderr)
        for target in dangling:
            print(f"  - {target}", file=sys.stderr)
        return 1

    if orphans:
        print(
            f"FAIL: {len(orphans)} docs/ page(s) are not reachable from the mkdocs nav:",
            file=sys.stderr,
        )
        for name in orphans:
            print(f"  - {name}", file=sys.stderr)
        print(
            "\nAdd each page to the mkdocs.yml nav, or move it out of docs/ if it is "
            "not part of the published site.",
            file=sys.stderr,
        )
        return 1

    print("PASS: every docs/ page is reachable from the navigation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
