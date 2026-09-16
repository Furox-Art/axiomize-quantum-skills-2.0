"""Axiomize skill linter.

Validates what the opencode/Claude skill loaders expect and what the repo
promises, so regressions never ship:

  1. SKILL.md frontmatter: name present, lowercase-hyphen, matches folder,
     description long enough and contains a trigger phrase.
  2. Every relative markdown link in every *.md resolves to a real file.
  3. The bundled tools import cleanly (syntax-level compile check).

Usage:
    python check_skill.py            # from anywhere; locates repo root
"""

import py_compile
import re
import sys
from pathlib import Path

TRIGGERS = ("Use when", "Use ONLY when", "use when")
NAME_RE = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")
LINK_RE = re.compile(r"\]\(([^)#\s][^)]*)\)")


def find_skill_dir(start: Path) -> Path:
    for cand in [start, *start.parents]:
        if cand.name == "axiomize" and (cand / "SKILL.md").exists():
            return cand
        if (cand / "skills" / "axiomize" / "SKILL.md").exists():
            return cand / "skills" / "axiomize"
    raise SystemExit("FAIL: could not locate skills/axiomize/SKILL.md")


def find_all_skill_dirs(start: Path) -> list[Path]:
    """Return every skill folder in the repo (any dir with a SKILL.md).

    Axiomize keeps more than one model-facing skill in this repository, so the
    linter validates all of them, not just ``skills/axiomize``.
    """
    primary = find_skill_dir(start)
    skills_root = primary.parent
    dirs = [primary]
    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        if skill_md.parent != primary:
            dirs.append(skill_md.parent)
    return dirs


def check_frontmatter(skill_dir: Path):
    text = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    assert m, "SKILL.md has no frontmatter"
    fm = m.group(1)
    name = re.search(r"name:\s*(\S+)", fm)
    desc = re.search(r"description:\s*(.+)", fm)
    checks = {
        "name present": bool(name),
        "name valid": bool(name and NAME_RE.fullmatch(name.group(1))),
        "folder matches name": bool(name and name.group(1) == skill_dir.name),
        "description present": bool(desc and len(desc.group(1).strip()) > 40),
        "trigger phrase": bool(desc and any(t in desc.group(1) for t in TRIGGERS)),
    }
    return checks


def check_links(md_files):
    broken = []
    for f in md_files:
        text = f.read_text(encoding="utf-8")
        for m in LINK_RE.finditer(text):
            target = m.group(1).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            resolved = (f.parent / target).resolve()
            suffix = resolved.suffix.lower()
            if suffix in {".md", ".py", ".yml", ".json", ".txt"} or not suffix:
                if not resolved.exists() or (resolved.is_file() is False and suffix):
                    broken.append((f, target))
    return broken


def main():
    here = Path(__file__).resolve().parent
    skill_dirs = find_all_skill_dirs(here.parent)
    primary = skill_dirs[0]
    failures = []

    for skill_dir in skill_dirs:
        print(f"skill dir : {skill_dir}")
        try:
            fm_checks = check_frontmatter(skill_dir)
            for k, ok in fm_checks.items():
                print(f"frontmatter / {k:24s} {'PASS' if ok else 'FAIL'}")
                failures += [] if ok else [f"frontmatter:{skill_dir.name}"]
        except AssertionError as e:
            print(f"frontmatter               FAIL ({e})")
            failures.append(f"frontmatter:{skill_dir.name}")

    md_files = sorted(p for p in primary.rglob("*.md")) + sorted(
        p for p in primary.parents[0].rglob("*.md") if not str(p).startswith(str(primary))
    )
    md_files = list(dict.fromkeys(md_files))
    broken = check_links([p for p in md_files if p.exists()])
    if broken:
        for f, t in broken:
            try:
                shown = f.relative_to(primary)
            except ValueError:
                shown = f.relative_to(primary.parents[0])
            print(f"broken link: {shown} -> {t}")
        failures.append("links")
    else:
        print(f"relative links            PASS ({len(md_files)} md files scanned)")

    for skill_dir in skill_dirs:
        for tool in sorted((skill_dir / "tools").glob("*.py")):
            try:
                py_compile.compile(str(tool), doraise=True)
                print(f"compiles / {tool.name:22s} PASS")
            except py_compile.PyCompileError as e:
                print(f"compiles / {tool.name:22s} FAIL")
                print(e)
                failures.append(f"compile:{tool.name}")

    if failures:
        print(f"\nRESULT: FAIL ({failures})")
        return 1
    print("\nRESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
