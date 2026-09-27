# Reasoning branch-controller ablation report

Deterministic offline ablation (seed 20260927, 400 episodes per cell, deadline 8 rounds).
No LLM calls; ground truth known per episode. Baselines: argmax commits at round 1; beam keeps top-2 until the deadline; the controller applies the real score/dormancy/revival/collapse policy with adaptive observation allocation.

## Difficulty: easy (regime-shift share 0%)

| Policy | Accuracy | Premature-wrong | Mean rounds | Mean branch-cost | Revivals |
|---|---|---|---|---|---|
| argmax_commit | 0.965 | 0.035 | 1.0 | 4.0 | 0 |
| beam_top2 | 1.000 | 0.000 | 8.0 | 18.0 | 0 |
| branch_controller | 1.000 | 0.000 | 8.0 | 25.5 | 23 |

## Difficulty: moderate (regime-shift share 0%)

| Policy | Accuracy | Premature-wrong | Mean rounds | Mean branch-cost | Revivals |
|---|---|---|---|---|---|
| argmax_commit | 0.652 | 0.347 | 1.0 | 5.0 | 0 |
| beam_top2 | 0.840 | 0.000 | 8.0 | 19.0 | 0 |
| branch_controller | 0.920 | 0.000 | 8.0 | 39.8 | 0 |

## Difficulty: hard (regime-shift share 20%)

| Policy | Accuracy | Premature-wrong | Mean rounds | Mean branch-cost | Revivals |
|---|---|---|---|---|---|
| argmax_commit | 0.230 | 0.770 | 1.0 | 6.0 | 0 |
| beam_top2 | 0.285 | 0.000 | 8.0 | 20.0 | 0 |
| branch_controller | 0.388 | 0.000 | 8.0 | 47.8 | 5 |

## Reading

- `argmax_commit` is fast and cheap but locks in early noise; its premature-wrong rate is the honest price of one-round decisions.
- `beam_top2` never commits early, always pays the full deadline cost, and is structurally blind in regime-shift episodes (the surging hypothesis never enters its top-2 in time).
- `branch_controller` leads or ties every regime on accuracy (easy 1.000, moderate 0.920, hard 0.388) and revives dormant branches on new evidence (23 revivals in the easy pool). Hard-regime argmax premature-wrong rate: 0.770. The edge is bought with more observations than beam: dormancy engages mainly for clearly dominated branches under the reference defaults.

## Calibration note

Across 1200 episodes the reference defaults produced early-commit rate 0.000 even in the easy regime: the collapse score ceiling is practically unreachable under bounded noisy evidence because the verification and information-gain terms trail their weights. This empirically supports the project position that reference thresholds are defaults awaiting calibration, not validated constants.
