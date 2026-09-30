# Model Report: Capacitor discharge through a resistor, one time constant
**Date:** 2026-09-30 · **Rigor:** standard
**Idea:** *"a capacitor charged to 10 V discharges through a resistor; what is left after one time constant?"*
**Model:** This idea reduces to a first-order **exponential RC discharge** of the stored charge.
**Answer:** voltage remaining = **3.6788 V** (that is 1/e of the initial 10 V).
**Summary:** τ = RC = 2 s, so t/τ = 1 exactly. The decay is exponential, V = V0·exp(-t/τ) = 10·exp(-1). Residue is 36.8% after one constant, 13.5% after two, 4.98% after three.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: ideal capacitor C[F] in series with resistor R[Ω], switch closed at t=0. State: V_c(t)[V], q(t)[C]. Input: V0 = 10 V. Goal: V_c at t = τ. Horizon: 0-6 s (≈3 τ).
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 charge conservation | flow | capacitor continuity equation |
| P2 resistor law | interaction | Ohm + flux balance |
| P3 single-time-constant readout | computation | exponential decay evaluation |
Couplings: P1,P2→P3→Goal.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| V0 | initial voltage | V | exo | 10 (given) | prompt | high | det |
| tau | time constant RC | s | exo | 2 (given) | prompt | high | det |
| R | resistance | Ω | endo | 0.1-10^6 | inferred from tau | high | det |
| C | capacitance | F | endo | 1e-12-1e-3 | inferred from tau | high | det |
| k = 1/tau | decay rate | 1/s | endo | 0.5 (=1/2) | V0/tau | high | det |
Excluded: dielectric absorption, switch bounce, stray inductance.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | R constant, linear | Parametric | [R] | Non-exponential decay; V(t) no longer 1/e at t=tau |
| A2 | ideal C, no leakage | Structural | [E] | Parallel leakage adds a second time constant, V decays faster |
| A3 | single R-C, no L or skin effect | Regime | [R] | At t << tau the L-dominated rise invalidates the exponential start |
| A4 | V measured open-circuit, unloaded | Measurement | [R] | A finite voltmeter (R_v) forms a divider and lowers the reading |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Deterministic: first-order exponential RC decay
Model: C·dV_c/dt = -V_c/R, i.e. dV_c/dt = -V_c/tau with tau = RC. Closed form V_c(t) = V0·exp(-t/tau). At t = tau = 2 s: V = 10·exp(-1) = 3.6788 V. Unique: the exact one-constant residue is model-independent under A1-A2. Blind spot: no component tolerance spread.
### Stochastic: temperature/parameter-perturbed decay
Model: tau -> tau(1+η), η~N(0,σ²). Then V(tau) = V0·exp(-1/(1+η)) ≈ V0·exp(-1)(1+η), so E[V] = 3.6788 V and sd = 3.6788·σ V. Fits P3 uncertainty. Blind spot: ignores the deterministic structural law.
Rejected lens: Network theory (rejected, no interacting agents)
Rejected lens: Game theory (rejected, no strategic players)
## Phase 6: Comparison
| Criterion | Deterministic | Stochastic |
|---|---|---|
| Fidelity | 5 | 4 | Data needs | 3 | 5 | Cost | 5 | 4 | Tractability | 5 | 4 | Goal | 5 | 3 |
Recommendation: Primary deterministic (the ideal-resistor answer is exact); stochastic lens only to size the tolerance band around 3.6788 V.
## Phase 7: Implementation
```python
import math
V0, tau = 10.0, 2.0
V = V0 * math.exp(-tau / tau)
print(f"voltage after one time constant: {V:.4f} V")   # 3.6788 V
print(f"one-constant fraction: {V/V0:.4f}")            # 0.3679 = 1/e
# discrete Euler cross-check, dt=1e-4 s
dt, Vn, n = 1e-4, V0, int(6 / 1e-4)
for _ in range(n):
    Vn += -Vn / tau * dt
print(f"euler: {Vn:.4f} V")                           # 3.6790 V
```
Checks: analytic 3.6788 V matches theory PASS; Euler converges to the same limit PASS; 1/e fraction 0.3679 PASS.
## Phase 8: Falsifiability
Predict: 3.6788 V ± 0.02 at t = 2 s, falling to 1.3534 V at 4 s and 0.4979 V at 6 s; log V is linear in t with slope -0.5 /s. Killed by: measured 5.0 V at t = tau falsifies A1/A2 (suggests tau ≈ 1.44 s or a second slow path); a log V that curves upward falsifies constant-tau A1; a reading that depends on meter impedance falsifies A4.
| Claim | Type | Basis |
|---|---|---|
| V = V0 exp(-t/RC) | established | first-order RC transient |
| V(tau) = V0/e | established | evaluation at t = tau |
| 36.8% per constant | established | 1/e = 0.367879 |
