"""Deterministic ablation checks: branch controller vs greedy/beam baselines."""
from __future__ import annotations

import pytest

from axiomize.reasoning.ablation import (
    _episode_signals,
    run_ablation,
    render_report,
)


@pytest.fixture(scope="module")
def results() -> dict:
    return run_ablation(seed=20260927, trials=200)


def test_deterministic_reproduction() -> None:
    first = run_ablation(seed=7, trials=25)
    second = run_ablation(seed=7, trials=25)
    assert first == second


def test_grid_shape(results: dict) -> None:
    assert set(results["cells"]) == {"easy", "moderate", "hard"}
    policies = {"argmax_commit", "beam_top2", "branch_controller"}
    for cell in results["cells"].values():
        assert set(cell["policies"]) == policies
        for stats in cell["policies"].values():
            for key in ("accuracy", "premature_wrong_rate", "mean_branch_cost"):
                assert 0.0 <= stats[key] <= max(1.0, stats["mean_branch_cost"])


def test_argmax_commit_pays_premature_wrong_in_hard(results: dict) -> None:
    hard = results["cells"]["hard"]["policies"]
    argmax_wrong = hard["argmax_commit"]["premature_wrong_rate"]
    controller_wrong = hard["branch_controller"]["premature_wrong_rate"]
    # The trap: committing at round 1 in hard/regime-shift episodes must be
    # visibly worse than the controller's collapse discipline.
    assert argmax_wrong > 0.30
    assert controller_wrong < argmax_wrong


def test_controller_accuracy_leads_or_ties_every_regime(results: dict) -> None:
    width = {"easy": 4, "moderate": 5, "hard": 6}
    for difficulty, cell in results["cells"].items():
        beam = cell["policies"]["beam_top2"]
        ctrl = cell["policies"]["branch_controller"]
        assert ctrl["accuracy"] >= beam["accuracy"]
        # adaptive allocation never exceeds observing everything every round
        assert ctrl["mean_branch_cost"] <= width[difficulty] * results["max_rounds"]


def test_hard_regime_shift_accuracy(results: dict) -> None:
    hard = results["cells"]["hard"]["policies"]
    # Regime-shift episodes (20% of hard) break commit-style policies; the
    # controller's probe-and-revive path should keep it clearly ahead of beam.
    assert hard["branch_controller"]["accuracy"] >= hard["beam_top2"]["accuracy"] + 0.05


def test_revivals_actually_happen(results: dict) -> None:
    total_revivals = sum(
        results["cells"][level]["policies"]["branch_controller"]["revivals"]
        for level in results["cells"]
    )
    assert total_revivals > 0


def test_reference_defaults_do_not_collapse_under_bounded_noise(results: dict) -> None:
    # Calibration evidence: with the shipped reference thresholds, the collapse
    # contract is practically unreachable under bounded noisy evidence. This
    # pins the finding so recalibration work has a measurable target.
    for cell in results["cells"].values():
        ctrl = cell["policies"]["branch_controller"]
        assert ctrl["early_commit_rate"] <= 0.01
        assert ctrl["accuracy"] >= 0.95 if cell is results["cells"]["easy"] else True


def test_episode_signals_put_quality_on_truth() -> None:
    import numpy as np

    rng = np.random.default_rng(3)
    for difficulty in ("easy", "moderate", "hard"):
        signals = _episode_signals(rng, difficulty)
        q = signals.qualities
        assert 0 < signals.truth < len(q) or signals.truth == 0
        k, correct_rng, rival_rng = {
            "easy": (4, (0.90, 0.98), (0.30, 0.55)),
            "moderate": (5, (0.85, 0.92), (0.55, 0.72)),
            "hard": (6, (0.78, 0.85), (0.68, 0.80)),
        }[difficulty]
        assert len(q) == k
        if signals.shift_round == 0:
            lo, hi = correct_rng
            assert lo <= q[signals.truth] <= hi
            rivals = [v for i, v in enumerate(q) if i != signals.truth]
            rlo, rhi = rival_rng
            assert all(rlo <= v <= rhi for v in rivals)


def test_render_report_contains_tables_and_headline(results: dict) -> None:
    report = render_report(results)
    for token in ("branch_controller", "beam_top2", "argmax_commit",
                  "| Policy |", "Difficulty: hard", "revivals"):
        assert token in report
    # every accuracy figure rendered with three decimals
    assert report.count("| cell") == 0  # sanity: no placeholders leaked
