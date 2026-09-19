# Model Report: Store Reorder Policy Under Uncertain Demand

**Date:** 2026-09-19 · **Rigor level:** standard *(chosen at Phase 0; see rigor.md)*
**Idea as stated:** *"Model this idea mathematically: a store stocks a product with uncertain demand; how often should it reorder to avoid stockouts without overstock?"*
**Model in one sentence:** This idea reduces to an **EOQ inventory optimization** for the order quantity, layered with a **newsvendor / (Q,R) base-stock rule** that sets a safety stock from the demand distribution to balance stockouts against holding cost.

**Plain-language summary:**
Order too rarely and you run out; order too often and carrying cost eats you. There is a sweet spot: order about **141 units at a time, roughly every 52 days** (about 7 orders a year) under the reference cost numbers, and keep a **safety stock of about 16 units** so you only stock out 5% of replenishment cycles. The single number that matters most is the **ratio of fixed order cost to holding cost** - it sets the order size. Whether demand is steady or spiky is the assumption that changes the answer most.

---

## 1. Decomposition

| Sub-problem | Nature | Archetype match |
|---|---|---|
| P1. How much to order (batch size) | decision | **EOQ (economic order quantity)**, inherits sqrt cost trade-off |
| P2. When to reorder under uncertainty | decision | **(Q,R) / base-stock with safety stock** |
| P3. Single-period over/under-stock risk | uncertainty | **Newsvendor critical fractile** |
| P4. Demand variability | uncertainty | **Stochastic demand (Poisson / Normal)** |

Couplings: P4 (demand spread) drives P2 and P3 (safety stock, critical fractile); P1 sets the cycle length that P2's reorder point protects.

## 2. Parameters

| Symbol | Name | Unit | Exo/Endo | Range (typical) | Source | Sensitivity | In model(s) |
|--------|------|------|----------|------------------|--------|-------------|-------------|
| D | annual demand rate | units/yr | exo | 500-2000 | data | high | eoq |
| K | fixed order cost | $/order | exo | 20-100 | data | high | eoq |
| h | holding cost | $/unit/yr | exo | 2-10 | data | high | eoq |
| C_u | underage (stockout) cost | $/unit | exo | 10-40 | est. | high | newsvendor |
| C_o | overage (leftover) cost | $/unit | exo | 2-10 | est. | medium | newsvendor |
| mu_L | lead-time demand mean | units | exo | 20-80 | est. | medium | qr |
| sigma_L | lead-time demand std | units | exo | 5-20 | est. | high | qr |
| Q | order quantity | units | endo | >= 0 | derived | — | eoq, qr |
| R | reorder point | units | endo | >= 0 | derived | — | qr |

Excluded: quantity discounts (no bulk pricing stated - flagged [S]); multiple products / shelf-space coupling; perishability.

Derived quantities:
- **EOQ = sqrt(2 D K / h)** - economic order quantity, = 141 units.
- **Critical fractile = C_u / (C_u + C_o)** - newsvendor service target, = 0.80.
- **Safety stock = z_0.95 · sigma_L** - buffer for 95% cycle service level, = 16 units.

## 3. Assumptions

| # | Assumption | Type | Violation consequence |
|---|------------|------|----------------------|
| 1 | Demand is stationary (constant rate, no trend/season) | Parametric | A trend makes EOQ stale; reorder point too low in peak season |
| 2 | Lead-time demand ~ Normal (or Poisson) | Structural | Heavy-tailed demand causes far more stockouts than the model predicts |
| 3 | Costs K, h, C_u, C_o are constant and known | Parametric | Mis-estimated stockout cost flips the optimal service level |
| 4 | Fixed order cost per order, no quantity discount | Structural | Bulk discounts push toward larger, less frequent orders |
| 5 | Demand independent across periods | Structural | Correlated demand (promotions) breaks the i.i.d. safety-stock math |

Load-bearing assumptions: **#1 (stationary demand)** and **#3 (known stockout cost)** - flipping either changes both the order size and the service level.

## 4. Perspective models

```
### EOQ (deterministic cost balance)
Model:      total cost C(Q) = (D/Q) K + (Q/2) h
            dC/dQ = 0  ->  Q* = EOQ = sqrt(2 D K / h) = sqrt(2*1000*50/5) = 141 units
            orders/year = D/Q* = 7.1 ;  cycle time = 365 * Q*/D = 52 days
Fits because: answers P1, the order-size half of "how often to reorder".
Unique insight: cost near the optimum is flat - order size can be rounded freely.
Blind spot: assumes demand is known and steady; sees no stockout risk.
```

