"""Synthetic score-outcome reliability diagnostic for the branch controller.

WHAT THIS IS: a deterministic, offline diagnostic. It runs the same seeded
synthetic episodes as :mod:`axiomize.reasoning.ablation`, records the
controller's decision confidence (the leader's ``branch_score`` at collapse,
or the surviving argmax branch's score at the deadline) together with the
known ground-truth outcome, and reports reliability-diagram bins, expected and
maximum calibration error (ECE/MCE) and the Brier score.

WHAT THIS IS NOT: calibration evidence on real tasks. Every episode is
synthetic with a known answer; no LLM is called and no real task is solved.
A low ECE here only means score and outcome agree *inside this synthetic
environment*. It does not validate the controller for real agent workloads.
The real-task protocol (live LLM runs on real tasks, recorded transcripts,
independently graded outcomes, then this same binning applied to real
(confidence, outcome) pairs) is PENDING -- see the "Reasoning evidence"
section of README.md. It was not executed in the 1.2.7 audit because no LLM
API access was available; nothing here substitutes for it.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from axiomize.reasoning.ablation import (
    _DIFFICULTY,
    _EMA_ALPHA,
    _MAX_ROUNDS,
    _MIN_COLLAPSE_ROUND,
    _PROBE_PERIOD,
    _Signals,
    _episode_signals,
    _episode_tape,
    _metrics,
    _observe_tape,
)
from axiomize.reasoning.branch_controller import (
    DEFAULT_THRESHOLDS,
    Branch,
    BranchState,
    Thresholds,
    branch_score,
    collapse_decision,
    update_branch_state,
)

#: Machine-readable label carried by every result payload and report.
SYNTHETIC_LABEL = "synthetic-diagnostic"

#: The disclaimer every consumer of these numbers must see.
DISCLAIMER = (
    "SYNTHETIC episodes with known ground truth; no LLM calls. This is a "
    "score-outcome consistency diagnostic inside a synthetic environment, "
    "NOT calibration evidence on real tasks. Real-task validation is pending."
)


@dataclass(frozen=True)
class ReliabilityBin:
    """One reliability-diagram bin. ``mean_score``/``accuracy`` are None when empty."""

    lower: float
    upper: float
    count: int
    mean_score: float | None
    accuracy: float | None


def reliability_bins(
    scores: Sequence[float],
    outcomes: Sequence[bool],
    n_bins: int = 10,
) -> list[ReliabilityBin]:
    """Bin (confidence, outcome) pairs into ``n_bins`` equal-width score bins.

    Fail-closed on malformed input: empty data, mismatched lengths, scores
    outside [0, 1] (NaN/inf included), non-bool outcomes, or ``n_bins < 1``
    all raise instead of producing a silently misleading diagram.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    if len(scores) != len(outcomes):
        raise ValueError("scores and outcomes must have the same length")
    if not scores:
        raise ValueError("reliability needs at least one (score, outcome) pair")
    for value in scores:
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"scores must be in [0, 1], got {value!r}")
    for outcome in outcomes:
        if not isinstance(outcome, bool):
            raise TypeError(f"outcomes must be bool, got {type(outcome).__name__}")
    totals = [0] * n_bins
    score_sums = [0.0] * n_bins
    correct_sums = [0] * n_bins
    for value, outcome in zip(scores, outcomes):
        index = min(int(value * n_bins), n_bins - 1)
        totals[index] += 1
        score_sums[index] += value
        correct_sums[index] += int(outcome)
    bins: list[ReliabilityBin] = []
    for index in range(n_bins):
        count = totals[index]
        bins.append(
            ReliabilityBin(
                lower=index / n_bins,
                upper=(index + 1) / n_bins,
                count=count,
                mean_score=score_sums[index] / count if count else None,
                accuracy=correct_sums[index] / count if count else None,
            )
        )
    return bins


def expected_calibration_error(bins: Sequence[ReliabilityBin]) -> float:
    """Count-weighted mean |accuracy - mean_score| over non-empty bins."""
    total = sum(b.count for b in bins)
    if total == 0:
        return 0.0
    return sum(
        b.count * abs(b.accuracy - b.mean_score)
        for b in bins
        if b.count and b.accuracy is not None and b.mean_score is not None
    ) / total


