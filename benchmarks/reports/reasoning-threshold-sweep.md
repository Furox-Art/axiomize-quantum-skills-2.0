# Collapse-threshold sweep (paired calibration evidence)

Paired sweep of `collapse_score` (seed 20260927, 400 episodes per cell per grid point; same episodes and same observation tapes for every threshold). Reference default: 0.78. All other thresholds unchanged.

## Difficulty: easy

| collapse_score | Accuracy | Collapse rate | Premature-wrong | Mean rounds | Mean cost |
|---|---|---|---|---|---|
| 0.60 | 1.000 | 0.990 | 0.000 | 5.30 | 19.8 |
| 0.65 | 1.000 | 0.950 | 0.000 | 5.85 | 21.3 |
| 0.70 | 1.000 | 0.000 | 0.000 | 8.00 | 25.9 |
| 0.72 | 1.000 | 0.000 | 0.000 | 8.00 | 25.9 |
| 0.75 | 1.000 | 0.000 | 0.000 | 8.00 | 25.9 |
| 0.78 | 1.000 | 0.000 | 0.000 | 8.00 | 25.9 |

## Difficulty: moderate

| collapse_score | Accuracy | Collapse rate | Premature-wrong | Mean rounds | Mean cost |
|---|---|---|---|---|---|
| 0.60 | 0.895 | 0.185 | 0.000 | 7.71 | 38.3 |
| 0.65 | 0.892 | 0.165 | 0.000 | 7.75 | 38.5 |
| 0.70 | 0.890 | 0.000 | 0.000 | 8.00 | 39.7 |
| 0.72 | 0.890 | 0.000 | 0.000 | 8.00 | 39.7 |
| 0.75 | 0.890 | 0.000 | 0.000 | 8.00 | 39.7 |
| 0.78 | 0.890 | 0.000 | 0.000 | 8.00 | 39.7 |

## Difficulty: hard

| collapse_score | Accuracy | Collapse rate | Premature-wrong | Mean rounds | Mean cost |
|---|---|---|---|---|---|
| 0.60 | 0.398 | 0.000 | 0.000 | 8.00 | 47.8 |
| 0.65 | 0.398 | 0.000 | 0.000 | 8.00 | 47.8 |
| 0.70 | 0.398 | 0.000 | 0.000 | 8.00 | 47.8 |
| 0.72 | 0.398 | 0.000 | 0.000 | 8.00 | 47.8 |
| 0.75 | 0.398 | 0.000 | 0.000 | 8.00 | 47.8 |
| 0.78 | 0.398 | 0.000 | 0.000 | 8.00 | 47.8 |

## Selection

Recommended measured candidate: **0.60** (earliest safe exits (easy-regime mean rounds 5.30) with zero hard-regime premature collapses).

Production defaults are intentionally unchanged in this change: the sweep is evidence for calibration, and the semantics of `DEFAULT_THRESHOLDS` stay under explicit project control.
