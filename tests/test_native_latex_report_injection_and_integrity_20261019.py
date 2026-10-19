"""Real report-to-LaTeX conversion and hostile macro safety contracts."""
from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace

import pytest

from axiomize.tools import report_to_latex as tex


@pytest.mark.parametrize("source,expected", [
    ("&", r"\&"), ("%", r"\%"), ("#", r"\#"),
    ("_", r"\_"), ("$", r"\$"), ("{", r"\{"),
    ("}", r"\}"), ("\\", r"\textbackslash{}"),
    ("α", r"$\alpha$"), ("β", r"$\beta$"),
])
def test_text_is_escaped_before_becoming_latex(source, expected):
    assert tex.esc_map(source, set()) == expected


@pytest.mark.parametrize("macro", [
    r"\input", r"\include", r"\write", r"\def",
    r"\catcode", r"\usepackage", r"\documentclass", r"\csname",
])
def test_structural_tex_commands_cannot_execute_from_user_math(macro):
    dropped = set()
    out = tex.safe_math(macro + "{outside}", dropped)
    assert "[blocked-" in out
    assert macro not in out
    assert dropped


@pytest.mark.parametrize("macro", [
    r"\alpha", r"\frac", r"\sum", r"\sqrt", r"\mathbb",
])
def test_approved_math_macros_remain_mathematically_legible(macro):
    dropped = set()
    assert macro in tex.safe_math(macro + "{x}", dropped)
    assert not dropped


def test_unknown_macro_is_neutralized_even_when_not_on_deny_list():
    dropped = set()
    result = tex.safe_math(r"\customExploit{x}", dropped)
    assert r"\customExploit" not in result
    assert "[blocked-customExploit]" in result
    assert dropped


def test_inline_math_bold_and_code_preserve_semantics():
    raw = "**evidence** `hash` $x^2+1$"
    result = tex.inline(raw, set())
    assert r"\textbf{evidence}" in result
    assert r"\texttt{hash}" in result
    assert "$x^2+1$" in result


def test_currency_is_not_mistaken_for_mathematical_delimiters():
    result = tex.inline("$5 cost and $2 fee", set())
    assert r"\$5 cost" in result


def test_table_separator_row_cannot_be_fabricated_into_data():
    result = "\n".join(tex.flush_table([
        ["Model", "Residual"], ["---", "---"], ["A", "0.01"]
    ], set()))
    assert r"\begin{tabular}{ll}" in result
    assert "A & 0.01" in result
    assert "---" not in result
    assert tex.flush_table([], set()) == []


def test_actual_scientific_markdown_preserves_all_structural_sections():
    raw = (
        "# Evidence\n## Physical Constraints\n### Model Diagnostics\n"
        "#### Replication\n- Point one\n  - Nested point\n1. First item\n"
        "| Model | Error |\n| --- | --- |\n| A | 0.01 |\n"
        "$$\n\\alpha+x^2\n$$\n---\n"
        "```python\nprint(42)\n```\n"
    )
    result = tex.convert(raw)
    for required in (
        r"\section*{Evidence}", r"\subsection*{Physical Constraints}",
        r"\subsubsection*{Model Diagnostics}", r"\paragraph*{Replication}",
        r"\begin{itemize}", r"\begin{enumerate}",
        r"\begin{tabular}", r"\begin{verbatim}",
        r"\end{document}", r"\[", r"\alpha",
    ):
        assert required in result


def test_mermaid_graph_code_is_comment_not_executable_tex():
    result = tex.convert("```mermaid\nA --> B\n```")
    assert "%A --> B" in result
    assert r"\begin{verbatim}" not in result


def test_unclosed_mathematics_are_explicitly_reported(capsys):
    result = tex.convert("$$\na+b")
    assert r"\[a+b\]" in result
    assert "unclosed" in capsys.readouterr().out


def test_blocked_math_macro_is_reported_and_neutralized(capsys):
    result = tex.convert("$$\n\\input{private}\n$$")
    assert "[blocked-input]" in result
    assert r"\input{private}" not in result
    assert "blocked" in capsys.readouterr().out


@pytest.mark.parametrize("bad", [None, [], {}, 42])
def test_nontext_markdown_is_rejected(bad):
    with pytest.raises(ValueError, match="markdown input must be text"):
        tex.convert(bad)


