# Model Report: Do Ice Cream Sales Cause Drowning Deaths?

**Date:** 2026-09-19 · **Rigor level:** standard *(chosen at Phase 0; see rigor.md)*
**Idea as stated:** *"Model this idea mathematically: ice cream sales and drowning deaths rise together in summer; does ice cream cause drownings?"*
**Model in one sentence:** This idea reduces to a **confounding bias** problem - a classic spurious correlation where a third variable (summer heat / season) drives both ice cream sales and drowning, so correlation != causation.

**Plain-language summary:**
Ice cream sales and drowning deaths rise together, but buying ice cream does not make people drown. Both are driven by a hidden third variable - **summer temperature** - which sends people to buy ice cream and to swim. When you statistically hold temperature constant (a backdoor adjustment), the raw correlation of **0.96 collapses to about -0.07**, i.e. essentially zero. The single number that matters most is the **partial correlation after adjusting for season**. The assumption that breaks first is that temperature is the *only* common cause; humidity, holidays, and beach attendance can also confound.

---

## 1. Decomposition

| Sub-problem | Nature | Archetype match |
|---|---|---|
| P1. Observed co-movement | uncertainty | **Spurious correlation** between two time series |
| P2. Hidden common cause | interaction | **Confounding by a third variable (season/temperature)** |
| P3. Causal structure | interaction | **DAG with a backdoor path** through the confounder |
| P4. Adjusted effect estimate | decision | **Covariate adjustment / partial correlation** |

Couplings: P1 is the raw observation; P2 identifies the confounder; P3 encodes it as a DAG; P4 closes the backdoor path to recover the (null) causal effect.

## 2. Parameters

| Symbol | Name | Unit | Exo/Endo | Range (typical) | Source | Sensitivity | In model(s) |
|--------|------|------|----------|------------------|--------|-------------|-------------|
| X | ice cream sales | $/day | endo | >= 0 | derived | — | dag, adjust |
| Y | drowning deaths | count/day | endo | >= 0 | derived | — | dag, adjust |
| Z | summer temperature | C | exo | 10-35 | data | high | dag, adjust |
| r_xy | raw correlation X,Y | (-) | endo | 0-1 | derived | — | adjust |
| r_xy.z | partial corr X,Y given Z | (-) | endo | -1-1 | derived | — | adjust |
| n | number of days observed | days | exo | 90-365 | data | medium | adjust |

Excluded: humidity as a second confounder (folded into Z - flagged [S]); individual-level vs city-level aggregation (ecological fallacy); time lags.

Derived quantities:
- **r_xy** - raw (marginal) correlation between ice cream and drowning.
- **r_xy.z** - partial correlation controlling for temperature (backdoor adjustment).

## 3. Assumptions

| # | Assumption | Type | Violation consequence |
|---|------------|------|----------------------|
| 1 | Temperature is the (only) common cause | Structural | Other confounders (holidays, beach crowds) leave residual bias |
| 2 | No reverse causation (drowning does not affect sales) | Structural | A feedback path would need a different identification strategy |
| 3 | Linear relationships between Z, X, Y | Regime | Nonlinear heat effects bias the linear partial correlation |
| 4 | No measurement error in temperature | Parametric | Noisy Z under-adjusts, leaving spurious partial correlation |
| 5 | City-level data reflect individual behavior | Boundary | Ecological fallacy - aggregate correlation need not hold per person |

Load-bearing assumptions: **#1 (temperature is the common cause)** and **#3 (linearity)** - if another hidden variable drives both, or the heat effect is strongly nonlinear, the adjustment leaves residual confounding.

## 4. Perspective models

```
### Causal DAG (backdoor structure)
Model:      Z -> X  and  Z -> Y  (temperature causes both);
            the X -> Y edge is the hypothesis under test.
            X <- Z -> Y is an open backdoor path that induces
            correlation even when X does not cause Y.
Fits because: it encodes P2 and P3 - the confounding structure explicitly.
Unique insight: the backdoor criterion says conditioning on Z blocks the
                non-causal path, isolating the true X -> Y effect.
Blind spot: a DAG assumes the structure; it cannot discover an unmeasured confounder.
```

