# Model Report: Drug dosing interval (half-life 6 h)
**Date:** 2026-09-27 · **Rigor:** standard
**Idea:** *"after a pill, drug level peaks at 40 mg/L, halves every 6 hours; ineffective below 5 mg/L, harmful above 60 mg/L - when is the next dose due?"*
**Model:** This idea reduces to **one-compartment pharmacokinetics** with first-order elimination: next dose at ≈ 18 h, when concentration reaches the 5 mg/L floor.
**Summary:** C(t)=40·2^{−t/6}; the therapeutic window is [5, 60] mg/L and the peak never exceeds 60, so dosing is safe; the level stays effective for three half-lives, giving a dosing interval of ≈ 18 h.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: patient bloodstream (single well-mixed compartment). State: C(t)[mg/L]. Inputs: dose D[mg], half-life t½=6 h, absorption lag. Goal: dosing interval τ[h] keeping C in window. Horizon: 0-72 h.
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 elimination flow | flow | one-compartment exponential decay |
| P2 steady-state accumulation | decision | repeated-dose superposition |
| P3 patient variability | uncertainty | lognormal parameter spread |
Couplings: P2,P3→P1→Goal.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| ke | elimination rate | 1/h | endo | 0.1155 | log(2)/6 | high | det |
| t½ | half-life | h | exo | 5-7 | label | high | det |
| Cmax | peak level | mg/L | endo | 40 | measured | high | det |
| MEC | minimum effective | mg/L | exo | 5 | clinical | high | det |
| MTC | toxic ceiling | mg/L | exo | 60 | clinical | high | det |
Excluded: liver-enzyme saturation, food effects.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | first-order elimination | Parametric | [R] | half-life not constant; interval wrong |
| A2 | one compartment, instant mixing | Structural | [E] | two-phase decay missed; early toxicity |
| A3 | complete absorption of dose | Regime | [R] | Cmax overestimated |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Deterministic: one-compartment ODE
Model: dC/dt = −ke·C with ke=log(2)/6=0.1155 1/h; C(t)=40·e^{−ke·t}. Window [5,60]: peak 40<60 safe; C reaches 5 mg/L at t= log(40/5)/ke = 3 half-lives = 18 h, so the dosing interval is τ≈18 h. Fits P1 flow. Unique: closed form, direct schedule. Blind: ignores accumulation across doses.
### Stochastic: between-patient variability
Model: t½ ~ LogNormal(6 h, CV≈0.25); simulate Monte Carlo of C(t) per patient; choose τ so P(C<MEC) ≤ 5% at end of interval → conservative τ ≈ 16-18 h. Fits P3. Unique: population safety bands. Blind: requires variability data.
Rejected lens: Game theory (rejected, no strategic players)
## Phase 6: Comparison
| Criterion | Deterministic | Stochastic |
|---|---|---|
| Fidelity | 4 | 4 | Data needs | 5 | 2 | Cost | 5 | 3 | Tractability | 5 | 3 | Goal | 4 | 5 |
Recommendation: primary deterministic interval; Stochastic bands before clinical use.
## Phase 7: Implementation
```python
import math
ke = math.log(2)/6
tau = math.log(40/5)/ke
resid = lambda t: 40*math.exp(-ke*t)
print(f"ke {ke:.4f} 1/h, next dose at {tau:.1f} h, C(18)={resid(18):.1f} mg/L")
```
Checks: C(18)=5.0 mg/L PASS; peak 40<60 no toxicity PASS.
## Phase 8: Falsifiability
Predict: measured level at 12 h is 20±2 mg/L and at 24 h is 2.5±0.7 mg/L without redose. Killed by: biphasic decay curve (A2 dead); half-life drifting with dose (A1 dead); severity rises above 60 with one pill (A3 or label data dead).
| Claim | Type | Basis |
|---|---|---|
| exponential elimination | established | pharmacokinetics (one-compartment) |
| τ = 3 half-lives for 8x drop | established | closed form of exponential decay |
