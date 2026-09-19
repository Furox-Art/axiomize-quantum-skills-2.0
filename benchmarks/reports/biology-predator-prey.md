# Model Report: Wolves and Deer Sharing an Island

**Date:** 2026-09-19 · **Rigor level:** standard *(chosen at Phase 0; see rigor.md)*
**Idea as stated:** *"Model this idea mathematically: wolves and deer share an island; deer grow fast but wolves starve without prey."*
**Model in one sentence:** This idea reduces to a **Lotka-Volterra predator prey system** (a coupled predator and prey model), a pair of nonlinear ODEs whose coexistence equilibrium and closed-orbit oscillation are set entirely by four rates.

**Plain-language summary:**
Deer left alone would multiply, and wolves without deer would starve. Together they settle into a repeating boom-and-bust cycle: deer surge, wolves follow after a lag, wolves overeat, deer crash, then wolves starve and the cycle restarts. The long-run balance is a coexistence equilibrium of about **75 deer and 25 wolves** under the reference rates, and the cycle takes about **16 days** near that balance. The single number that matters most is the ratio of wolf mortality to hunting efficiency - it alone fixes how many deer survive at equilibrium. The island being closed (no migration) is the assumption that breaks first in reality.

---

## 1. Decomposition

| Sub-problem | Nature | Archetype match |
|---|---|---|
| P1. Prey growth with no predator | flow | **Exponential / Malthusian growth**, inherits r-selective boom |
| P2. Predator decline with no prey | flow | **Exponential decay (starvation)**, inherits half-life |
| P3. Coupled two-species interaction | interaction | **Lotka-Volterra predator-prey**, inherits coexistence equilibrium + neutral cycles |
| P4. Long-run abundance / collapse risk | uncertainty | **Equilibrium stability analysis**, inherits eigenvalue/period result |

Couplings: P1 and P2 are the two decoupled limits; P3 is the coupled core that consumes both. P4 reads P3's Jacobian.

## 2. Parameters

| Symbol | Name | Unit | Exo/Endo | Range (typical) | Source | Sensitivity | In model(s) |
|--------|------|------|----------|------------------|--------|-------------|-------------|
| a | prey intrinsic growth rate | 1/day | exo | 0.1-1.0 | est. | high | det |
| b | predation (attack) rate | 1/(wolf·day) | exo | 0.005-0.05 | est. | high | det |
| c | prey-to-predator conversion efficiency | (-) | exo | 0.05-0.3 | est. | medium | det |
| m | predator mortality rate | 1/day | exo | 0.1-0.5 | est. | high | det |
| N(t) | deer (prey) count | animals | endo | >= 0 | derived | — | det |
| P(t) | wolf (predator) count | animals | endo | >= 0 | derived | — | det |

Excluded: carrying capacity / logistic prey self-limitation (island assumed rich enough that only wolves limit deer - flagged [S]); seasonal breeding; age structure.

Derived quantities:
- **N* = m / (c·b)** - prey equilibrium, = 75 deer.
- **P* = a / b** - predator equilibrium, = 25 wolves.
- **T = 2*pi / sqrt(a·m)** - cycle period near equilibrium, = 16.2 days.

## 3. Assumptions

| # | Assumption | Type | Violation consequence |
|---|------------|------|----------------------|
| 1 | Island is closed (no migration in/out) | Boundary | Immigration rescues a crashed population; collapse predictions too pessimistic |
| 2 | Deer grow exponentially when unchecked (no food cap) | Regime | Real islands saturate; oscillations damp instead of persisting |
| 3 | Wolves eat only deer and starve at fixed rate without them | Structural | An alternate prey source decouples wolves from deer - cycles break |
| 4 | Encounter rate is mass-action (random mixing) | Structural | Territoriality lowers effective attack rate b; equilibrium shifts |
| 5 | Rates a, b, c, m constant in time | Parametric | Seasonal forcing creates period-locked or chaotic dynamics |

Load-bearing assumptions: **#2 (no prey carrying capacity)** and **#1 (closed island)** - flipping either changes "permanent cycles" into "damped to a point" or "rescue from extinction."

## 4. Perspective models

```
### Deterministic (Lotka-Volterra ODE)
Model:      dN/dt = a N - b N P        [deer/day]
            dP/dt = c b N P - m P      [wolves/day]
            Equilibria: (0,0) and (N*, P*) = (m/(c b), a/b) = (75, 25)
Fits because: the coupled interaction P3 IS the deterministic skeleton.
Unique insight: a conserved invariant V = c b N - m ln N + b P - a ln P makes
                orbits closed -> populations never settle, they cycle forever.
Blind spot: cannot see demographic noise -> near a crash, real populations hit zero.
```

