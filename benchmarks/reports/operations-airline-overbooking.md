# Model Report: Airline overbooking (expected show-ups 194.75)
**Date:** 2026-09-27 · **Rigor:** standard
**Idea:** *"airline sells 205 tickets for a 200-seat plane; each passenger independently shows with probability 0.95."*
**Model:** This idea reduces to **binomial overbooking / newsvendor** analysis: N ~ Binomial(205, 0.95), expected show-ups 194.75, P(overbook) ≈ 0.0224.
**Summary:** Expected show-ups: 194.75 passengers, i.e. 5.25 seats empty on average, while the risk of exceeding capacity is only ≈ 2.2 percent with ≈ 0.032 expected denied boardings per flight. Selling 205 is comfortable; the newsvendor critical fractile pins the optimal sales figure once bump cost is priced.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: single flight, capacity C=200. State: N[,] show-ups. Inputs: S=205 sales, show probability p=0.95. Goal: expected show-ups, oversale probability, expected denied boardings. Horizon: one departure.
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 show-up count | uncertainty | binomial |
| P2 capacity breach | flow | threshold crossing |
| P3 sales level choice | decision | newsvendor critical fractile |
Couplings: P1→P2; P3 set by cost trade-off.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| S | tickets sold | , | exo | 200-215 | booking system | high | det |
| p | show probability | , | exo | 0.9-0.97 | history | high | stoch |
| C | seat capacity | , | exo | 200 | fleet | low | det |
| cb | denied boarding cost | $ | exo | est. | policy | high | det |
Excluded: group bookings (correlation), cancellations vs no-shows.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | independent show decisions | Parametric | [R] | family groups raise tail risk; P(overbook) underestimated |
| A2 | stationary p over days | Structural | [E] | weekend/holiday drift biases mean |
| A3 | denied boarding allowed (legal) | Regime | [R] | risk becomes hard constraint, not cost |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Stochastic: binomial show-up model
Model: N ~ Binomial(S=205, p=0.95). Expected show-ups: E[N]=S·p=194.75; sd=√(S·p·(1−p))≈3.04. Oversale probability P(N>200)=0.0224; expected denied boardings E[(N−200)+]≈0.032 per flight. Fits P1+P2. Unique: exact distribution. Blind: independence is a modeling convenience.
### Optimization: newsvendor sales policy
Model: choose S maximizing expected net revenue; critical fractile P(N≤C)=cb/(cb+cs) with cs the empty-seat (spoilage) cost. If cb≫cs the fractile pushes sales DOWN to ≈ 200-202; if bump cost is small, sales above 205 stay optimal. Fits P3 decision. Blind: requires cost ratio.
Rejected lens: Deterministic (rejected, show-ups are fundamentally random)
## Phase 6: Comparison
| Criterion | Stochastic | Optimization |
|---|---|---|
| Fidelity | 5 | 4 | Data needs | 4 | 3 | Cost | 5 | 3 | Tractability | 5 | 3 | Goal | 4 | 5 |
Recommendation: primary binomial risk numbers; newsvendor layer once cost ratio is priced.
## Phase 7: Implementation
```python
from scipy.stats import binom
S, p, C = 205, 0.95, 200
mu = S*p
p_over = 1 - binom.cdf(C, S, p)
denied = sum((k-C)*binom.pmf(k, S, p) for k in range(C+1, S+1))
print(f"expected show-ups {mu:.2f}, P(overbook) {p_over:.4f}, E[denied] {denied:.4f}")
```
Checks: E[N]=194.75 PASS; P(overbook)≈0.022 PASS; E[denied]≈0.032 PASS.
## Phase 8: Falsifiability
Predict: over 1000 flights, ≈22±14 flights bump at least one passenger and mean show-ups land in 194.75±1.5. Killed by: empirical show-up correlation within bookings (A1 dead, move to beta-binomial); p trending by weekday (A2 dead); regulation banning oversale (A3 dead, model becomes constraint).
| Claim | Type | Basis |
|---|---|---|
| binomial show-up count | established | classical revenue-management model |
| critical fractile rule | established | newsvendor theory |
