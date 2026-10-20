"""Round-2 coverage hardening for the shipped skill tools.

Covers benchmark grading/linting/pre-flight CSV validation and the reference
SIR/Gillespie/Erlang-C validation CLI. All inputs are local and deterministic.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from axiomize.tools import benchmark_runner, check_skill, csv_check
from axiomize.tools import validate as validate_tool


# --------------------------------------------------------------------------- #
# benchmark_runner: bounded reads
# --------------------------------------------------------------------------- #

def test_bounded_text_rejects_missing_file(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        benchmark_runner._bounded_text(tmp_path / "missing.json", 10, "dataset")


def test_bounded_text_surfaces_stat_errors(tmp_path, monkeypatch):
    path = tmp_path / "data.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(Path, "is_file", lambda self: True)

    def explode(self):
        raise OSError("stat denied")

    monkeypatch.setattr(Path, "stat", explode)
    with pytest.raises(SystemExit, match="cannot stat dataset"):
        benchmark_runner._bounded_text(path, 10, "dataset")


def test_bounded_text_rejects_oversized_file(tmp_path):
    path = tmp_path / "data.json"
    path.write_text("0123456789", encoding="utf-8")
    with pytest.raises(SystemExit, match="exceeds hard size limit"):
        benchmark_runner._bounded_text(path, 5, "dataset")


def test_bounded_text_rejects_undecodable_file(tmp_path):
    path = tmp_path / "data.bin"
    path.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(SystemExit, match="cannot read dataset"):
        benchmark_runner._bounded_text(path, 100, "dataset")


# --------------------------------------------------------------------------- #
# benchmark_runner: load_cases
# --------------------------------------------------------------------------- #

def _dataset(tmp_path, payload, name="ideas.json"):
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_cases_requires_a_path():
    with pytest.raises(SystemExit, match="benchmark dataset not found"):
        benchmark_runner.load_cases("")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ("{not json", "invalid JSON"),
        ([], "must contain a cases array"),
        ({"cases": {}}, "must contain a cases array"),
    ],
)
def test_load_cases_rejects_malformed_datasets(tmp_path, payload, message):
    if isinstance(payload, str):
        path = tmp_path / "ideas.json"
        path.write_text(payload, encoding="utf-8")
    else:
        path = _dataset(tmp_path, payload)
    with pytest.raises(SystemExit, match=message):
        benchmark_runner.load_cases(path)


def test_load_cases_enforces_case_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_runner, "MAX_CASES", 1)
    path = _dataset(tmp_path, {"cases": [{"id": "a"}, {"id": "b"}]})
    with pytest.raises(SystemExit, match="hard case limit"):
        benchmark_runner.load_cases(path)


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("not-a-dict", r"case 0 needs a non-empty string id"),
        ({"id": 3}, r"case 0 needs a non-empty string id"),
        ({"id": "  "}, r"case 0 needs a non-empty string id"),
        ({"id": "a", "must_contain": "x"}, "invalid must_contain"),
        ({"id": "a", "must_contain": [1]}, "invalid must_contain"),
        ({"id": "a", "min_lenses_built": True}, "min_lenses_built must be an integer"),
        ({"id": "a", "min_lenses_built": 1001}, "min_lenses_built must be an integer"),
        ({"id": "a", "min_lenses_built": "3"}, "min_lenses_built must be an integer"),
    ],
)
def test_load_cases_rejects_invalid_case_records(tmp_path, case, message):
    path = _dataset(tmp_path, {"cases": [case]})
    with pytest.raises(SystemExit, match=message):
        benchmark_runner.load_cases(path)


def test_load_cases_rejects_too_many_patterns(tmp_path, monkeypatch):
    monkeypatch.setattr(benchmark_runner, "MAX_PATTERNS_PER_CASE", 1)
    path = _dataset(tmp_path, {"cases": [{"id": "a", "must_contain": ["x", "y"]}]})
    with pytest.raises(SystemExit, match="invalid must_contain"):
        benchmark_runner.load_cases(path)


def test_load_cases_rejects_duplicate_ids(tmp_path):
    path = _dataset(tmp_path, {"cases": [{"id": "a"}, {"id": "a"}]})
    with pytest.raises(SystemExit, match="duplicate benchmark case id"):
        benchmark_runner.load_cases(path)


def test_load_cases_indexes_valid_cases(tmp_path):
    path = _dataset(tmp_path, {"cases": [{"id": "a"}, {"id": "b", "must_contain": ["x|y"]}]})
    cases = benchmark_runner.load_cases(path)
    assert sorted(cases) == ["a", "b"]
    assert cases["b"]["must_contain"] == ["x|y"]


# --------------------------------------------------------------------------- #
# benchmark_runner: grading
# --------------------------------------------------------------------------- #

def test_grade_rejects_non_text():
    with pytest.raises(ValueError, match="report must be text"):
        benchmark_runner.grade(None, {"must_contain": []})


def test_grade_handles_empty_and_word_boundary_alternatives():
    checks, lenses = benchmark_runner.grade(
        "the alpha value is 1",
        {"must_contain": ["", r"\bbeta\b", r"\balpha\b"], "min_lenses_built": 0},
    )
    assert checks["must_contain[1]: "] is False
    assert checks["must_contain[2]: \\bbeta\\b"] is False
    assert checks["must_contain[3]: \\balpha\\b"] is True
    assert lenses == 0


def test_grade_archetype_token_matching_ignores_stopwords():
    checks, _ = benchmark_runner.grade(
        "A deterministic compartment model with network structure.",
        {"must_contain": [], "expected_archetype": "network / compartment",
         "min_lenses_built": 0},
    )
    assert checks["archetype 'network / compartment' present"] is True
    checks, _ = benchmark_runner.grade(
        "nothing relevant here at all",
        {"must_contain": [], "expected_archetype": "network", "min_lenses_built": 0},
    )
    assert checks["archetype 'network' present"] is False
    checks, _ = benchmark_runner.grade(
        "nothing relevant", {"must_contain": [], "min_lenses_built": 0}
    )
    assert checks["archetype present"] is False


def test_grade_counts_perspective_section_lenses():
    report = (
        "## 4. Perspective models\n"
        "### Lens A\n### Lens B\n### Excluded\n### Derived\n"
        "## 5. Next\n"
    )
    checks, lenses = benchmark_runner.grade(report, {"must_contain": [], "min_lenses_built": 2})
    assert lenses == 2
    assert checks["perspectives built >= 2 (found 2)"] is True


def test_grade_perspective_section_without_following_heading():
    report = "## 4 Perspective models\n### Lens A\n### Lens B\n"
    _, lenses = benchmark_runner.grade(report, {"must_contain": [], "min_lenses_built": 2})
    assert lenses == 2


def test_grade_falls_back_to_lens_headings_outside_section():
    report = "### Deterministic model\n### Stochastic model\n### Unrelated heading\n"
    _, lenses = benchmark_runner.grade(report, {"must_contain": [], "min_lenses_built": 2})
    assert lenses == 2


def test_grade_rejects_boolean_min_lenses():
    with pytest.raises(ValueError, match="min_lenses_built must be an integer"):
        benchmark_runner.grade("text", {"must_contain": [], "min_lenses_built": True})


def test_grade_checks_rejection_units_assumptions_and_falsifiability():
    report = (
        "Model rejected: no steady state.\n"
        "| Parameter | Unit | Class |\n|---|---|---|\n| beta | 1/day | endo |\n"
        "Violation consequence listed.\nFalsifiable prediction.\n"
    )
    checks, _ = benchmark_runner.grade(
        report,
        {"must_contain": [], "min_lenses_built": 0, "must_reject_at_least_one": True},
    )
    assert checks["rejection with reason present"] is True
    assert checks["parameter Unit column non-empty"] is True
    assert checks["assumptions have consequences column"] is True
    assert checks["falsifiability section"] is True


def test_grade_rejection_parenthetical_variant():
    checks, _ = benchmark_runner.grade(
        "(rejected because unstable)",
        {"must_contain": [], "min_lenses_built": 0, "must_reject_at_least_one": True},
    )
    assert checks["rejection with reason present"] is True


@pytest.mark.parametrize(
    "oracle",
    [
        "not-a-dict",
        {"keyword": "x", "expected": 1.0},
        {"keyword": "x", "expected": 1.0, "tolerance": -1.0},
        {"keyword": "x", "expected": float("inf"), "tolerance": 1.0},
    ],
)
def test_grade_rejects_invalid_numeric_oracle(oracle):
    with pytest.raises(ValueError, match="numeric_oracle|numeric oracle"):
        benchmark_runner.grade("x 1.0", {"must_contain": [], "min_lenses_built": 0,
                                       "numeric_oracle": oracle})


def test_grade_numeric_oracle_matches_and_misses():
    case = {
        "must_contain": [], "min_lenses_built": 0,
        "numeric_oracle": {"keyword": "peak", "expected": 10.0, "tolerance": 0.5},
    }
    checks, _ = benchmark_runner.grade("peak infected 10.2", case)
    assert checks["numeric oracle peak ~ 10.0 ±0.5"] is True
    checks, _ = benchmark_runner.grade("no number at all", case)
    assert checks["numeric oracle peak ~ 10.0 ±0.5"] is False


# --------------------------------------------------------------------------- #
# benchmark_runner: CLI
# --------------------------------------------------------------------------- #

def _run_cli(monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", ["axiomize-benchmark", *argv])
    code = benchmark_runner.main()
    return code, capsys.readouterr().out


def test_benchmark_cli_lists_cases(tmp_path, monkeypatch, capsys):
    path = _dataset(tmp_path, {"cases": [{"id": "case-a", "prompt": "do science"}]})
    code, out = _run_cli(monkeypatch, capsys, ["--benchmarks", str(path), "--case-list"])
    assert code == 0
    assert "case-a: do science" in out


def test_benchmark_cli_reports_unknown_case(tmp_path, monkeypatch, capsys):
    path = _dataset(tmp_path, {"cases": [{"id": "case-a"}]})
    code, out = _run_cli(monkeypatch, capsys, ["--benchmarks", str(path), "--case", "nope"])
    assert code == 1
    assert "unknown case 'nope'" in out


def test_benchmark_cli_requires_a_report_for_grading(tmp_path, monkeypatch, capsys):
    path = _dataset(tmp_path, {"cases": [{"id": "case-a"}]})
    code, out = _run_cli(monkeypatch, capsys, ["--benchmarks", str(path), "--case", "case-a"])
    assert code == 0
    assert "case-a" in out


def test_benchmark_cli_grades_a_report_to_pass(tmp_path, monkeypatch, capsys):
    path = _dataset(tmp_path, {"cases": [{"id": "case-a", "must_contain": ["sir"],
                                         "min_lenses_built": 0}]})
    report = tmp_path / "report.md"
    report.write_text(
        "SIR model\n| Parameter | Unit | Class |\n|---|---|---|\n| b | 1/day | endo |\n"
        "Violation consequence\nFalsifiable\n", encoding="utf-8")
    code, out = _run_cli(monkeypatch, capsys, ["--benchmarks", str(path), "--case", "case-a",
                                               "--report", str(report)])
    assert code == 0
    assert "PASS" in out


def test_benchmark_cli_reports_definition_error(tmp_path, monkeypatch, capsys):
    # load_cases does not validate numeric_oracle records, so grade() raises
    # ValueError and main() maps it to a definition-error exit.
    path = _dataset(tmp_path, {"cases": [{"id": "case-a", "min_lenses_built": 0,
                                         "must_contain": [],
                                         "numeric_oracle": {"keyword": "SIR"}}]})
    report = tmp_path / "report.md"
    report.write_text("SIR\n", encoding="utf-8")
    code, out = _run_cli(monkeypatch, capsys, ["--benchmarks", str(path), "--case", "case-a",
                                               "--report", str(report)])
    assert code == 1
    assert "benchmark definition error" in out
    assert "numeric_oracle requires" in out


# --------------------------------------------------------------------------- #
# csv_check
# --------------------------------------------------------------------------- #

def _csv(tmp_path, text, name="data.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_csv_load_surfaces_stat_error(tmp_path, monkeypatch):
    monkeypatch.setattr(csv_check.os.path, "getsize", lambda p: (_ for _ in ()).throw(OSError("denied")))
    with pytest.raises(SystemExit, match="cannot stat"):
        csv_check.load(tmp_path / "x.csv", "t", "y")


def test_csv_load_rejects_oversized_file(tmp_path, monkeypatch):
    path = _csv(tmp_path, "t,y\n1,2\n")
    monkeypatch.setattr(csv_check, "MAX_CSV_BYTES", 1)
    with pytest.raises(SystemExit, match="hard CSV size limit"):
        csv_check.load(path, "t", "y")


def test_csv_load_surfaces_open_error(tmp_path, monkeypatch):
    path = _csv(tmp_path, "t,y\n1,2\n")

    def explode(*args, **kwargs):
        raise OSError("cannot open")

    monkeypatch.setattr("builtins.open", explode)
    with pytest.raises(SystemExit, match="cannot open"):
        csv_check.load(path, "t", "y")


def test_csv_load_rejects_empty_file(tmp_path):
    path = _csv(tmp_path, "")
    with pytest.raises(SystemExit, match="is empty"):
        csv_check.load(path, "t", "y")


def test_csv_load_requires_explicit_columns(tmp_path):
    path = _csv(tmp_path, "t,y\n1,2\n")
    with pytest.raises(SystemExit, match="--time-col is required"):
        csv_check.load(path, None, "y")
    with pytest.raises(SystemExit, match="--value-col is required"):
        csv_check.load(path, "t", None)


def test_csv_load_rejects_unknown_columns(tmp_path):
    path = _csv(tmp_path, "t,y\n1,2\n")
    with pytest.raises(SystemExit, match="time column 'nope' not found"):
        csv_check.load(path, "nope", "y")
    with pytest.raises(SystemExit, match="value column 'nope' not found"):
        csv_check.load(path, "t", "nope")


def test_csv_load_skips_short_rows_and_parses_values(tmp_path):
    path = _csv(tmp_path, "t,y\n1,2\n3\n4,5\n")
    tname, vname, t, y = csv_check.load(path, "t", "y")
    assert (tname, vname) == ("t", "y")
    assert list(t) == [1.0, 4.0]
    assert list(y) == [2.0, 5.0]


def test_csv_load_enforces_row_limit(tmp_path, monkeypatch):
    path = _csv(tmp_path, "t,y\n1,2\n3,4\n")
    monkeypatch.setattr(csv_check, "MAX_DATA_ROWS", 1)
    with pytest.raises(SystemExit, match="hard row limit"):
        csv_check.load(path, "t", "y")


def test_csv_load_rejects_unparseable_and_nonfinite_rows(tmp_path):
    path = _csv(tmp_path, "t,y\n1,oops\n")
    with pytest.raises(SystemExit, match="cannot parse"):
        csv_check.load(path, "t", "y")
    path = _csv(tmp_path, "t,y\n1,nan\n", name="nan.csv")
    with pytest.raises(SystemExit, match="must be finite"):
        csv_check.load(path, "t", "y")


def test_csv_load_rejects_dataset_without_rows(tmp_path):
    path = _csv(tmp_path, "t,y\n")
    with pytest.raises(SystemExit, match="no parseable data rows"):
        csv_check.load(path, "t", "y")


def _csv_main(monkeypatch, capsys, argv):
    monkeypatch.setattr(sys, "argv", ["axiomize-csv-check", *argv])
    code = csv_check.main()
    return code, capsys.readouterr().out


def test_csv_main_passes_clean_data(tmp_path, monkeypatch, capsys):
    rows = "\n".join(f"{i},{i * 2 + 1}" for i in range(12))
    path = _csv(tmp_path, "t,y\n" + rows + "\n")
    code, out = _csv_main(monkeypatch, capsys, ["--data", str(path), "--time-col", "t",
                                                "--value-col", "y"])
    assert code == 0
    assert "PASS - safe to calibrate" in out


def test_csv_main_flags_duplicates_gaps_outliers_and_negative_values(tmp_path, monkeypatch, capsys):
    text = "t,y\n0,10\n0,12\n5,11\n4,13\n7,12\n8,11\n9,12\n10,13\n11,11\n12,12\n13,-5\n14,1000\n"
    path = _csv(tmp_path, text)
    code, out = _csv_main(monkeypatch, capsys, ["--data", str(path), "--time-col", "t",
                                                "--value-col", "y"])
    assert code == 1
    assert "not sorted" in out
    assert "WARNING" in out
    assert "FAIL - clean data" in out


def test_csv_main_rejects_unphysical_outlier_threshold(tmp_path, monkeypatch):
    path = _csv(tmp_path, "t,y\n1,2\n")
    monkeypatch.setattr(sys, "argv", ["axiomize-csv-check", "--data", str(path),
                                      "--time-col", "t", "--value-col", "y",
                                      "--z-outlier", "0"])
    with pytest.raises(SystemExit):
        csv_check.main()


# --------------------------------------------------------------------------- #
# check_skill
# --------------------------------------------------------------------------- #

def _fake_skill(root: Path, frontmatter: str, links: str = "") -> Path:
    skill = root / "skills" / "axiomize"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(frontmatter + links, encoding="utf-8")
    (skill / "tools").mkdir()
    (skill / "tools" / "tool.py").write_text("x = 1\n", encoding="utf-8")
    return skill


def test_find_skill_dir_fails_outside_a_repo(tmp_path):
    with pytest.raises(SystemExit, match="could not locate"):
        check_skill.find_skill_dir(tmp_path)


def test_find_skill_dir_accepts_the_skill_directory_itself(tmp_path):
    skill = _fake_skill(tmp_path, "---\nname: axiomize\ndescription: " + "d" * 50 + " Use when x\n---\n")
    assert check_skill.find_skill_dir(skill) == skill


def test_find_all_skill_dirs_includes_siblings_once(tmp_path):
    skill = _fake_skill(tmp_path, "---\nname: axiomize\ndescription: " + "d" * 50 + " Use when x\n---\n")
    sibling = tmp_path / "skills" / "other"
    sibling.mkdir()
    (sibling / "SKILL.md").write_text("---\nname: other\ndescription: " + "d" * 50 + " Use when y\n---\n",
                                      encoding="utf-8")
    dirs = check_skill.find_all_skill_dirs(tmp_path)
    assert dirs[0] == skill
    assert sorted(p.name for p in dirs) == ["axiomize", "other"]


def test_check_frontmatter_reports_each_predicate(tmp_path):
    skill = _fake_skill(tmp_path, "---\nname: other\ndescription: short\n---\n")
    checks = check_skill.check_frontmatter(skill)
    assert checks == {
        "name present": True,
        "name valid": True,
        "folder matches name": False,
        "description present": False,
        "trigger phrase": False,
    }


def test_check_frontmatter_requires_block(tmp_path):
    skill = tmp_path / "skills" / "axiomize"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("no frontmatter\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="no frontmatter"):
        check_skill.check_frontmatter(skill)


def test_check_links_ignores_external_and_accepts_existing(tmp_path):
    skill = _fake_skill(tmp_path, "x")
    (skill / "real.md").write_text("", encoding="utf-8")
    (skill / "docs").mkdir()
    doc = skill / "page.md"
    doc.write_text(
        "[a](https://example.com) [b](mailto:x@y.z) [c](#anchor) "
        "[d](real.md) [e](docs) [f](docs/) [g](tools/tool.py)\n",
        encoding="utf-8",
    )
    assert check_skill.check_links([doc]) == []


def test_check_links_reports_missing_and_directory_with_suffix(tmp_path):
    skill = _fake_skill(tmp_path, "x")
    (skill / "dir.py").mkdir()
    doc = skill / "page.md"
    doc.write_text("[a](missing.md) [b](dir.py) [c](missingdir)\n", encoding="utf-8")
    broken = check_skill.check_links([doc])
    assert (doc, "missing.md") in broken
    assert (doc, "dir.py") in broken
    assert (doc, "missingdir") in broken


def _run_linter(monkeypatch, capsys, module_file: Path):
    monkeypatch.setattr(check_skill, "__file__", str(module_file))
    code = check_skill.main()
    return code, capsys.readouterr().out


def test_linter_reports_success_for_a_valid_repo(tmp_path, monkeypatch, capsys):
    skill = _fake_skill(
        tmp_path,
        "---\nname: axiomize\ndescription: " + "d" * 60 + " Use when modeling\n---\n",
    )
    tool = skill / "tools" / "check_skill.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    code, out = _run_linter(monkeypatch, capsys, tool)
    assert code == 0
    assert "RESULT: PASS" in out
    assert "compiles / tool.py" in out


def test_linter_reports_frontmatter_link_and_compile_failures(tmp_path, monkeypatch, capsys):
    skill = _fake_skill(tmp_path, "---\nname: other\ndescription: short\n---\n[b](missing.md)\n")
    (skill / "tools" / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    sibling = tmp_path / "skills" / "outer.md"
    sibling.write_text("[c](also-missing.md)\n", encoding="utf-8")
    tool = skill / "tools" / "check_skill.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    code, out = _run_linter(monkeypatch, capsys, tool)
    assert code == 1
    assert "broken link:" in out
    assert "compiles / broken.py" in out
    assert "RESULT: FAIL" in out


def test_linter_reports_missing_frontmatter_block(tmp_path, monkeypatch, capsys):
    root = tmp_path / "skills" / "axiomize"
    root.mkdir(parents=True)
    (root / "SKILL.md").write_text("nothing\n", encoding="utf-8")
    (root / "tools").mkdir()
    tool = root / "tools" / "check_skill.py"
    tool.write_text("x = 1\n", encoding="utf-8")
    code, out = _run_linter(monkeypatch, capsys, tool)
    assert code == 1
    assert "frontmatter" in out and "FAIL" in out


# --------------------------------------------------------------------------- #
# validate: probability helpers and reports
# --------------------------------------------------------------------------- #

def test_fadeout_probability_boundaries():
    assert validate_tool._fadeout_probability(0.3, 0.1, 0) == 1.0
    assert validate_tool._fadeout_probability(0.0, 0.1, 5) == 1.0
    assert validate_tool._fadeout_probability(0.0, 0.0, 5) == 1.0
    assert validate_tool._fadeout_probability(0.1, 0.1, 5) == pytest.approx(1.0 / 6.0)
    assert 0.0 < validate_tool._fadeout_probability(0.1, 0.3, 5) < 1.0
    assert 0.0 < validate_tool._fadeout_probability(0.3, 0.1, 5) <= 1.0


def test_erlang_c_staffing_boundaries():
    assert validate_tool.erlang_c(0.0, 10.0, 3) == (0.0, 0.0)
    p_wait, wait = validate_tool.erlang_c(30.0, 10.0, 3)
    assert p_wait == 1.0
    assert wait == float("inf")
    p_wait, wait = validate_tool.erlang_c(10.0, 10.0, 4)
    assert 0.0 < p_wait < 1.0
    assert wait > 0


def _sir_args(**overrides):
    values = dict(beta=0.3, gamma=0.1, I0=10, N=1000, days=60, sweep=False, plot=None)
    values.update(overrides)
    return SimpleNamespace(**values)


def test_report_sir_runs_checks_and_sweep(capsys):
    code = validate_tool.report_sir(_sir_args(sweep=True))
    out = capsys.readouterr().out
    assert code in {0, 1}
    assert "=== SIR validation ===" in out
    assert "sensitivity sweep over beta" in out


def test_report_sir_subcritical_theory_match(capsys):
    code = validate_tool.report_sir(_sir_args(beta=0.05, gamma=0.1, I0=1, N=1000))
    out = capsys.readouterr().out
    assert "dies out" in out
    assert code in {0, 1}


def test_report_sir_plot_skips_without_matplotlib(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    code = validate_tool.report_sir(_sir_args(plot=str("unused.png")))
    assert "plot skipped: matplotlib not installed" in capsys.readouterr().out
    assert code in {0, 1}


def test_report_sir_writes_plot(tmp_path, capsys):
    target = tmp_path / "sir.png"
    code = validate_tool.report_sir(_sir_args(plot=str(target)))
    assert target.is_file()
    assert "plot saved" in capsys.readouterr().out
    assert code in {0, 1}


def test_report_gillespie_full_and_sweep(capsys):
    args = SimpleNamespace(beta=0.4, gamma=0.2, I0=3, N=200, days=40, runs=20, seed=7, sweep=True)
    code = validate_tool.report_gillespie(args)
    out = capsys.readouterr().out
    assert code in {0, 1}
    assert "Gillespie stochastic SIR" in out
    assert "sensitivity sweep over I0" in out


def test_report_gillespie_rejects_excess_work(monkeypatch):
    args = SimpleNamespace(beta=0.4, gamma=0.2, I0=3, N=200_000, days=40, runs=20, seed=7, sweep=True)
    monkeypatch.setattr(validate_tool, "MAX_GILLESPIE_WORK", 1)
    with pytest.raises(ValueError, match="exceed hard stochastic work limit"):
        validate_tool.report_gillespie(args)


def test_report_gillespie_without_major_outbreaks(capsys):
    args = SimpleNamespace(beta=0.0, gamma=1.0, I0=2, N=100, days=10, runs=3, seed=1, sweep=False)
    code = validate_tool.report_gillespie(args)
    assert code in {0, 1}
    assert "Gillespie stochastic SIR" in capsys.readouterr().out


def test_report_queue_finds_minimal_staffing(capsys):
    args = SimpleNamespace(lam=10.0, mu=5.0, target_wait=60.0, sweep=True)
    code = validate_tool.report_queue(args)
    out = capsys.readouterr().out
    assert code == 0
    assert "minimal staffing c*" in out
    assert "sensitivity sweep over mu" in out
    assert "staffing cliff" in out


def test_report_queue_reports_no_feasible_level(capsys):
    args = SimpleNamespace(lam=100.0, mu=1.0, target_wait=0.0, sweep=False)
    code = validate_tool.report_queue(args)
    out = capsys.readouterr().out
    assert code == 1
    assert "No staffing level meets the target" in out


def test_report_queue_rejects_impossible_parameters():
    with pytest.raises(ValueError, match="lambda >= 0"):
        validate_tool.report_queue(SimpleNamespace(lam=-1.0, mu=1.0, target_wait=1.0, sweep=False))
    with pytest.raises(ValueError, match="baseline staff exceeds hard limit"):
        validate_tool.report_queue(SimpleNamespace(lam=1e9, mu=1.0, target_wait=1.0, sweep=False))


def test_validate_cli_dispatches_and_converts_errors(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["axiomize-validate", "--model", "queue",
                                      "--lam", "10", "--mu", "5", "--target-wait", "60"])
    with pytest.raises(SystemExit) as excinfo:
        validate_tool.main()
    assert excinfo.value.code == 0
    assert "M/M/c queue staffing" in capsys.readouterr().out


def test_validate_cli_rejects_invalid_model_arguments(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["axiomize-validate", "--model", "gillespie",
                                      "--I0", "-1"])
    with pytest.raises(SystemExit) as excinfo:
        validate_tool.main()
    assert excinfo.value.code == 2
    assert "must be" in capsys.readouterr().err


def test_validate_cli_queue_returns_failure_code(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["axiomize-validate", "--model", "queue",
                                      "--lam", "100", "--mu", "1", "--target-wait", "0"])
    with pytest.raises(SystemExit) as excinfo:
        validate_tool.main()
    assert excinfo.value.code == 1


# --------------------------------------------------------------------------- #
# Remaining branches: tokenised alternatives, default path, link resolution
# --------------------------------------------------------------------------- #

def test_alt_tokens_present_requires_every_nonstopword_token():
    assert benchmark_runner._alt_tokens_present("the SIR model", "sir model works") is True
    assert benchmark_runner._alt_tokens_present("the SIR model", "sir works") is False


def test_default_benchmark_path_returns_empty_when_no_candidate_exists(tmp_path, monkeypatch):
    fake_here = tmp_path / "nested" / "pkg" / "benchmark_runner.py"
    fake_here.parent.mkdir(parents=True)
    monkeypatch.setattr(benchmark_runner, "__file__", str(fake_here))
    monkeypatch.chdir(tmp_path)
    assert benchmark_runner._default_benchmark_path() == ""


def test_check_links_accepts_existing_targets(tmp_path):
    skill = tmp_path / "skills" / "axiomize"
    skill.mkdir(parents=True)
    (skill / "existing.md").write_text("ok\n", encoding="utf-8")
    page = skill / "SKILL.md"
    page.write_text("[a](existing.md)\n", encoding="utf-8")
    assert check_skill.check_links([page]) == []


# --------------------------------------------------------------------------- #
# Remaining validate.py defensive branches
# --------------------------------------------------------------------------- #

def test_final_size_theory_rejects_invalid_rates():
    with pytest.raises(ValueError, match="requires beta >= 0 and gamma > 0"):
        validate_tool.final_size_theory(-0.1, 0.1)
    with pytest.raises(ValueError, match="requires beta >= 0 and gamma > 0"):
        validate_tool.final_size_theory(0.1, 0.0)


def test_gillespie_once_enforces_event_bound(monkeypatch):
    monkeypatch.setattr(validate_tool, "_validate_sir",
                        lambda *args, **kwargs: (0.3, 0.1, 1, 0, 180.0))
    with pytest.raises(RuntimeError, match="event bound exceeded"):
        validate_tool.gillespie_sir_once(0.3, 0.1, 1, 0, rng=object())


def test_gillespie_once_stops_when_no_transition_rate(monkeypatch):
    monkeypatch.setattr(validate_tool, "_validate_sir",
                        lambda *args, **kwargs: (0.0, 0.0, 1, 1, 180.0))
    result = validate_tool.gillespie_sir_once(0.0, 0.0, 1, 1, rng=object())
    assert result["events"] == 0
    assert result["extinct_early"] is True
    assert result["final_R"] == 1


def test_report_gillespie_skips_true_outbreak_branch(capsys):
    args = SimpleNamespace(beta=0.101, gamma=0.1, I0=1, N=1000, days=180,
                           runs=60, seed=4, sweep=False)
    code = validate_tool.report_gillespie(args)
    out = capsys.readouterr().out
    assert "non-fade-out runs" in out
    assert "of which true outbreaks (>10% infected): 0" in out
    assert "true-outbreak final size" not in out
    assert code in {0, 1}


def test_report_queue_sweep_can_exhaust_staffing_bound(capsys, monkeypatch):
    monkeypatch.setattr(validate_tool, "MAX_QUEUE_STAFF", 3)
    args = SimpleNamespace(lam=2.0, mu=10.0, target_wait=0.01, sweep=True)
    code = validate_tool.report_queue(args)
    out = capsys.readouterr().out
    assert "minimal staffing c* = 3" in out
    assert "sensitivity sweep over mu" in out
    assert code == 0


def test_report_queue_returns_failure_when_search_bound_is_empty(capsys, monkeypatch):
    # Force the search window to a degenerate empty range while keeping the
    # hard-limit check satisfied, exercising the defensive empty-rows return.
    import builtins

    monkeypatch.setattr(validate_tool, "MAX_QUEUE_STAFF", 1)
    real_min = builtins.min
    monkeypatch.setattr(builtins, "min", lambda *a, **k: 0)
    try:
        code = validate_tool.report_queue(
            SimpleNamespace(lam=1.0, mu=1.0, target_wait=1.0, sweep=False))
    finally:
        monkeypatch.setattr(builtins, "min", real_min)
    assert code == 1
    assert "=== M/M/c queue staffing" in capsys.readouterr().out