def test_input_size_budget_is_not_bypassed(monkeypatch):
    monkeypatch.setattr(tex, "MAX_MARKDOWN_BYTES", 3)
    with pytest.raises(ValueError, match="hard limit"):
        tex.convert("exceeds")


def test_real_cli_outputs_tex_without_pdf_dependency(tmp_path, monkeypatch):
    source = tmp_path / "model.md"
    target = tmp_path / "out" / "model.tex"
    source.write_text("# Evidence\nRecorded constraints", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(target)
    ])
    tex.main()
    result = target.read_text(encoding="utf-8")
    assert r"\section*{Evidence}" in result
    assert r"\end{document}" in result


def test_cli_requires_explicit_input_and_output(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["axiomize-latex"])
    with pytest.raises(SystemExit) as exc:
        tex.main()
    assert exc.value.code == 2


def test_pdf_compiler_never_uses_shell_escape(monkeypatch, tmp_path):
    source = tmp_path / "model.md"
    target = tmp_path / "model.tex"
    source.write_text("# Model", encoding="utf-8")
    commands = []

    def fake_run(arguments, **options):
        commands.append((arguments, options))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tex.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(target), "--pdf"
    ])
    tex.main()
    assert target.is_file()
    assert len(commands) == 3
    assert all(options["shell"] is False for _, options in commands)
    assert all("-no-shell-escape" in args for args, _ in commands[1:])


def test_missing_pdf_compiler_does_not_delete_generated_tex(monkeypatch, tmp_path):
    source = tmp_path / "model.md"
    target = tmp_path / "model.tex"
    source.write_text("# Model", encoding="utf-8")

    def refuse(*args, **kwargs):
        raise FileNotFoundError("pdflatex unavailable")

    monkeypatch.setattr(tex.subprocess, "run", refuse)
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(target), "--pdf"
    ])
    tex.main()
    assert target.is_file()


@pytest.mark.parametrize("source, expected", [
    ("χ", "$chi$"), ("Γ", "$Gamma$"),
    ("Ж", "Ж"), ("™", "TM"),
])
def test_nontransliterated_unicode_preserves_or_normalizes_real_character(source, expected):
    assert tex.esc_map(source, set()) == expected


def test_unknown_nonrepresentable_unicode_is_recorded_not_executed():
    dropped = set()
    assert tex.esc_map("🧪", dropped) == ""
    assert any("U+" in item for item in dropped)


def test_combining_marks_are_recorded_as_dropped_source():
    dropped = set()
    assert tex.esc_map("\u0301", dropped) == ""
    assert any("COMBINING" in item for item in dropped)


def test_unknown_unicode_in_math_is_recorded():
    dropped = set()
    assert tex.sanitize_math("🧪", dropped) == ""
    assert dropped


def test_unknown_greek_name_is_normalized_in_math():
    assert tex.sanitize_math("χ", set()) == "chi"
    assert tex.sanitize_math("Γ", set()) == "GAMMA"


def test_deny_list_defaults_to_a_new_set_and_never_exposes_input():
    assert "[blocked-input]" in tex.neutralize_dangerous_macros(r"\input{local}")
    assert r"\input" not in tex.neutralize_dangerous_macros(r"\input{local}")


def test_allow_list_defaults_to_a_new_set():
    result = tex.neutralize_math_macros(r"\arbitrary{danger}")
    assert "[blocked-arbitrary]" in result
    assert r"\arbitrary" not in result


def test_inline_double_dollar_expressions_use_display_environment():
    result = tex.inline("$$x+y$$", set())
    assert r"\[x+y\]" in result


def test_empty_math_unicode_keeps_unmodified_ascii_value():
    assert tex.sanitize_math("x+3", set()) == "x+3"


def test_report_main_file_size_checked_before_reading(monkeypatch, tmp_path):
    source = tmp_path / "too-large.md"
    output = tmp_path / "report.tex"
    source.write_text("Long document", encoding="utf-8")
    monkeypatch.setattr(tex, "MAX_MARKDOWN_BYTES", 2)
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(output)
    ])
    with pytest.raises(ValueError, match="hard limit"):
        tex.main()
    assert not output.exists()