```
### Covariate adjustment (partial correlation / regression)
Model:      regress X on Z and Y on Z, then correlate the residuals:
            r_xy.z = corr(X - E[X|Z], Y - E[Y|Z]).
            Simulated summer data: raw r_xy = 0.962, adjusted r_xy.z = -0.068.
Fits because: it delivers P4 - the adjusted effect estimate.
Unique insight: the near-total collapse of the correlation after adjustment is
                the quantitative signature of pure confounding.
Blind spot: linear adjustment only removes the linear component of confounding.
```

Rejected lenses (one line each):
- **Randomized controlled trial** - the gold standard, but you cannot randomize weather or drownings.
- **Instrumental variables** - no plausible instrument for ice cream sales is available.

## 5. Comparison

| Criterion (1-5) | Causal DAG | Covariate adjustment |
|---|---|---|
| Makes causal structure explicit | 5 | 2 |
| Gives a numeric effect | 1 | 5 |
| Robustness to assumptions | 3 | 3 |
| Interpretability to a layperson | 4 | 4 |

**Recommendation:** **Causal DAG** to state the structure and the backdoor criterion, with **covariate adjustment (partial correlation)** to deliver the number - justified by the DAG's 5/5 on structure and adjustment's 5/5 on the numeric answer.

## 6. Implementation & validation

```python
import numpy as np
import numpy.linalg as la
rng = np.random.default_rng(0); n = 365
temp = 20 + 12*np.sin(2*np.pi*np.arange(n)/365) + rng.normal(0,2,n)
ice   = 50 + 8*temp + rng.normal(0,15,n)      # ice cream ~ temp
drown = 2 + 0.3*temp + rng.normal(0,0.5,n)    # drowning ~ temp
r_raw = np.corrcoef(ice, drown)[0,1]          # 0.962
def resid(y, X):
    b = la.lstsq(np.column_stack([np.ones(len(X)), X]), y, rcond=None)[0]
    return y - np.column_stack([np.ones(len(X)), X]) @ b
r_adj = np.corrcoef(resid(ice,temp), resid(drown,temp))[0,1]  # -0.068
```

Sanity checks run:
- **Raw correlation:** r_xy = 0.962 (strong, as observed). **PASS**
- **Backdoor adjustment:** r_xy.z = -0.068 (collapses to ~0). **PASS**
- **Confounding confirmed:** removing Z removes the association. **PASS**
- **Theory-match:** matches the classic spurious-correlation / confounding result. **PASS**

Sensitivity sweep (top-2): **strength of Z->X** and **strength of Z->Y**. The stronger either link, the larger the spurious raw correlation - and the more completely adjustment removes it. Adding a second, unmeasured confounder (humidity) leaves a small residual partial correlation.

## 7. Predictions & falsifiability

Concrete predictions:
1. Raw correlation between ice cream sales and drowning **~0.96** in summer-driven data.
2. Partial correlation controlling for temperature **~ -0.07 (statistically ~0)**.
3. Within a narrow temperature band (e.g. only 30 C days), ice cream and drowning are **uncorrelated**.

Killed by (mapped back to assumptions):
- **Correlation persists after adjusting for temperature AND season** -> kills A1 (temperature as sole common cause); a real link or another confounder exists.
- **Correlation holds in winter, at constant cold temperature** -> kills the confounding explanation (A1/A3); points to a genuine or reverse link.
- **Adjusting for temperature only weakens but does not remove the link** -> kills A3 (linearity) or A4 (no measurement error).

## 8. Confidence ledger

| Claim | Type | Basis |
|-------|------|-------|
| Correlation != causation when a common cause exists | established | causal-inference theory |
| Conditioning on the confounder blocks the backdoor path | established | backdoor criterion (Pearl) |
| Raw correlation collapses to ~0 after adjusting for temperature | established as model consequence | computed here on simulated data |
| Temperature is the ONLY confounder | assumption | A1; humidity/holidays may also confound |
| Effect estimate -0.07 is exactly zero | speculation | finite-sample noise around a true null |

## 9. Research-tier appendix

None (rigor level: standard).

---

*Generated via Axiomize workflow · rigor level: standard · archetypes matched: confounding bias, causal DAG with backdoor path, covariate adjustment / partial correlation, spurious correlation.*
*Archive note: generated as a stored blind-test artifact for `benchmarks/ideas.json` case `causal-confounding`; numbers computed with axiomize 2.1.0 (seed 0).*

