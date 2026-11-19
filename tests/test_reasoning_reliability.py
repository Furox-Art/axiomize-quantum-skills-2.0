"""Synthetic reliability diagnostic: binning math, episode paths, labelling.

The diagnostic is explicitly synthetic (no LLM, known ground truth). These
tests pin both the statistics and the honesty labelling, plus every branch of
the episode runner so the 100% branch-coverage gate holds.
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest

from axiomize.reasoning import reliability
from axiomize.reasoning.ablation import _episode_signals
from axiomize.reasoning.branch_controller import DEFAULT_THRESHOLDS
from axiomize.reasoning.reliability import (
    DISCLAIMER,
    SYNTHETIC_LABEL,
    ReliabilityBin,
    brier_score,
    expected_calibration_error,
    maximum_calibration_error,
    reliability_bins,
    render_report,
    run_synthetic_reliability,
    summarize_reliability,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def result() -> dict:
    return run_synthetic_reliability(seed=20261119, trials=80)


# --------------------------------------------------------------------------- #
# Binning and error statistics (hand-computed references)
# --------------------------------------------------------------------------- #

def test_bins_hand_computed_two_bin_example() -> None:
    bins = reliability_bins([0.05, 0.15, 0.95], [False, True, True], n_bins=2)
    assert bins[0] == ReliabilityBin(0.0, 0.5, 2, 0.10, 0.5)
    assert bins[1].count == 1
    assert bins[1].mean_score == pytest.approx(0.95)
    assert bins[1].accuracy == 1.0
    assert expected_calibration_error(bins) == pytest.approx((2 * 0.4 + 0.05) / 3)
    assert maximum_calibration_error(bins) == pytest.approx(0.4)
    assert brier_score([0.05, 0.15, 0.95], [False, True, True]) == pytest.approx(0.2425)


def test_score_one_lands_in_last_bin_and_zero_in_first() -> None:
    bins = reliability_bins([0.0, 1.0], [False, True], n_bins=4)
    assert bins[0].count == 1
    assert bins[-1].count == 1
    assert bins[1].count == 0 and bins[2].count == 0
    # empty bins carry None, not a misleading 0.0 accuracy
    assert bins[1].mean_score is None and bins[1].accuracy is None


def test_bin_boundary_score_goes_to_upper_bin() -> None:
    bins = reliability_bins([0.5], [True], n_bins=2)
    assert bins[0].count == 0
    assert bins[1].count == 1


def test_perfect_and_overconfident_pools() -> None:
    perfect = summarize_reliability([0.0, 1.0], [False, True], n_bins=2)
    assert perfect["ece"] == 0.0
    assert perfect["mce"] == 0.0
    assert perfect["brier"] == 0.0
    over = summarize_reliability([0.9, 0.9], [False, False], n_bins=2)
    assert over["ece"] == pytest.approx(0.9)
    assert over["mce"] == pytest.approx(0.9)
    assert over["accuracy"] == 0.0
    assert over["mean_score"] == pytest.approx(0.9)


def test_empty_bin_list_errors_are_zero() -> None:
    empty = [ReliabilityBin(0.0, 1.0, 0, None, None)]
    assert expected_calibration_error(empty) == 0.0
    assert maximum_calibration_error(empty) == 0.0


def test_single_bin_collapses_to_absolute_gap() -> None:
    bins = reliability_bins([0.8, 0.8], [True, False], n_bins=1)
    assert len(bins) == 1
    assert expected_calibration_error(bins) == pytest.approx(0.3)
    assert maximum_calibration_error(bins) == pytest.approx(0.3)


@pytest.mark.parametrize(
    ("scores", "outcomes", "n_bins", "exc"),
    [
        ([0.5], [True], 0, ValueError),
        ([0.5], [], 10, ValueError),
        ([], [], 10, ValueError),
        ([-0.1], [True], 10, ValueError),
        ([1.1], [True], 10, ValueError),
        ([float("nan")], [True], 10, ValueError),
        ([float("inf")], [True], 10, ValueError),
        ([0.5], [1], 10, TypeError),
        ([0.5], [np.bool_(True)], 10, TypeError),
    ],
)
def test_bins_fail_closed_on_malformed_input(scores, outcomes, n_bins, exc) -> None:
    with pytest.raises(exc):
        reliability_bins(scores, outcomes, n_bins=n_bins)


def test_brier_fail_closed() -> None:
    with pytest.raises(ValueError, match="same length"):
        brier_score([0.5], [])
    with pytest.raises(ValueError, match="at least one"):
        brier_score([], [])


# --------------------------------------------------------------------------- #
# Synthetic episode runner: determinism, labels, forced branch paths
# --------------------------------------------------------------------------- #

def test_deterministic_reproduction() -> None:
    first = run_synthetic_reliability(seed=7, trials=15)
    second = run_synthetic_reliability(seed=7, trials=15)
    assert first == second


def test_payload_is_explicitly_synthetic(result: dict) -> None:
    assert result["label"] == SYNTHETIC_LABEL
    assert result["synthetic"] is True
    assert result["llm_calls"] == 0
    assert "NOT calibration evidence on real tasks" in result["disclaimer"]
    assert result["disclaimer"] == DISCLAIMER
    assert set(result["cells"]) == {"easy", "moderate", "hard"}
    for cell in result["cells"].values():
        assert cell["n"] == 80
        assert 0.0 <= cell["ece"] <= 1.0
        assert 0.0 <= cell["mce"] <= 1.0
        assert 0.0 <= cell["brier"] <= 1.0
        assert sum(b["count"] for b in cell["bins"]) == 80


def test_single_difficulty_selection() -> None:
    single = run_synthetic_reliability(seed=3, trials=10, difficulty="hard")
    assert set(single["cells"]) == {"hard"}


def test_run_fail_closed() -> None:
    with pytest.raises(ValueError, match="trials"):
        run_synthetic_reliability(trials=0)
    with pytest.raises(ValueError, match="unknown difficulty"):
        run_synthetic_reliability(difficulty="impossible")


def test_episode_collapse_path_records_leader_score() -> None:
    # Easy regime + calibrated default collapses early: confidence must be the
    # leader's support score (>= collapse threshold), not a placeholder.
    rng = np.random.default_rng(5)
    collapsed = 0
    for _ in range(30):
        signals = _episode_signals(rng, "easy")
        confidence, correct = reliability._controller_episode(rng, signals)
        assert 0.0 <= confidence <= 1.0
        assert isinstance(correct, bool)
        if confidence >= DEFAULT_THRESHOLDS.collapse_score:
            collapsed += 1
    assert collapsed > 0


def test_episode_deadline_path_when_collapse_is_unreachable() -> None:
    rng = np.random.default_rng(9)
    thresholds = replace(DEFAULT_THRESHOLDS, collapse_score=2.0)
    for _ in range(5):
        signals = _episode_signals(rng, "hard")
        confidence, correct = reliability._controller_episode(rng, signals, thresholds)
        assert 0.0 <= confidence <= 1.0
        assert isinstance(correct, bool)


def test_episode_all_rejected_fallback_path() -> None:
    # reject_contradiction=0.0 rejects every branch (leader contradiction is
    # exactly 0.0 and the gate is >=): exercises the empty-ranked fallback.
    rng = np.random.default_rng(11)
    thresholds = replace(DEFAULT_THRESHOLDS, reject_contradiction=0.0)
    signals = _episode_signals(rng, "hard")
    confidence, correct = reliability._controller_episode(rng, signals, thresholds)
    assert 0.0 <= confidence <= 1.0
    assert isinstance(correct, bool)


def test_episode_dormancy_and_probe_paths() -> None:
    # dormant_score above any reachable score forces every branch dormant, so
    # the every-third-round probe and revival paths run on every episode.
    rng = np.random.default_rng(13)
    thresholds = replace(DEFAULT_THRESHOLDS, dormant_score=1.01)
    for _ in range(4):
        signals = _episode_signals(rng, "moderate")
        confidence, _ = reliability._controller_episode(rng, signals, thresholds)
        assert 0.0 <= confidence <= 1.0


def test_hard_regime_accuracy_stays_honest(result: dict) -> None:
    # The synthetic hard regime is hard: the diagnostic must not quietly
    # present a solved environment. The ablation pins 0.388 at 400 trials;
    # at 80 trials the same generator stays far below the easy regime.
    assert result["cells"]["hard"]["accuracy"] < result["cells"]["easy"]["accuracy"]
    assert result["cells"]["hard"]["accuracy"] < 0.7


# --------------------------------------------------------------------------- #
# Report rendering and CLI
# --------------------------------------------------------------------------- #

def test_report_carries_the_synthetic_label_and_pending_protocol(result: dict) -> None:
    report = render_report(result)
    for token in (
        "SYNTHETIC",
        "NOT calibration evidence on real tasks",
        SYNTHETIC_LABEL,
        "Difficulty: hard",
        "| Score bin |",
        "Pending real-task protocol (not executed)",
        "Status: PENDING",
        "0.388",
        "2.4x",
    ):
        assert token in report
    # empty bins render as '-', never as a fabricated 0.000 accuracy
    assert "| 0 | - | - | - |" in report


def test_main_writes_report_and_json(tmp_path: Path, capsys) -> None:
    report = tmp_path / "rel.md"
    payload = tmp_path / "rel.json"
    code = reliability.main(
        ["--seed", "3", "--trials", "8", "--difficulty", "easy",
         "--report-out", str(report), "--json-out", str(payload)]
    )
    assert code == 0
    assert "SYNTHETIC" in report.read_text(encoding="utf-8")
    data = json.loads(payload.read_text(encoding="utf-8"))
    assert data["synthetic"] is True
    assert data["llm_calls"] == 0
    assert set(data["cells"]) == {"easy"}
    assert "synthetic reliability report written" in capsys.readouterr().out


def test_main_default_report_destination(tmp_path: Path, monkeypatch, capsys) -> None:
    here = tmp_path / "a" / "b" / "c" / "d" / "reliability.py"
    here.parent.mkdir(parents=True)
    monkeypatch.setattr(reliability, "__file__", str(here))
    monkeypatch.setattr(
        reliability, "run_synthetic_reliability",
        lambda seed, trials, difficulty: {"seed": seed, "cells": {}},
    )
    monkeypatch.setattr(reliability, "render_report", lambda result: "# default\n")
    monkeypatch.setattr(sys, "argv", ["reliability", "--trials", "1"])
    assert reliability.main() == 0
    expected = tmp_path / "a" / "benchmarks" / "reports" / "reasoning-reliability.md"
    assert expected.read_text(encoding="utf-8") == "# default\n"
    assert "synthetic reliability report written" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# README honesty pins (the limitation text must not silently disappear)
# --------------------------------------------------------------------------- #

def test_readme_documents_synthetic_limit_and_pending_protocol() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    for token in (
        "synthetic",
        "0.388",
        "2.4",
        "real-task",
        "PENDING",
        "reasoning-reliability.md",
    ):
        assert token in readme, f"README must keep the reasoning-evidence honesty text: {token!r}"


def test_committed_report_is_a_labelled_snapshot() -> None:
    # Structural pin, not byte-equality: the ablation history shows seeded
    # numpy draws can differ across platforms/versions, so the committed
    # snapshot is provenance-stamped (seed/trials inside) rather than pinned
    # byte-for-byte against a local regeneration.
    committed = (
        REPO_ROOT / "benchmarks" / "reports" / "reasoning-reliability.md"
    ).read_text(encoding="utf-8")
    for token in (
        "SYNTHETIC",
        "NOT calibration evidence on real tasks",
        SYNTHETIC_LABEL,
        "Seed 20261119",
        "300 episodes per difficulty",
        "Difficulty: easy",
        "Difficulty: moderate",
        "Difficulty: hard",
        "Pending real-task protocol (not executed)",
        "Status: PENDING",
    ):
        assert token in committed
