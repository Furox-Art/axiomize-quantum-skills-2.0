# Model Report: Catalyst replacement time ≈ 10 months
**Date:** 2026-09-27 · **Rigor:** standard
**Idea:** *"reactor catalyst loses about 5 percent activity per month; product spec fails below 60 percent; when to replace or regenerate?"*
**Model:** This idea reduces to **catalyst deactivation kinetics**: first-order activity decay gives specification threshold crossing at ≈ 9.96 months.
**Summary:** da/dt = −kd·a with kd = −log(0.95) = 0.0513 per month; activity hits the 60 percent specification constraint at t* = log(0.6)/log(0.95) ≈ 9.96 months. Economic optimization pulls replacement slightly earlier; schedule turnaround at month 9-10.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: fixed-bed reactor catalyst inventory. State: a(t)[,] relative activity. Inputs: kd[1/month] deactivation constant, spec floor[ₐ=0.6]. Goal: replacement/regeneration timer + economics. Horizon: 0-24 months.
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 activity decay | flow | first-order deactivation kinetics |
| P2 replacement timing | decision | Renewal / Optimization |
| P3 rate variability | uncertainty | temperature-driven decay spread |
Couplings: P3→P1→P2→Goal.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| kd | deactivation rate | 1/month | endo | 0.0513±0.01 | loss record | high | det |
| aspec | spec floor | , | exo | 0.6 | product spec | high | det |
| Cr | replacement cost | k$ | exo | 100-500 | procurement | med | det |
| L | output loss per Δa | k$/month | exo | est. | high | stoch |
Excluded: poisoning events, regeneration yield uncertainty.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | exponential first-order decay | Parametric | [R] | sintering gives a(t)=(1+kt)^{−1}; timing wrong |
| A2 | activity maps linearly to spec | Structural | [E] | selectivity losses appear before 0.6 |
| A3 | steady operating temperature | Regime | [R] | kd drifts; schedule slips |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Deterministic: deactivation kinetics
Model: da/dt = −kd·a, a(0)=1 ⇒ a(t)=0.95^t. Specification constraint a≥0.6 crosses at t* = log(0.6)/log(0.95) = 9.96 months. Fits P1. Unique: one-line schedule. Blind: treats decay as memoryless, ignores partial regeneration.
### Optimization: replacement economics
Model: total monthly cost C(T) = Cr/T + L·(1−ȧ(T)) with mean activity ȧ over cycle T; minimize C(T) over renewal interval T. With Cr high, optimum sits near but above the 10-month spec bound, so spec constraint binds: T≈9-10 months. Fits P2 decision. Blind: needs cost data.
Rejected lens: Spatial (rejected, well-mixed bed assumption leaves no spatial gradients)
## Phase 6: Comparison
| Criterion | Deterministic | Optimization |
|---|---|---|
| Fidelity | 4 | 3 | Data needs | 5 | 3 | Cost | 5 | 3 | Tractability | 5 | 3 | Goal | 4 | 5 |
Recommendation: Deterministic timer as baseline; Optimization once costs are quantified.
## Phase 7: Implementation
```python
import math
kd = -math.log(0.95)
t_star = math.log(0.6)/math.log(0.95)
print(f"kd {kd:.4f} 1/month, spec crossing {t_star:.2f} months")
```
Checks: a(9.96)=0.60 PASS; faster decay raises kd and shortens t* monotonic PASS.
## Phase 8: Falsifiability
Predict: activity at month 6 is 0.74±0.03 and spec crossing at 9.96±1 months. Killed by: leveling-off decay curve (A1 dead, try second-order or sintering); spec failure before activity floor (A2 dead); seasonal kd swings (A3 dead).
| Claim | Type | Basis |
|---|---|---|
| first-order deactivation | established | catalyst deactivation kinetics |
| t*=log(0.6)/log(0.95) | established | exponential threshold algebra |
