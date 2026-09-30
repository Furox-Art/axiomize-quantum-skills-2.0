# Model Report: First-order disappearance of a compound, rate 0.1 per hour
**Date:** 2026-09-30 · **Rigor:** standard
**Idea:** *"a compound decays by first-order kinetics with k = 0.1 per hour; how long until it is reduced by one half?"*
**Model:** This idea reduces to a **first-order chemical** decay channel, C(t) = C0·exp(-k t).
**Answer:** half-life = **6.9315 h**.
**Summary:** t(half) = ln(2)/k = 0.6931/0.1 = 6.9315 h. Because the decay is first-order, the half-life is independent of the starting amount and of k's other context: it is the single number 0.6931/k. After 3 half-lives only 12.5% remains.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: closed homogeneous batch, single first-order channel. State: C(t) [mol/L]. Input: k = 0.1 /h, C0. Goal: time to halve. Horizon: 0-30 h (≈4.3 half-lives).
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 loss channel | flow | first-order decay |
| P2 time-to-halve readout | computation | exponential inversion |
| P3 channel independence | uncertainty | multi-exponential mixture |
Couplings: P1→P2→Goal; P3 perturbs P2.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| k | first-order rate constant | 1/h | exo | 0.1 (given) | prompt | high | det |
| t_half | halving time | h | endo | 6.9315 (= ln2/k) | ln2/k | high | det |
| C0 | initial concentration | mol/L | endo | 0-1 | not given | low | det |
| k_obs | observed rate | 1/h | endo | 0.1 | k | high | det |
| ln2 | dilog constant | dimensionless | endo | 0.6931 | exact | high | det |
Excluded: reversible binding, matrix partitioning, temperature ramp.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | k constant in time | Parametric | [R] | Buffer catalysis, pH drift or solvent change makes t_half drift; the single number 6.9315 h no longer holds |
| A2 | well-mixed, no spatial gradient | Structural | [E] | Diffusion-limited zones decay slower, apparent half-life inflates |
| A3 | single first-order path, no reverse reaction | Structural | [E] | Reversible binding stretches the tail and inflates the apparent half-life |
Load-bearing: A1,A3.
## Phase 5: Perspective models
### Deterministic: closed-form first-order decay
Model: dC/dt = -k·C, so C(t) = C0·exp(-k t). Setting C = C0/2 gives t_half = ln(2)/k = 0.6931/0.1 = 6.9315 h. Unique: the analytic result needs only k, so the missing C0 is genuinely irrelevant. Blind spot: no measurement noise on k.
### Stochastic: renewal-process decay
Model: replace deterministic flow with a Poisson hazard at rate k. Then C(t) is a pure-death process; E[C(t)] = C0·exp(-k t) exactly, and the hitting time of the half-level concentrates near 6.9315 h with relative sd ~ 1/sqrt(k·t_half) ≈ 0.38. Fits P3 uncertainty. Blind spot: same mean, so it cannot flag a drifting k.
### Reliability: competing parallel channels
Model: two independent channels with rates k1, k2 give C(t) = C0·(a·exp(-k1 t) + (1-a)·exp(-k2 t)). If k2 is small, the apparent half-life is inflated to 6.9315·(1 + k2/k1) and never truly reaches a plateau. Blind spot: requires the unknown k2, so it can only bound the error.
Rejected lens: Game theory (rejected, no strategic actors)
## Phase 6: Comparison
| Criterion | Deterministic | Stochastic | Reliability |
|---|---|---|---|
| Fidelity | 5 | 4 | 3 | Data needs | 3 | 4 | 5 | Cost | 5 | 4 | 3 | Tractability | 5 | 4 | 3 | Goal | 5 | 4 | 2 |
Recommendation: Primary deterministic (the answer is exactly 6.9315 h and needs no extra data). Stochastic lens for measurement spread, reliability lens only as a bias warning.
## Phase 7: Implementation
```python
import math
k = 0.1
t_half = math.log(2) / k
print(f"half-life: {t_half:.4f} h")                     # 6.9315 h
# direct bisection on C(t) = C0/2 as an independent check
lo, hi = 0.0, 100.0
for _ in range(200):
    mid = (lo + hi) / 2
    if math.exp(-k * mid) > 0.5:
        lo = mid
    else:
        hi = mid
print(f"bisected: {(lo + hi) / 2:.4f} h")              # 6.9315 h
print(f"remaining after 3 half-lives: {0.5 ** 3:.4f}")  # 0.1250
```
Checks: closed form and bisection agree to 1e-9 h PASS; three half-lives leave 12.5% PASS; result is independent of C0 PASS.
## Phase 8: Falsifiability
Predict: halving at 6.9315 h, quarter remaining at 13.863 h, 12.5% at 20.794 h; ln C is linear in t with slope -0.1 /h. Killed by: 5% remaining at 6.93 h falsifies A3 (a second slow channel is inflating the tail); a curved ln C falsifies A1; a halving time that scales with C0 falsifies the first-order classification itself.
| Claim | Type | Basis |
|---|---|---|
| C = C0 exp(-k t) | established | first-order kinetics |
| t_half = ln2/k = 6.9315 h | established | exact inversion |
| half-life independent of C0 | established | first-order rate law |
