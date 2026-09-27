# Model Report: Training program under self-selection
**Date:** 2026-09-27 · **Rigor:** standard
**Idea:** *"employees who enjoyed math at school volunteered for our analytics training, and their productivity rose; did the training cause the gain?"*
**Model:** This idea reduces to **program evaluation under selection bias**: the naive Before/After contrast is rejected because ability confounds training uptake and productivity.
**Summary:** A DAG with ability → training and ability → productivty (backdoor path) shows the raw gain mixes the training effect with selection bias. Identification requires a counterfactual control group: propensity matching/IPW on measured covariates, difference-in-differences on panel data, or a randomized pilot. Without such a design the honest answer is "effect not identified".
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: firm workforce. State: productivity Y[$/day or units]. Inputs: training indicator T∈{0,1}, ability A[,] (math background), covariates X (tenure, role). Goal: causal effect E[Y(1)−Y(0)]. Horizon: pre+post windows (e.g., 3 months each).
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 treatment-effect identification | interaction | causal DAG / potential outcomes |
| P2 effect estimation given design | uncertainty | matching / IPW / DiD |
| P3 rollout decision | decision | scale vs pilot |
Couplings: P1 gates P2; P2 feeds P3.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| τ | average treatment effect | units/day | endo | unknown | to estimate | high | det |
| P(T=1|X) | propensity score | , | endo | 0-1 | logit on X | high | det/stoch |
| βA | ability→productivity | units/day | exo | unknown | regression aid | high | det |
| w | IPW weights | , | endo | 1-20 | 1/pscore | med | det |
Excluded: general-equilibrium effects, Hawthorne effects.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | conditional exchangeability given X | Structural | [E] | residual confounding; estimate biased by βA |
| A2 | positivity: 0<P(T=1|X)<1 | Parametric | [R] | extrapolation where no controls exist |
| A3 | SUTVA / no spillovers between employees | Regime | [R] | trained help untrained, attenuating τ |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Causal: DAG + potential outcomes
Model: DAG T←A→Y, T→Y; naive diff-in-means = τ + βA·(E[A|T=1]−E[A|T=0]) = τ + selection term. Identification: backdoor adjustment on A (ability proxies) → counterfactual means via propensity matching or IPW; with panel data, difference-in-differences removes time-invariant ability. Fits P1+P2. Unique: explicit assumptions. Blind: unmeasured motivation remains.
### Decision: staged rollout policy
Model: value of information: run pilot RCT (n≈200) at cost cp; expected payoff = P(τ>0)·scale gain − pilot cost; decide scale ↔ collect more evidence via epsilon-greedy rollout. Fits P3. Unique: turns identification uncertainty into a decision. Blind: needs payoff priors.
Rejected lens: plain OLS on observed sample (rejected, selection bias unaddressed)
Rejected lens: Thermodynamic (rejected, no energy conservation structure).
## Phase 6: Comparison
| Criterion | Causal | Decision |
|---|---|---|
| Fidelity | 5 | 3 | Data needs | 3 | 3 | Cost | 4 | 2 | Tractability | 4 | 3 | Goal | 5 | 4 |
Recommendation: primary Causal identification; Decision layer for rollout policy.
## Phase 7: Implementation
```python
import numpy as np
rng = np.random.default_rng(0); n = 400
A = rng.normal(size=n)                       # ability (confounder)
T = (A + rng.normal(size=n) > 0.2).astype(float)
Y = 10 + 2*T + 3*A + rng.normal(size=n)      # true tau = 2
naive = Y[T==1].mean() - Y[T==0].mean()      # inflated
import statsmodels.api as sm
X = np.column_stack([np.ones(n), T, A])
adj = sm.OLS(Y, X).fit().params[1]
print(f"naive {naive:.2f} vs backdoor-adjusted {adj:.2f} (true 2.0)")
```
Checks: naive > adjusted upward-bias reproduced PASS; adjusted ≈ 2.0 PASS.
## Phase 8: Falsifiability
Predict: on holdout hires with randomized assignment, adjusted τ transfers within ±25 percent; pre-trend test flat under DiD. Killed by: pre-trends diverge (DiD dead); overlap histogram empty region (A2 dead); effect vanishes after ability control entirely (training contributes nothing).
| Claim | Type | Basis |
|---|---|---|
| self-selection inflates naive contrast | established | program evaluation / selection bias |
| backdoor + propensity adjustment | established | potential-outcome identification theory |