def test_compile_failure_does_not_claim_pdf_success(monkeypatch, tmp_path, capsys):
    source = tmp_path / "test.md"
    output = tmp_path / "test.tex"
    source.write_text("# Real report", encoding="utf-8")
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=0 if len(calls) == 1 else 1)

    monkeypatch.setattr(tex.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(output), "--pdf"
    ])
    tex.main()
    assert output.is_file()
    assert len(calls) == 2
    assert "PDF compilation failed" in capsys.readouterr().out


def test_compile_timeout_is_reported_not_hidden(monkeypatch, tmp_path, capsys):
    source = tmp_path / "test.md"
    output = tmp_path / "test.tex"
    source.write_text("# Report", encoding="utf-8")
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        if len(calls) > 1:
            raise subprocess.TimeoutExpired(args, 1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tex.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(output), "--pdf"
    ])
    tex.main()
    assert output.is_file()
    assert "timed out" in capsys.readouterr().out


def test_present_pdf_is_only_announced_after_successful_compilation(monkeypatch, tmp_path, capsys):
    source = tmp_path / "test.md"
    output = tmp_path / "test.tex"
    source.write_text("# Valid", encoding="utf-8")
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        if len(calls) == 3:
            output.with_suffix(".pdf").write_bytes(b"%PDF-1.4\n% test artifact")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(tex.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(output), "--pdf"
    ])
    tex.main()
    assert output.with_suffix(".pdf").is_file()
    assert "PDF ready" in capsys.readouterr().out
    assert len(calls) == 3


def test_pdf_probe_timeout_leaves_tex_without_false_pdf_success(monkeypatch, tmp_path):
    source = tmp_path / "test.md"
    output = tmp_path / "test.tex"
    source.write_text("# Model", encoding="utf-8")

    def timeout(args, **kw):
        raise subprocess.TimeoutExpired(args, 1)

    monkeypatch.setattr(tex.subprocess, "run", timeout)
    monkeypatch.setattr(sys, "argv", [
        "axiomize-latex", "--input", str(source), "--output", str(output), "--pdf"
    ])
    tex.main()
    assert output.exists()
    assert not output.with_suffix(".pdf").exists()


@pytest.mark.parametrize("source,expected", [
    ("^", r"\textasciicircum{}"), ("~", r"\textasciitilde{}"),
])
def test_remaining_ascii_tex_metacharacters_are_escaped(source, expected):
    assert tex.esc_map(source, set()) == expected


def test_math_unicode_transliteration_from_known_symbols():
    dropped = set()
    assert r"\beta" in tex.sanitize_math("β", dropped)
    assert not dropped


def test_single_line_display_math_is_not_dropped():
    converted = tex.convert("$$x^2+y^2$$")
    assert r"\[x^2+y^2\]" in converted


def test_table_flushes_before_following_plain_prose():
    converted = tex.convert("| A | B |\n| --- | --- |\n| one | two |\nFollowing prose")
    assert r"\begin{tabular}" in converted
    assert converted.index(r"\end{tabular}") < converted.index("Following prose")


def test_explicit_blank_markdown_line_is_skipped_not_fabricated():
    converted = tex.convert("\n\n\n")
    assert r"\end{document}" in converted
    assert r"\section*" not in converted


def test_real_bundled_example_selftest_passes_all_template_structure(capsys):
    assert tex.selftest() == 0
    output = capsys.readouterr().out
    assert "converted epidemic-sir.md" in output
    assert "FAIL" not in output


def test_selftest_unavailable_example_is_explicitly_reported(monkeypatch, capsys):
    original_exists = tex.Path.exists

    def missing_example(path):
        if path.name == "epidemic-sir.md":
            return False
        return original_exists(path)

    monkeypatch.setattr(tex.Path, "exists", missing_example)
    assert tex.selftest() == 0
    assert "example not found" in capsys.readouterr().out


def test_selftest_does_not_fake_pass_when_mandatory_template_fragments_absent(monkeypatch, capsys):
    monkeypatch.setattr(tex, "convert", lambda text: "no LaTeX structures")
    assert tex.selftest() == 1
    assert "FAIL" in capsys.readouterr().out


def test_real_selftest_cli_requires_no_input_file(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["axiomize-latex", "--selftest"])
    with pytest.raises(SystemExit) as result:
        tex.main()
    assert result.value.code == 0