def maximum_calibration_error(bins: Sequence[ReliabilityBin]) -> float:
    """Largest per-bin |accuracy - mean_score|; 0.0 when every bin is empty."""
    gaps = [
        abs(b.accuracy - b.mean_score)
        for b in bins
        if b.count and b.accuracy is not None and b.mean_score is not None
    ]
    return max(gaps, default=0.0)


def brier_score(scores: Sequence[float], outcomes: Sequence[bool]) -> float:
    """Mean squared error between confidence and the 0/1 outcome."""
    if len(scores) != len(outcomes):
        raise ValueError("scores and outcomes must have the same length")
    if not scores:
        raise ValueError("Brier score needs at least one (score, outcome) pair")
    return sum((value - float(outcome)) ** 2 for value, outcome in zip(scores, outcomes)) / len(
        scores
    )


def summarize_reliability(
    scores: Sequence[float],
    outcomes: Sequence[bool],
    n_bins: int = 10,
) -> dict:
    """Reliability summary for one pool of (confidence, outcome) pairs."""
    bins = reliability_bins(scores, outcomes, n_bins=n_bins)
    return {
        "n": len(scores),
        "accuracy": sum(outcomes) / len(scores),
        "mean_score": sum(scores) / len(scores),
        "ece": expected_calibration_error(bins),
        "mce": maximum_calibration_error(bins),
        "brier": brier_score(scores, outcomes),
        "bins": [asdict(b) for b in bins],
    }