```
### Newsvendor + (Q,R) (stochastic service level)
Model:      critical fractile = C_u/(C_u + C_o) = 20/(20+5) = 0.80
            single-period Q* = F^-1(0.80) over demand ~ Normal(100, 25) = 121 units
            (Q,R): safety stock = z_0.95 * sigma_L = 1.645 * 10 = 16 units
                   reorder point R = mu_L + safety stock = 40 + 16 = 56 units
Fits because: answers P2 and P3, the uncertainty half - avoid stockouts.
Unique insight: the optimal service level is set by the cost RATIO, not the demand level.
Blind spot: single-period logic; ignores that leftover stock carries to next cycle.
```

Rejected lenses (one line each):
- **Dynamic programming / Markov decision process** - optimal but overkill; the (Q,R) rule is near-optimal here.
- **Discrete-event simulation of the whole store** - cost not justified for one product.

## 5. Comparison

| Criterion (1-5) | EOQ | Newsvendor/(Q,R) |
|---|---|---|
| Answers "how much" | 5 | 3 |
| Answers "how often / stockout risk" | 2 | 5 |
| Simplicity | 5 | 4 |
| Uses demand distribution | 1 | 5 |

**Recommendation:** **EOQ** sets the order quantity (141 units, ~every 52 days), **(Q,R) with safety stock** sets the reorder point (R = 56) - the two lenses are complementary, justified by EOQ's 5/5 on quantity and (Q,R)'s 5/5 on stockout risk.

## 6. Implementation & validation

```python
import numpy as np
from scipy.stats import norm
D, K, h = 1000.0, 50.0, 5.0
EOQ = np.sqrt(2*D*K/h)                 # 141.4 units
Co, Cu = 5.0, 20.0
crit = Cu/(Cu+Co)                      # 0.80
Q_nv = norm.ppf(crit, 100, 25)         # 121.0 units
mu_L, sd_L = 40.0, 10.0
R = mu_L + norm.ppf(0.95)*sd_L         # 56.4 units
```

Sanity checks run:
- **EOQ:** sqrt(2·1000·50/5) = 141.4, cost is minimized (dC/dQ = 0). **PASS**
- **Critical fractile:** 0.80 within (0,1). **PASS**
- **Safety stock:** z_0.95·sigma_L = 16.4 >= 0; reorder point R = 56.4 > mu_L. **PASS**
- **Theory-match:** matches standard EOQ / newsvendor closed forms. **PASS**

Sensitivity sweep (top-2): **h (holding cost)** and **C_u (stockout cost)**. Doubling h cuts EOQ by ~29% (141 -> 100); raising C_u from 20 to 40 lifts the critical fractile from 0.80 to 0.89 and the reorder point up with it.

## 7. Predictions & falsifiability

Concrete predictions:
1. Optimal order quantity **~141 units**, **~7 orders/year**, cycle **~52 days**.
2. Reorder point **R = 56 units** (40 mean lead-time demand + 16 safety stock) for a 95% cycle service level.
3. Stockouts in only **~5%** of replenishment cycles at that policy.

Killed by (mapped back to assumptions):
- **Frequent stockouts despite the reorder point** -> kills A2 (Normal demand); demand is heavier-tailed than modeled.
- **Seasonal stockouts every peak** -> kills A1 (stationary demand); a time-varying reorder point is needed.
- **Always-overstocked shelves** -> kills A3 (cost estimates); overage cost is lower or underage cost higher than assumed.

## 8. Confidence ledger

| Claim | Type | Basis |
|-------|------|-------|
| EOQ = sqrt(2DK/h) minimizes deterministic cost | established | EOQ theory, solved here |
| Critical fractile Cu/(Cu+Co) sets service level | established | newsvendor theory |
| Order ~141 units every ~52 days | speculation | conditional on D, K, h estimates |
| Safety stock ~16 units for 95% service | established as model consequence | from Normal lead-time demand assumption |
| Demand is stationary and Normal | assumption | A1/A2, flagged [S]; needs data check |

## 9. Research-tier appendix

None (rigor level: standard).

---

*Generated via Axiomize workflow · rigor level: standard · archetypes matched: EOQ inventory optimization, newsvendor critical fractile, (Q,R) base-stock with safety stock, stochastic demand.*
*Archive note: generated as a stored blind-test artifact for `benchmarks/ideas.json` case `operations-inventory`; numbers computed with axiomize 2.1.0.*

