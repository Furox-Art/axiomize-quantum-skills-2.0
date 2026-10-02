#!/usr/bin/env python3
"""Stage the browsable docs pages out of skills/ and examples/, then verify them.

Shared by the Pages build and the pull-request docs check so the two cannot
drift; they previously carried near-identical inline shell, which is how the
link-rewriting below came to point at the wrong repository unnoticed.

What it produces
----------------
* ``docs/rigor.md``, ``docs/archetypes.md``, ``docs/adaptive-workflow.md`` --
  verbatim copies, so their internal relative links keep working inside
  ``docs/``.
* ``docs/skill.md`` -- SKILL.md with the heads of all 15 perspective files
  appended, because a lens is worth reading in full only from the repository.
* ``docs/examples.md`` -- the heads of every worked example.

The link rewriting, and the bug it fixes
----------------------------------------
SKILL.md is authored to be browsed *inside* ``skills/axiomize/``, so it links to
``perspectives/foo.md``, ``templates/bar.md`` and ``first-principles.md``
relatively. Those paths do not resolve once the text is concatenated into
``docs/skill.md``: ``docs/perspectives/`` does not exist, and
``mkdocs build --strict`` does not catch a link that leaves the site, so the
build passed while every lens link was dead.

The previous rewrite sent them to ``Furox-Art/axiomize``, a *different*
repository that happens to publish a similar-looking ``skills/axiomize/``
tree. The content published here is staged from this repository, so a reader who
followed a lens link was sent to another project's file, and a divergence
between the two would be invisible from the docs site. The rewrite now targets
this repository, and :func:`verify_no_foreign_links` fails the build if any link
in the staged pages points at a repository other than this one.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills" / "axiomize"
DOCS = ROOT / "docs"
EXAMPLES = ROOT / "examples"

#: The repository whose content is published on this site. Every rewritten link
#: must resolve here; :func:`verify_no_foreign_links` enforces it.
REPO_SLUG = "Furox-Art/axiomize-quantum-skills-2.0"
REPO_BRANCH = "main"
SKILL_TREE_URL = f"https://github.com/{REPO_SLUG}/tree/{REPO_BRANCH}/skills/axiomize"
EXAMPLES_TREE_URL = f"https://github.com/{REPO_SLUG}/tree/{REPO_BRANCH}/examples"

#: How many lines of each perspective / example are inlined. The full text lives
#: in the repository and is linked, not duplicated into the site.
PERSPECTIVE_HEAD_LINES = 12
EXAMPLE_HEAD_LINES = 8

#: The 15 lens filenames. Kept as an explicit list, not a directory glob, so
#: that a newly added perspective has to be registered here rather than silently
#: keeping a link that resolves to nothing.
LENS_NAMES = (
    "agent-based",
    "causal-inference",
    "control",
    "decision-theory",
    "demographic",
    "deterministic",
    "game-theory",
    "information-theory",
    "network",
    "optimization",
    "reliability",
    "spatial",
    "spc",
    "stochastic",
    "thermodynamic",
)

_ALTERNATION = "|".join(re.escape(name) for name in LENS_NAMES)

#: A lens linked by bare filename, as in `[optimization](optimization.md)`. Used
#: both in SKILL.md and in the "See also" lines of the perspective files. One
#: pattern covers both, so there is a single place where the lens link shape is
#: recognised.
_BARE_LENS_LINK = re.compile(rf"\]\(({_ALTERNATION})\.md\)")

#: Any absolute http(s) URL inside the staged pages.
_ABSOLUTE_URL = re.compile(r"\]\((https?://[^)\s]+)\)")


def _head(path: Path, lines: int) -> str:
    """Return the first ``lines`` lines of ``path``, newline-terminated."""
    text = path.read_text(encoding="utf-8")
    kept = text.splitlines(keepends=True)[:lines]
    return "".join(kept)


def stage() -> list[Path]:
    """Write the staged pages into docs/ and return the paths written."""
    DOCS.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for name in ("rigor.md", "archetypes.md", "adaptive-workflow.md"):
        target = DOCS / name
        target.write_text((SKILLS / name).read_text(encoding="utf-8"), encoding="utf-8")
        written.append(target)

    parts = [
        "# The workflow\n",
        # Rewritten here rather than after the fact, so the links in the staged
        # page can never point anywhere but this repository.
        rewrite_links((SKILLS / "SKILL.md").read_text(encoding="utf-8")),
        "\n\n# The lenses\n\n",
    ]
    for perspective in sorted((SKILLS / "perspectives").glob("*.md")):
        parts.append(f"## {perspective.stem}\n\n")
        # The inlined heads carry their own relative links, e.g.
        # `[optimization](optimization.md)` and
        # `../../../examples/supply-chain-inventory.md`. They are rewritten for
        # the same reason SKILL.md is: inside docs/skill.md the relative base is
        # docs/, where neither path exists.
        parts.append(rewrite_links(_head(perspective, PERSPECTIVE_HEAD_LINES)))
        parts.append("\n")
    skill_md = DOCS / "skill.md"
    skill_md.write_text("".join(parts), encoding="utf-8")
    written.append(skill_md)

    example_parts = ["# Worked examples\n"]
    for example in sorted(EXAMPLES.glob("*.md")):
        example_parts.append(f"## {example.stem}\n\n")
        example_parts.append(_head(example, EXAMPLE_HEAD_LINES))
        example_parts.append("\n")
    examples_md = DOCS / "examples.md"
    examples_md.write_text("".join(example_parts), encoding="utf-8")
    written.append(examples_md)

    return written


def rewrite_links(text: str) -> str:
    """Point repository-relative links in staged text at this repository.

    Applied to SKILL.md and to each inlined perspective head. The text is
    authored to be browsed inside ``skills/axiomize/``, so it links to
    ``perspectives/foo.md``, ``templates/bar.md``, a sibling lens
    (``optimization.md``) and ``../../../examples/x.md``. None of those resolve
    once the text is concatenated into ``docs/skill.md``: the relative base is
    ``docs/``, and ``mkdocs build --strict`` does not flag a link that leaves the
    site, so the build passed with every lens link dead.

    ``docs/rigor.md``, ``docs/archetypes.md`` and ``docs/adaptive-workflow.md``
    are verbatim copies whose links are already relative to ``docs/`` and are
    deliberately not rewritten.
    """
    text = text.replace(f"](perspectives/", f"]({SKILL_TREE_URL}/perspectives/")
    text = text.replace(f"](templates/", f"]({SKILL_TREE_URL}/templates/")
    text = text.replace("](first-principles.md", f"]({SKILL_TREE_URL}/first-principles.md")
    text = _BARE_LENS_LINK.sub(
        lambda m: f"]({SKILL_TREE_URL}/perspectives/{m.group(1)}.md", text
    )
    # `../../../examples/<name>.md`, authored from three levels down inside
    # skills/axiomize/perspectives/.
    text = re.sub(
        r"\]\(\.\./\.\./\.\./examples/([^)\s]+\.md)\)",
        lambda m: f"]({EXAMPLES_TREE_URL}/{m.group(1)})",
        text,
    )
    return text


def verify_no_foreign_links() -> list[str]:
    """Return a failure per absolute link that leaves this repository.

    A link to another repository's path in a page assembled from this
    repository's files is always wrong: the reader is sent somewhere that is not
    the source of what they just read. A link to ``github.com/Furox-Art`` (the
    user profile) or to an external project is fine, so only URLs that name a
    different *repository path* are rejected.
    """
    failures: list[str] = []
    for name in ("skill.md", "examples.md"):
        path = DOCS / name
        if not path.is_file():
            continue
        for match in _ABSOLUTE_URL.finditer(path.read_text(encoding="utf-8")):
            url = match.group(1)
            parsed = urlparse(url)
            if parsed.netloc not in {"github.com", "www.github.com", "raw.githubusercontent.com"}:
                continue
            parts = [p for p in parsed.path.split("/") if p]
            # /owner/repo/... -- anything deeper than the repository's own name
            # is a link into a project; only ours is acceptable.
            if len(parts) >= 2 and parts[0] == REPO_SLUG.split("/")[0] and parts[1] != REPO_SLUG.split("/")[1]:
                failures.append(f"docs/{name} links into another repository: {url}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="skip staging and only verify the pages already in docs/",
    )
    args = parser.parse_args(argv)

    if args.verify_only:
        skill_md = DOCS / "skill.md"
        if not skill_md.is_file():
            print("FAIL: docs/skill.md is missing; run without --verify-only first", file=sys.stderr)
            return 1
        # In --verify-only mode the pages are already rewritten, so only the
        # foreign-link check is meaningful.
        failures = verify_no_foreign_links()
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        if failures:
            return 1
        print("PASS: staged docs carry no links into another repository")
        return 0

    written = stage()

    failures = verify_no_foreign_links()
    if failures:
        print("FAIL: staging produced links into another repository:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    for path in written:
        print(f"staged {path.relative_to(ROOT).as_posix()}")
    print(f"link target: {SKILL_TREE_URL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
