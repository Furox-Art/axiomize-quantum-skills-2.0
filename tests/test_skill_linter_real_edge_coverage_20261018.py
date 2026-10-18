"""Real skill-package linter, linked docs and compilation failure contracts."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SRC = Path(__file__).resolve().parents[1] / "skills" / "axiomize" / "tools" / "check_skill.py"
SPEC = importlib.util.spec_from_file_location("axiomize_skill_linter_for_coverage", SRC)
assert SPEC is not None and SPEC.loader is not None
checker = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(checker)


@pytest.fixture
def skill(tmp_path):
    folder = tmp_path / "skills" / "axiomize"
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        "---\nname: axiomize\ndescription: Use when deterministic numerical models need explicit verification and provenance evidence\n---\n\n# Skill\n",
        encoding="utf-8",
    )
    (folder / "tools").mkdir()
    (folder / "tools" / "valid.py").write_text("def test():\n    return 1\n")
    return folder


def test_real_skill_directory_discovery_from_nested_tool_path(skill):
    assert checker.find_skill_dir(skill / "tools") == skill
    assert checker.find_skill_dir(skill.parent.parent) == skill


def test_skill_directory_discovery_fails_in_unrelated_folder(tmp_path):
    with pytest.raises(SystemExit, match="could not locate"):
        checker.find_skill_dir(tmp_path)


def test_child_skill_directories_included_without_duplicate_primary(skill):
    child = skill.parent / "secondary"
    child.mkdir()
    (child / "SKILL.md").write_text("---\nname: secondary\n---\n")
    paths = checker.find_all_skill_dirs(skill)
    assert paths == [skill, child]


def test_all_valid_skill_frontmatter_requirements_are_met(skill):
    result = checker.check_frontmatter(skill)
    assert all(result.values())


def test_skill_frontmatter_missing_is_rejected(skill):
    (skill / "SKILL.md").write_text("# Missing frontmatter\n")
    with pytest.raises(AssertionError, match="no frontmatter"):
        checker.check_frontmatter(skill)


@pytest.mark.parametrize("frontmatter,field", [
    ("description: Use when a very long tested scientific description is present", "name present"),
    ("name: Upper_Case\ndescription: Use when a very long tested scientific description is present", "name valid"),
    ("name: not-axiomize\ndescription: Use when a very long tested scientific description is present", "folder matches name"),
    ("name: axiomize\ndescription: short", "description present"),
    ("name: axiomize\ndescription: A sufficiently long scientific text without the exact trigger phrase", "trigger phrase"),
])
def test_invalid_frontmatter_predicate_is_recorded(skill, frontmatter, field):
    (skill / "SKILL.md").write_text(f"---\n{frontmatter}\n---\n", encoding="utf-8")
    assert checker.check_frontmatter(skill)[field] is False


def test_external_links_do_not_claim_broken_local_references(skill):
    md = skill / "links.md"
    md.write_text("[web](https://example.com) [mail](mailto:a@example.com) [anchor](#heading)")
    assert checker.check_links([md]) == []


def test_missing_local_reference_is_reported_with_original_target(skill):
    md = skill / "links.md"
    md.write_text("[missing](absent.md)")
    assert checker.check_links([md]) == [(md, "absent.md")]


def test_real_existing_relative_python_reference_is_valid(skill):
    md = skill / "links.md"
    md.write_text("[tool](tools/valid.py)")
    assert checker.check_links([md]) == []


def test_real_directory_link_with_python_suffix_is_rejected(skill):
    (skill / "isdir.py").mkdir()
    md = skill / "links.md"
    md.write_text("[wrong](isdir.py)")
    assert checker.check_links([md]) == [(md, "isdir.py")]


def test_real_linter_accepts_a_valid_skill(monkeypatch, skill, capsys):
    monkeypatch.setattr(checker, "find_all_skill_dirs", lambda _: [skill])
    assert checker.main() == 0
    assert "RESULT: PASS" in capsys.readouterr().out


def test_real_linter_reports_malformed_frontmatter(monkeypatch, skill, capsys):
    monkeypatch.setattr(checker, "find_all_skill_dirs", lambda _: [skill])
    (skill / "SKILL.md").write_text("No frontmatter")
    assert checker.main() == 1
    assert "frontmatter" in capsys.readouterr().out


def test_real_linter_reports_broken_relative_link(monkeypatch, skill, capsys):
    monkeypatch.setattr(checker, "find_all_skill_dirs", lambda _: [skill])
    (skill / "doc.md").write_text("[broken](notfound.md)")
    assert checker.main() == 1
    assert "broken link" in capsys.readouterr().out


def test_real_linter_refuses_syntactically_invalid_python(monkeypatch, skill, capsys):
    monkeypatch.setattr(checker, "find_all_skill_dirs", lambda _: [skill])
    (skill / "tools" / "invalid.py").write_text("def broken( :\n")
    assert checker.main() == 1
    assert "compiles / invalid.py" in capsys.readouterr().out
