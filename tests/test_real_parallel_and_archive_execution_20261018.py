"""Execute real multithread-safe worker routines and auditable report indexing.

Tests exercise distributed script modules actually bundled with the wheel.
No coverage exemptions, fabricated input datasets or ignored subprocess errors.
"""
from __future__ import annotations

import sys

import pytest

from axiomize.tools import index_reports, parallel_sweep


@pytest.mark.parametrize("bad", [True, False, None, "invalid", -1, 0, 33, 2.5])
def test_worker_limit_refuses_unbounded_or_fractional_allocations(bad):
    with pytest.raises(ValueError, match="workers"):
        parallel_sweep._bounded_workers(bad)


@pytest.mark.parametrize("bad", [True, False, None, "not integer", -1, 0, 100001, 2.25])
def test_monte_carlo_limit_refuses_unbounded_or_fractional_allocations(bad):
    with pytest.raises(ValueError, match="total_runs"):
        parallel_sweep._bounded_runs(bad)


@pytest.mark.parametrize("workers,expected", [(1, 1), (4, 4), ("2", 2), (2.0, 2)])
def test_worker_validation_preserves_valid_integer_values(workers, expected):
    assert parallel_sweep._bounded_workers(workers) == expected


@pytest.mark.parametrize("runs,expected", [(1, 1), (100000, 100000), ("19", 19)])
def test_monte_carlo_validation_preserves_valid_integer_values(runs, expected):
    assert parallel_sweep._bounded_runs(runs) == expected


def test_actual_sir_ode_final_size_is_physical_and_monotonic_in_beta():
    low = parallel_sweep.sir_final_size((0.1, 0.1, 10, 1000))
    high = parallel_sweep.sir_final_size((0.5, 0.1, 10, 1000))
    assert low[:2] == (0.1, 0.1)
    assert high[:2] == (0.5, 0.1)
    assert 0 <= low[2] < high[2] <= 1


def test_actual_stochastic_chunk_is_reproducible_with_frozen_seed():
    args = (0.3, 0.1, 1, 5000, 20, 1001)
    first = parallel_sweep.gillespie_chunk(args)
    second = parallel_sweep.gillespie_chunk(args)
    assert first == second
    assert isinstance(first, int)
    assert 0 <= first <= 20



def test_zero_rate_stochastic_process_does_not_divide_by_zero():
    # With beta=gamma=0 the competing-hazard clock has no events.
    # The simulator must stop cleanly instead of sampling Exp(1/0).
    assert parallel_sweep.gillespie_chunk((0.0, 0.0, 1, 5000, 4, 1001)) == 4


def test_real_multiprocess_grid_matches_analytical_final_size(capsys):
    result = parallel_sweep.job_sweep(workers=1)
    output = capsys.readouterr().out
    assert result == 0
    assert "28 independent ODE tasks" in output
    assert "sanity check: center cell" in output
    assert "-> PASS" in output


def test_real_multiprocess_gillespie_agrees_with_analytic_probability(capsys):
    result = parallel_sweep.job_mc(workers=1, total_runs=160)
    output = capsys.readouterr().out
    assert result == 0
    assert "160 CTMC runs" in output
    assert "sanity check -> PASS" in output
    assert "observed" in output


def test_direct_parallel_tool_cli_dispatches_real_monte_carlo(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["axiomize-parallel", "--job", "mc", "--workers", "1"])
    with pytest.raises(SystemExit) as exc:
        parallel_sweep.main()
    assert exc.value.code == 0
    assert "400 CTMC runs" in capsys.readouterr().out


def test_parallel_tool_cli_rejects_bad_requested_workers(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["axiomize-parallel", "--job", "mc", "--workers", "0"])
    with pytest.raises(SystemExit) as exc:
        parallel_sweep.main()
    assert exc.value.code == 2


def test_missing_reports_directory_does_not_fabricate_archive(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert index_reports.main() == 0
    assert "nothing to index" in capsys.readouterr().out
    assert not (tmp_path / "reports").exists()


def test_indexer_creates_empty_but_explicit_archive(tmp_path, monkeypatch):
    (tmp_path / "reports").mkdir()
    monkeypatch.chdir(tmp_path)
    assert index_reports.main() == 0
    index = (tmp_path / "reports" / "INDEX.md").read_text(encoding="utf-8")
    assert "0 session(s)" in index
    assert "Modeling Session Index" in index


def test_real_report_index_keeps_dates_and_escapes_pipe_in_table(tmp_path, monkeypatch):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "a.md").write_text(
        "# Model Report: Model A\n**Date:** 2026-01-10\n"
        "**Rigor level:** formal\n**Model in one sentence:** Population | observations\n",
        encoding="utf-8",
    )
    (reports / "b.md").write_text(
        "# Model Report: Model B\n**Date:** 2026-02-10\n"
        "**Rigor level:** empirical\n**Model in one sentence:** Measured curve\n",
        encoding="utf-8",
    )
    (reports / "c.md").write_text("Unlabeled but legitimate note\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert index_reports.main() == 0
    first = (reports / "INDEX.md").read_text(encoding="utf-8")
    assert "3 session(s)" in first
    assert "Population / observations" in first
    assert first.index("Model B") < first.index("Model A")
    assert "[c](c.md)" in first
    assert index_reports.main() == 0
    assert (reports / "INDEX.md").read_text(encoding="utf-8") == first


def test_report_parser_does_not_make_up_missing_metadata(tmp_path):
    path = tmp_path / "real-report.md"
    path.write_text("No recognized report fields", encoding="utf-8")
    result = index_reports.parse_report(path)
    assert result == {"file": "real-report.md", "title": "real-report", "date": "", "rigor": "", "model": ""}
