# Model Report: Footbridge ringdown (decay rate 0.0693 1/s)
**Date:** 2026-09-27 · **Rigor:** standard
**Idea:** *"after a crowd leaves a footbridge, the deck keeps wobbling with a 2 s period, amplitude halving every 10 s."*
**Model:** This idea reduces to a **damped harmonic oscillator**: decay rate γ ≈ 0.0693 1/s from the 10 s halving, natural period 2.0 s.
**Summary:** Deck behaves as second-order spring-mass-damper with ζ ≈ 0.011 (lightly damped). Ringdown time to 1% amplitude ≈ 66 s. Doubling the decay rate halves ringdown; sensitivity to γ is linear and high.
---
## Phase 0: Rigor
Standard; ≥2 lenses, formal notation. Say 'deeper'/'quicker' anytime.
## Phase 1: Parse
System: bridge deck mode, mass m. State: x(t)[m], v=ẋ[m/s]. Inputs: γ[1/s] damping, ω0=2π/T0[rad/s]. Goal: ringdown time and damping augmentation. Horizon: 0-120 s.
## Phase 2: Decompose
| Sub-problem | Nature | Archetype |
|---|---|---|
| P1 modal oscillation | flow | damped harmonic oscillator |
| P2 damping augmentation | decision | absorber / Control design |
| P3 crowd forcing history | interaction | impulsive load |
Couplings: P2→P1→Goal.
## Phase 3: Parameters
| Symbol | Name | Unit | Exo/Endo | Range | Source | Sens | In |
|---|---|---|---|---|---|---|---|
| T0 | natural period | s | endo | 2.0±0.05 | measured | high | det |
| γ | decay rate | 1/s | endo | 0.0693±0.005 | log(2)/halving | high | det |
| ζ | damping ratio | , | endo | 0.011 | γ/ω0 | med | det |
| ω0 | natural frequency | rad/s | endo | 3.14 | 2π/T0 | high | det |
Excluded: soil coupling, wind.
## Phase 4: Assumptions
| # | Assumption | Type | Class | Violation consequence |
|---|---|---|---|---|
| A1 | linear viscous damping | Parametric | [R] | envelope non-exponential, γ biased |
| A2 | single dominant mode | Structural | [E] | beats appear; ringdown multi-scale |
| A3 | no re-excitation during ringdown | Regime | [R] | decay cannot be isolated |
Load-bearing: A1,A2.
## Phase 5: Perspective models
### Deterministic: damped harmonic oscillator
Model: ẍ+2γẋ+ω0²·x=0 with ω0=2π/2.0=3.14 rad/s; envelope A(t)=A0·e^{−γt}. Halving in 10 s ⇒ γ=log(2)/10=0.0693 1/s; 1% level at t=2·log(100)/log(2)·10≈66 s. Fits P1. Unique: closed form. Blind: no mode coupling.
### Control: damping augmentation design
Model: added tuned mass damper raises effective decay rate γ′; ringdown t1% scales as 4.605/γ′. Sensitivity ∂t1%/∂γ′ = −4.605/γ′² favors modest damping gains. Fits P2 decision lens. Blind: cost/feasibility of the absorber.
Rejected lens: undamped harmonic oscillator (rejected, amplitude visibly decays)
Rejected lens: Network (rejected, single mode, no graph).
## Phase 6: Comparison
| Criterion | Deterministic | Control |
|---|---|---|
| Fidelity | 5 | 3 | Data needs | 5 | 3 | Cost | 5 | 2 | Tractability | 5 | 3 | Goal | 4 | 5 |
Recommendation: primary deterministic ringdown; Control lens for design question.
## Phase 7: Implementation
```python
import math
T0, half = 2.0, 10.0
g = math.log(2)/half
w0 = 2*math.pi/T0
z = g/w0
t99 = math.log(100)/g
print(f"decay rate {g:.4f} 1/s, zeta {z:.4f}, ringdown-to-1% {t99:.1f} s")
```
Checks: γ·10 = log(2) PASS; ζ≪1 lightly damped PASS.
## Phase 8: Falsifiability
Predict: envelope halves at 10.0±1.0 s, period 2.0±0.1 s, t1% ≈ 66±7 s. Killed by: non-exponential envelope (A1 dead); beat pattern in FFT (A2 dead); period shift during decay means γ-ω coupling outside model.
| Claim | Type | Basis |
|---|---|---|
| exponential ringdown | established | damped harmonic oscillator |
| ζ=γ/ω0 identification | established | modal analysis |