def _controller_episode(
    rng: np.random.Generator,
    signals: _Signals,
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> tuple[float, bool]:
    """One synthetic episode; returns (decision confidence, correct).

    Mirrors the ablation's controller run (same observation model, dormancy
    probing and collapse discipline) but records the leader's support score at
    the decision point instead of only the outcome.
    """
    k = signals.qualities.size
    tape = _episode_tape(rng, k)
    evidence = np.zeros(k)
    n_obs = np.zeros(k, dtype=int)
    branches = [
        Branch(branch_id=f"h{i}", metrics=_metrics(0.0, 0, 0.0, _MAX_ROUNDS))
        for i in range(k)
    ]
    answer: int | None = None
    confidence = 0.0
    for round_no in range(1, _MAX_ROUNDS + 1):
        leader_evidence = float(np.max(evidence)) if n_obs.sum() else 0.0
        new_branches: list[Branch] = []
        for i, branch in enumerate(branches):
            observable = (
                branch.state is BranchState.ACTIVE
                or (branch.state is BranchState.DORMANT and round_no % _PROBE_PERIOD == 0)
            )
            if observable:
                obs = _observe_tape(signals, tape, i, round_no)
                evidence[i] = (1 - _EMA_ALPHA) * evidence[i] + _EMA_ALPHA * obs
                n_obs[i] += 1
            new_metrics = _metrics(
                evidence[i], int(n_obs[i]),
                max(leader_evidence, float(evidence[i])), _MAX_ROUNDS,
            )
            updated = Branch(
                branch_id=branch.branch_id,
                metrics=new_metrics,
                state=branch.state,
                previous_metrics=branch.metrics,
            )
            new_branches.append(update_branch_state(updated, thresholds))
        branches = new_branches
        if round_no >= _MIN_COLLAPSE_ROUND:
            can_collapse, _, leader = collapse_decision(branches, thresholds)
            if can_collapse and leader is not None:
                answer = int(leader.branch_id[1:])
                confidence = branch_score(leader.metrics)
                break
    if answer is None:
        ranked = [b for b in branches if b.state is not BranchState.REJECTED]
        if ranked:
            chosen = max(ranked, key=lambda b: evidence[int(b.branch_id[1:])])
        else:
            # Every branch rejected (only reachable with pathological
            # thresholds): fall back to the raw evidence argmax, as the
            # ablation does.
            chosen = branches[int(np.argmax(evidence))]
        answer = int(chosen.branch_id[1:])
        confidence = branch_score(chosen.metrics)
    return confidence, answer == signals.truth


def run_synthetic_reliability(
    seed: int = 20261119,
    trials: int = 300,
    difficulty: str = "all",
    thresholds: Thresholds = DEFAULT_THRESHOLDS,
) -> dict:
    """Run the synthetic reliability diagnostic and return a labelled payload."""
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if difficulty != "all" and difficulty not in _DIFFICULTY:
        raise ValueError(f"unknown difficulty {difficulty!r}; expected 'all' or {sorted(_DIFFICULTY)}")
    rng = np.random.default_rng(seed)
    levels = tuple(_DIFFICULTY) if difficulty == "all" else (difficulty,)
    cells: dict = {}
    for level in levels:
        scores: list[float] = []
        outcomes: list[bool] = []
        for _ in range(trials):
            signals = _episode_signals(rng, level)
            confidence, correct = _controller_episode(rng, signals, thresholds)
            scores.append(confidence)
            outcomes.append(correct)
        cells[level] = summarize_reliability(scores, outcomes)
    return {
        "label": SYNTHETIC_LABEL,
        "synthetic": True,
        "llm_calls": 0,
        "disclaimer": DISCLAIMER,
        "seed": seed,
        "trials_per_cell": trials,
        "collapse_score": thresholds.collapse_score,
        "cells": cells,
    }


def render_report(result: dict) -> str:
    """Markdown report; the synthetic disclaimer is part of the artifact itself."""
    lines = [
        "# Reasoning score-outcome reliability (SYNTHETIC diagnostic)",
        "",
        f"> **{result['disclaimer']}**",
        "",
        f"Label: `{result['label']}`. Seed {result['seed']}, "
        f"{result['trials_per_cell']} episodes per difficulty, "
        f"collapse_score {result['collapse_score']:.2f}, LLM calls: {result['llm_calls']}.",
        "",
        "Confidence is the leader's `branch_score` at collapse, or the surviving",
        "argmax branch's score at the deadline. Bins are equal-width in score.",
        "",
    ]
    for level, cell in result["cells"].items():
        lines += [
            f"## Difficulty: {level}",
            "",
            f"n={cell['n']}, accuracy={cell['accuracy']:.3f}, "
            f"mean score={cell['mean_score']:.3f}, ECE={cell['ece']:.3f}, "
            f"MCE={cell['mce']:.3f}, Brier={cell['brier']:.3f}",
            "",
            "| Score bin | Count | Mean score | Accuracy | Gap |",
            "|---|---|---|---|---|",
        ]
        for b in cell["bins"]:
            if b["count"]:
                gap = abs(b["accuracy"] - b["mean_score"])
                lines.append(
                    f"| [{b['lower']:.1f}, {b['upper']:.1f}) | {b['count']} "
                    f"| {b['mean_score']:.3f} | {b['accuracy']:.3f} | {gap:.3f} |"
                )
            else:
                lines.append(f"| [{b['lower']:.1f}, {b['upper']:.1f}) | 0 | - | - | - |")
        lines.append("")
    lines += [
        "## What this does not establish",
        "",
        "These numbers describe agreement between score and outcome inside a",
        "synthetic episode generator with known ground truth. They are not a",
        "calibration measurement on real tasks, and a low ECE here must not be",
        "quoted as evidence that the controller is calibrated for real agent",
        "workloads. The hard-regime accuracy ceiling (0.388 at ~2.4x the beam",
        "baseline's observation cost; see benchmarks/reports/reasoning-ablation.md)",
        "applies to this synthetic environment as well.",
        "",
        "## Pending real-task protocol (not executed)",
        "",
        "1. Collect real tasks with independently verifiable outcomes.",
        "2. Run a live LLM agent under the branch-control protocol; record",
        "   transcripts, per-decision confidence and observation cost.",
        "3. Grade outcomes independently of the agent (human or oracle).",
        "4. Apply `reliability_bins`/`summarize_reliability` to the real",
        "   (confidence, outcome) pairs and report ECE/MCE/Brier with provenance.",
        "5. Only then may calibration claims be made; until then the reference",
        "   thresholds remain defaults awaiting calibration.",
        "",
        "Status: PENDING. The 1.2.7 audit had no LLM API access, so steps 1-4",
        "were not run and no real-task result is claimed.",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261119)
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--difficulty", default="all", choices=["all", *_DIFFICULTY])
    parser.add_argument("--json-out", default=None, help="optional path for raw results JSON")
    parser.add_argument(
        "--report-out",
        default=None,
        help="markdown report destination (default: benchmarks/reports/reasoning-reliability.md)",
    )
    args = parser.parse_args(argv)
    result = run_synthetic_reliability(
        seed=args.seed, trials=args.trials, difficulty=args.difficulty
    )
    report = render_report(result)
    if args.report_out is None:
        repo_root = Path(__file__).resolve().parents[3]
        args.report_out = str(repo_root / "benchmarks" / "reports" / "reasoning-reliability.md")
    out = Path(args.report_out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"synthetic reliability report written -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
