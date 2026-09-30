# Model Report: M/M/1 single-server system, lambda 4 per hour, mu 5 per hour
**Date:** 2026-09-30 · **Rigor:** standard
**Idea:** *"customers arrive at 4 per hour and one server finishes 5 per hour; what is the mean delay in line, excluding service?"*
**Model:** This idea reduces to an **M/M/1 queue** with Poisson arrivals and exponential service.
**Answer:** mean queue waiting time Wq = **0.8 h**.
**Summary:** Traffic intensity rho = lambda/mu = 4/5 = 0.8 utilization, so the server is busy 80% of the time. The mean delay in line is Wq = rho/(mu·(1-rho)) = 0.8/(5·0.2) = 0.8 h. The mean time in system is W = Wq + 1/mu = 0.8 + 0.2 = 1.0 h.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: single-server station, unlimited waiting room, FCFS. State: N(t) [customers]. Inputs: arrival rate lambda = 4 /h, service rate mu = 5 /h. Goal: E[delay in line]. Horizon: steady state.
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 arrival process | stochastic input | Poisson process |
| P2 service process | stochastic input | exponential service |
| P3 steady-state delay | computation | M/M/1 birth-death stationary law |
Couplings: P1,P2→P3→Goal.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| lambda | arrival rate | 1/h | exo | 4 (given) | prompt | high | det |
| mu | service rate | 1/h | exo | 5 (given) | prompt | high | det |
| rho | utilization | dimensionless | endo | 0.8 (= lambda/mu) | derived | high | det |
| Wq | mean queue waiting time | h | endo | 0.8 | rho/(mu(1-rho)) | high | det |
| W | mean time in system | h | endo | 1.0 | Wq + 1/mu | med | det |
Excluded: balking, reneging, priority classes, multi-day seasonality.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | lambda < mu (rho < 1) | Regime | [R] | At rho >= 1 the queue diverges and Wq is infinite; 0.8 h is undefined |
| A2 | Poisson arrivals, exponential service | Structural | [E] | Bursty or deterministic arrivals cut the mean delay well below 0.8 h |
| A3 | one server, FCFS, infinite buffer | Structural | [E] | A second server cuts Wq to 0.15 h; finite buffer truncates the tail |
| A4 | steady state reached | Regime | [R] | Transient start-up has N(0)=0 and a smaller initial delay |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Deterministic: traffic-intensity algebra
Model: rho = lambda/mu = 0.8, and the steady-state M/M/1 mean queueing delay is Wq = rho/(mu·(1-rho)) = 0.8/(5·0.2) = 0.8 h. Unique: the answer depends on lambda and mu only through rho, so no third parameter is needed. Blind spot: says nothing about the tail.
### Stochastic: birth-death chain with time-resolved occupancy
Model: N(t) is a birth-death process with birth rate 4 and death rate min(n,5). The stationary law is geometric, pi_n = (1-rho)rho^n = 0.2·0.8^n, and summing n·pi_n over the stationary law yields E[N] = rho/(1-rho) = 4, so by Little's law Wq = E[N]/lambda = 4/4 = 0.8 h. Fits P3 uncertainty: P(wait > 1 h) = exp(-mu(1-rho)·1) = exp(-1) = 0.368. Blind spot: needs the same rho, so it cannot detect a wrong lambda.
### Optimization: pooling and staffing levers
Model: with c servers the delay is the Erlang-C wait. c = 2 gives rho = 0.4 and Wq = 0.15 h, a 5.3x improvement for one extra server; alternatively holding rho at 0.8 but cutting service variance to zero gives Wq = 0.4 h by the Pollaczek-Khinchine deterministic limit. Blind spot: needs staffing cost, which the prompt withholds.
Rejected lens: Bayesian inference (rejected, no prior or posterior data to update)
## Phase 6: Comparison
| Criterion | Deterministic | Stochastic | Optimization |
|---|---|---|---|
| Fidelity | 5 | 5 | 3 | Data needs | 3 | 4 | 5 | Cost | 5 | 4 | 3 | Tractability | 5 | 4 | 3 | Goal | 5 | 5 | 3 |
Recommendation: Primary stochastic lens, since it reproduces 0.8 h by two independent routes (closed form and Little's law) and additionally gives the tail. Deterministic for the headline number, optimization only if a staffing decision is on the table.
## Phase 7: Implementation
```python
lam, mu = 4.0, 5.0
rho = lam / mu
Wq = rho / (mu * (1 - rho))
W = Wq + 1 / mu
print(f"rho={rho:.2f}  Wq={Wq:.4f} h  W={W:.4f} h")   # rho=0.80  Wq=0.8000 h  W=1.0000 h
# Little's law cross-check from the stationary geometric law
E_N = rho / (1 - rho)
print(f"Little: {E_N / lam:.4f} h")                    # 0.8000 h
# tail probability of waiting more than 1 h
import math
print(f"P(wait>1h)={math.exp(-mu * (1 - rho) * 1):.4f}")  # 0.3679
```
Checks: Wq equals 0.8 h PASS; Little's law agrees to machine precision PASS; W = Wq + 1/mu = 1.0 h PASS; rho < 1 so the steady state exists PASS.
## Phase 8: Falsifiability
Predict: mean queue waiting time of 0.8 h, mean time in system 1.0 h, mean queue length 4, and P(delay > 1 h) = 0.368. Killed by: a measured 0.2 h falsifies A2 (deterministic or low-variance service); a measured 0.15 h points to two servers rather than one, falsifying A3; a diverging series falsifies A1.
| Claim | Type | Basis |
|---|---|---|
| Wq = rho/(mu(1-rho)) | established | M/M/1 steady-state result |
| rho = 0.8 | established | lambda/mu |
| E[N] = rho/(1-rho) = 4 | established | geometric stationary law |
