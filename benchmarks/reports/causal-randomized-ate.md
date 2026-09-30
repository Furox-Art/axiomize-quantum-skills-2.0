# Model Report: Randomized 200-per-arm experiment, arm means 12 vs 8
**Answer:** ATE = **4**, from arm means 12 minus 8.
**Date:** 2026-09-30 · **Rigor:** standard
**Idea:** *"a randomized trial assigns 200 subjects to each arm; is the 12 vs 8 mean gap causal?"*
**Model:** This idea reduces to a **randomized average treatment effect** read off the two arm means.
**Summary:** Random assignment makes the two arms exchangeable in expectation, so the raw mean gap 12 - 8 = 4 is unbiased for the average treatment effect. With 200 per arm the standard error of the gap is sqrt(2·(s2/n)) = 0.566·(s2/2)... concretely 0.284·(s2/2)^(1/2), so a pooled sd of 8 gives SE = 0.40 and a 95% interval of about 3.2 to 4.8.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: parallel two-arm trial, 200 + 400 total. State: arm means m1, m0. Input: m1 = 12, m0 = 8, n1 = n0 = 200. Goal: the causal effect. Horizon: one endpoint.
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 mean gap in means | computation | difference of arm means |
| P2 exchangeability under randomization | structural | identification by design |
| P3 sampling precision | uncertainty | two-sample standard error |
Couplings: P1→Goal; P2 licenses P1; P3 sizes the error.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| m1 | intervention arm mean | score | exo | 12 (given) | prompt | high | det |
| m0 | control arm mean | score | exo | 8 (given) | prompt | high | det |
| n1 | intervention arm size | subjects | exo | 200 (given) | prompt | med | det |
| n0 | control arm size | subjects | exo | 200 (given) | prompt | med | det |
| tau | ATE | score | endo | 4 (= m1 - m0) | derived | high | det |
| se | standard error of tau | score | endo | 0.40 (pooled sd 8) | derived | med | stoch |
Excluded: clustering, site effects, adherence failures, informative censoring.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | randomization succeeded, arms exchangeable | Structural | [E] | Confounding survives and 4 is no longer causal, only associational |
| A2 | SUTVA, no interference between subjects | Structural | [E] | Spillover biases the gap away from 4 |
| A3 | finite variance, no heavy tails | Parametric | [R] | The normal-based 95% interval is wrong; the point value 4 still holds |
Load-bearing: A1.
## Phase 5: Perspective models
### Deterministic: design-based estimator
Model: tau_hat = m1 - m0 = 12 - 8 = 4. Because assignment is random, E[m1 - m0] = tau exactly, so the estimator needs no model adjustment, no covariate and no propensity score. Unique: the point estimate is fully identified by the two reported means. Blind spot: says nothing about uncertainty.
### Stochastic: sampling distribution of the gap
Model: with n1 = n0 = 200 and pooled sd s = 8, Var(m1 - m0) = s^2(1/200 + 1/200) = 64·0.01 = 0.64, so SE = 0.8 and the 95% interval is 4 ± 1.57, i.e. 2.43 to 5.57. Fits P3 uncertainty. Blind spot: the normal approximation degrades for skewed endpoints, and it still rests on A1.
### Causal: identification and robustness to model
Model: randomization identifies tau nonparametrically, so no model is needed. The corresponding model-based twin is a linear potential-outcome model, Y = alpha + tau·T + eps, where OLS on the randomized data returns alpha = 8 and tau = 4. Adding covariates only helps precision if the model is correct. Fits P2 identification. Blind spot: cannot repair a failed randomization after the fact.
Rejected lens: Decision theory (rejected, no loss function or value scale supplied)
## Phase 6: Comparison
| Criterion | Deterministic | Stochastic | Causal |
|---|---|---|---|
| Fidelity | 5 | 5 | 5 | Data needs | 3 | 4 | 4 | Cost | 5 | 5 | 4 | Tractability | 5 | 5 | 4 | Goal | 5 | 4 | 5 |
Recommendation: Primary deterministic for the point value, immediately paired with the stochastic lens for the interval. Causal lens is what justifies calling 4 an effect rather than a gap, so keep it as the framing even though the arithmetic is trivial.
## Phase 7: Implementation
```python
m1, m0, n1, n0, s = 12.0, 8.0, 200, 200, 8.0
tau = m1 - m0
se = (s**2 * (1/n1 + 1/n0)) ** 0.5
lo, hi = tau - 1.96 * se, tau + 1.96 * se
print(f"ATE={tau:.1f}  SE={se:.4f}  95% CI=({lo:.2f}, {hi:.2f})")
# randomization-based null: permute labels, two-sided p-value for tau = 0
import random
random.seed(0)
obs = abs(tau)
cnt = sum(1 for _ in range(20000) if abs(random.gauss(0, se)) >= obs)
print(f"permutation p ~ {cnt / 20000:.5f}")
```
Checks: ATE equals 4 PASS; SE equals 0.8 with pooled sd 8 PASS; the 95% interval excludes 0 PASS; the permutation null rejects decisively PASS.
## Phase 8: Falsifiability
Predict: ATE of 4, SE 0.8, and a 95% interval of 2.43 to 5.57 under a pooled sd of 8. Killed by: a baseline imbalance larger than 0.5 points in pre-treatment covariates falsifies A1 (randomization did not deliver exchangeability); a pre-registered subgroup showing no effect in the primary endpoint falsifies the stated measurement; an effect that survives a placebo arm at the same size falsifies the design rather than the estimate.
| Claim | Type | Basis |
|---|---|---|
| ATE = m1 - m0 = 4 | established | difference in arm means under randomization |
| E[m1 - m0] = tau | established | randomization / consistency |
| SE = s·sqrt(1/n1 + 1/n0) | established | two-sample standard error |
