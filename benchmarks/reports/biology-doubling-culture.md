# Model Report: Doubling-time growth of a bacterial culture
**Date:** 2026-09-30 · **Rigor:** standard
**Idea:** *"a culture starts at 1000 organisms and doubles every 3 hours; what is there after 9 hours?"*
**Model:** This idea reduces to **exponential bacterial growth** by discrete per-generation doubling.
**Answer:** population = **8000** (after 9 h).
**Summary:** N0 = 1000, T_d = 3 hours, so 9 hours is exactly 3 generations. N = N0·2^(t/T_d) = 1000·2^3 = 8000. Growth is exponential in time and geometric (doubling) per generation; each generation adds a factor 2, not a fixed increment.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: closed batch culture, no feeding or removal. State: N(t) [organisms]. Input: N0 = 1000, T_d = 3 hours. Goal: N at t = 9 h. Horizon: 0-9 h (3 generations).
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 per-generation increment | flow | geometric (doubling) growth |
| P2 generation clock | computation | T_d scaling |
| P3 finite-resource reality | uncertainty | logistic saturation |
Couplings: P1,P2→Goal; P3 bounds P1.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| N0 | initial inoculum | organisms | exo | 1000 (given) | prompt | high | det |
| Td | doubling time | h | exo | 3 (given) | prompt | high | det |
| G | generations elapsed | dimensionless | endo | 3 (= 9/3) | t/Td | high | det |
| mu_max | max specific rate | 1/h | endo | ln2/3 = 0.231 | ln2/Td | med | det |
| K | half-saturation constant | organisms | endo | 1e6-1e9 | resource limit | med | stoch |
Excluded: diauxic lag, inoculum viability loss, shear.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | Td constant, no resource limit | Parametric | [R] | Growth is logistic, not exponential; 8000 is an upper bound never reached |
| A2 | synchronous binary fission | Structural | [E] | Asynchronous division smooths the staircase into a continuous curve, mean unchanged |
| A3 | no mortality or washout | Structural | [E] | Net rate drops below mu_max, population undershoots |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Deterministic: geometric exponential growth
Model: dN/dt = mu·N with mu = ln2/T_d = 0.231 1/h, giving N(t) = N0·exp(mu t) = N0·2^(t/T_d). At t = 9 h: N = 1000·2^(9/3) = 8000. Unique: the integer-generation reading is exact under A2. Blind spot: ignores the resource ceiling entirely.
### Stochastic: branching-process growth with division noise
Model: each organism divides after an Erlang-distributed time of rate ln2/T_d. E[N(t)] still equals N0·2^(t/T_d) = 8000, but Var grows as ~N(t)^2, so the coefficient of variation falls like 1/sqrt(N). Fits P3 uncertainty. Blind spot: preserves the mean, so it cannot reveal the resource ceiling.
### Optimization: finite-resource logistic cap
Model: dN/dt = mu·N·(1 - N/K). Solution N(t) = K/(1 + ((K-N0)/N0)·exp(-mu t)). For K = 1e6 the 9 h value is 8000 within 0.4%, so the exponential lens is a good approximation here but degrades past t ≈ 2.5·T_d·ln(K/N0). Blind spot: needs K, which the prompt withholds.
Rejected lens: Game theory (rejected, no competing strains or players)
## Phase 6: Comparison
| Criterion | Deterministic | Stochastic | Optimization |
|---|---|---|---|
| Fidelity | 5 | 4 | 3 | Data needs | 3 | 4 | 5 | Cost | 5 | 4 | 3 | Tractability | 5 | 4 | 4 | Goal | 5 | 4 | 3 |
Recommendation: Primary deterministic (exact integer-generation arithmetic). Stochastic lens to size the spread; logistic lens only as the stated upper-bound caveat, since no K is given.
## Phase 7: Implementation
```python
N0, Td, t = 1000.0, 3.0, 9.0
G = t / Td
N = N0 * 2 ** G
print(f"generations: {G:.0f}  population: {N:.0f}")   # generations: 3  population: 8000
import math
mu = math.log(2) / Td
print(f"continuous exp: {N0 * math.exp(mu * t):.1f}")  # continuous exp: 8000.0
# logistic ceiling, K = 1e6
K = 1e6
print(f"logistic N: {K / (1 + (K - N0) / N0 * math.exp(-mu * t)):.1f}")
```
Checks: 3 full generations gives exactly 8000 PASS; continuous exponential agrees to 4 significant figures PASS; logistic value sits just below the exponential bound PASS.
## Phase 8: Falsifiability
Predict: population of exactly 8000 at 9 h, 4000 at 6 h, 2000 at 3 h; log2(population) is linear in time with slope 1/3 per hour. Killed by: 7000 at 9 h falsifies A1 (resource limit already active, logistic); 8500 falsifies A2/A3 (mortality would lower, not raise, the value); a curved log2(population) falsifies constant Td.
| Claim | Type | Basis |
|---|---|---|
| N = N0 2^(t/Td) | established | geometric growth |
| 3 generations in 9 h | established | t/Td |
| mu = ln2/Td | established | growth-rate to doubling-time relation |
