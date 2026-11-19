# Reasoning score-outcome reliability (SYNTHETIC diagnostic)

> **SYNTHETIC episodes with known ground truth; no LLM calls. This is a score-outcome consistency diagnostic inside a synthetic environment, NOT calibration evidence on real tasks. Real-task validation is pending.**

Label: `synthetic-diagnostic`. Seed 20261119, 300 episodes per difficulty, collapse_score 0.65, LLM calls: 0.

Confidence is the leader's `branch_score` at collapse, or the surviving
argmax branch's score at the deadline. Bins are equal-width in score.

## Difficulty: easy

n=300, accuracy=1.000, mean score=0.663, ECE=0.337, MCE=0.337, Brier=0.114

| Score bin | Count | Mean score | Accuracy | Gap |
|---|---|---|---|---|
| [0.0, 0.1) | 0 | - | - | - |
| [0.1, 0.2) | 0 | - | - | - |
| [0.2, 0.3) | 0 | - | - | - |
| [0.3, 0.4) | 0 | - | - | - |
| [0.4, 0.5) | 0 | - | - | - |
| [0.5, 0.6) | 0 | - | - | - |
| [0.6, 0.7) | 300 | 0.663 | 1.000 | 0.337 |
| [0.7, 0.8) | 0 | - | - | - |
| [0.8, 0.9) | 0 | - | - | - |
| [0.9, 1.0) | 0 | - | - | - |

## Difficulty: moderate

n=300, accuracy=0.913, mean score=0.659, ECE=0.254, MCE=0.256, Brier=0.142

| Score bin | Count | Mean score | Accuracy | Gap |
|---|---|---|---|---|
| [0.0, 0.1) | 0 | - | - | - |
| [0.1, 0.2) | 0 | - | - | - |
| [0.2, 0.3) | 0 | - | - | - |
| [0.3, 0.4) | 0 | - | - | - |
| [0.4, 0.5) | 0 | - | - | - |
| [0.5, 0.6) | 3 | 0.593 | 0.667 | 0.074 |
| [0.6, 0.7) | 297 | 0.660 | 0.916 | 0.256 |
| [0.7, 0.8) | 0 | - | - | - |
| [0.8, 0.9) | 0 | - | - | - |
| [0.9, 1.0) | 0 | - | - | - |

## Difficulty: hard

n=300, accuracy=0.413, mean score=0.657, ECE=0.244, MCE=0.599, Brier=0.299

| Score bin | Count | Mean score | Accuracy | Gap |
|---|---|---|---|---|
| [0.0, 0.1) | 0 | - | - | - |
| [0.1, 0.2) | 0 | - | - | - |
| [0.2, 0.3) | 0 | - | - | - |
| [0.3, 0.4) | 0 | - | - | - |
| [0.4, 0.5) | 0 | - | - | - |
| [0.5, 0.6) | 1 | 0.599 | 0.000 | 0.599 |
| [0.6, 0.7) | 299 | 0.657 | 0.415 | 0.242 |
| [0.7, 0.8) | 0 | - | - | - |
| [0.8, 0.9) | 0 | - | - | - |
| [0.9, 1.0) | 0 | - | - | - |

## What this does not establish

These numbers describe agreement between score and outcome inside a
synthetic episode generator with known ground truth. They are not a
calibration measurement on real tasks, and a low ECE here must not be
quoted as evidence that the controller is calibrated for real agent
workloads. The hard-regime accuracy ceiling (0.388 at ~2.4x the beam
baseline's observation cost; see benchmarks/reports/reasoning-ablation.md)
applies to this synthetic environment as well.

## Pending real-task protocol (not executed)

1. Collect real tasks with independently verifiable outcomes.
2. Run a live LLM agent under the branch-control protocol; record
   transcripts, per-decision confidence and observation cost.
3. Grade outcomes independently of the agent (human or oracle).
4. Apply `reliability_bins`/`summarize_reliability` to the real
   (confidence, outcome) pairs and report ECE/MCE/Brier with provenance.
5. Only then may calibration claims be made; until then the reference
   thresholds remain defaults awaiting calibration.

Status: PENDING. The 1.2.7 audit had no LLM API access, so steps 1-4
were not run and no real-task result is claimed.