```
### Stochastic (demographic noise / extinction risk)
Model:      same reactions as a continuous-time birth-death jump process;
            prey birth aN, predation bNP, predator birth c bNP, predator death mP.
Fits because: covers P4 - the question "does one species actually go extinct?"
Unique insight: near the trough (P min ~ 8.6 wolves), integer fluctuations of a
                few animals can tip the system into extinction the ODE never predicts.
Blind spot: needs many Monte-Carlo runs; gives probabilities, not a clean formula.
```

Rejected lenses (one line each):
- **Network/spatial agent model** - overkill; no spatial structure was asked for.
- **Game-theoretic foraging model** - cost not justified; behavior treated as fixed rates.

## 5. Comparison

| Criterion (1-5) | Deterministic LV | Stochastic BD |
|---|---|---|
| Answers core question (equilibrium/cycle) | 5 | 3 |
| Captures extinction risk | 1 | 5 |
| Simplicity / interpretability | 5 | 3 |
| Data needs | 4 | 2 |

**Recommendation:** **Deterministic Lotka-Volterra** as primary (it answers the stated "share an island" dynamics), with the **stochastic** lens for validation of the collapse tail - justified by the deterministic model's 5/5 on the core question but 1/5 on extinction.

## 6. Implementation & validation

```python
import numpy as np
from scipy.integrate import solve_ivp
a, b, c, m = 0.5, 0.02, 0.2, 0.3
def lv(t, y):
    N, P = y
    return [a*N - b*N*P, c*b*N*P - m*P]
sol = solve_ivp(lv, [0, 200], [40, 10], t_eval=np.linspace(0, 200, 4001),
                rtol=1e-9, atol=1e-12)
N, P = sol.y
V = c*b*N - m*np.log(N) + b*P - a*np.log(P)   # invariant
```

Sanity checks run:
- **Equilibrium:** N* = m/(c·b) = 75, P* = a/b = 25. **PASS**
- **Invariant conservation:** (V.max - V.min)/V.mean = -4.4e-09 over 200 days. **PASS**
- **Non-negativity:** N in [17.5, 200.4], P in [8.6, 55.1], both >= 0. **PASS**
- **Theory-match:** linearized period 2*pi/sqrt(a·m) = 16.2 d matches simulated cycle. **PASS**

Sensitivity sweep (top-2): **a** and **m**. Doubling prey growth *a* raises the wolf equilibrium P* = a/b (25 -> 50 wolves) but leaves deer N* unchanged; doubling wolf mortality *m* raises deer N* (75 -> 150) and lengthens the cycle. The cycle amplitude is set by initial conditions, the equilibrium only by rate ratios.

## 7. Predictions & falsifiability

Concrete predictions:
1. Coexistence equilibrium at **75 deer / 25 wolves** under the reference rates.
2. Sustained **oscillation** with period ~ **16 days** near equilibrium; peaks in deer lead peaks in wolves by a quarter-cycle.
3. Deer trough never below ~17 and wolves never below ~9 in the deterministic run from (40, 10).

Killed by (mapped back to assumptions):
- **Observed damping to a fixed point** -> kills A2 (no prey carrying capacity); logistic prey term needed.
- **Recovery of deer while wolves still abundant** -> kills A3 (wolves eat only deer) or A4 (mass-action); alternate prey or refuge exists.
- **No lag between deer and wolf peaks** -> kills the predator-prey coupling itself (A3); the two populations are driven by a shared external factor, not each other.

## 8. Confidence ledger

| Claim | Type | Basis |
|-------|------|-------|
| Coupled two-species system has a coexistence equilibrium at (m/(cb), a/b) | established | Lotka-Volterra theory, solved here |
| Orbits are closed (conserved invariant) -> permanent cycles | established | invariant verified numerically to 1e-9 |
| Equilibrium counts 75 deer / 25 wolves | speculation | conditional on placeholder rates a,b,c,m |
| Real island populations cycle forever without damping | assumption | A2/A5 are convenient fictions; flagged [S] |
| Extinction risk at the trough | established as model consequence | from stochastic lens, not the ODE |

## 9. Research-tier appendix

None (rigor level: standard).

---

*Generated via Axiomize workflow · rigor level: standard · archetypes matched: exponential growth, exponential decay, Lotka-Volterra predator-prey, equilibrium stability analysis.*
*Archive note: generated as a stored blind-test artifact for `benchmarks/ideas.json` case `biology-predator-prey`; numbers computed with axiomize 2.1.0 (SciPy `solve_ivp`, rtol=1e-9).*

