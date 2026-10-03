# Worked Example Gallery

Eighteen worked examples live in [`examples/`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples) in this repository. Each turns
a plain-language idea into a mathematical model, states which perspectives it rejected and
why, and closes with explicit falsification criteria.

**Structure.** Reports follow the 8-phase report layout used by the examples: Phase 1
Parse, Phase 2 Decompose, Phase 3 Parameters, Phase 4 Assumptions, Phase 5 Perspective
models, Phase 6 Comparison, Phase 7 Implementation, Phase 8 Falsifiability, followed by a
confidence ledger. `skills/axiomize/templates/report.md` is the blank form.

**What these are, and what they are not.** These are **illustrative worked examples**
written and reviewed by the maintainer as demonstrations of the workflow and the report
contract. They are *not* measured results, *not* benchmark outputs, and the numbers in them
are illustrative parameter choices rather than fitted values from a named dataset. Where an
example states a closed-form value, it is given with its tolerance so you can re-derive it
yourself. For graded, reproducible numbers with provenance, see
[benchmark-results.md](benchmark-results.md) instead.

**Parameter provenance.** Examples tag each parameter as `exo` (exogenous, supplied) or
`endo` (endogenous, to be estimated) and give units. The three markers used for parameter
sources are `lit.` (literature value), `data` (fitted from your own data) and `est.`
(estimated). Treat an `est.` value as a placeholder until you replace it with your own.

**Validation.** Every example is a plausible model, not a verified one. Before trusting an
example's conclusions, re-derive its closed-form checks with
`python skills/axiomize/tools/benchmark_runner.py --case <id> --report <path>`, or adapt it
to a Model IR and run `axiomize model --action validate`.

## Epidemiology

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Epidemic spread](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/epidemic-sir.md) | Deterministic (+ stochastic check) | Epidemiology | An SIR model exposes an R₀ threshold: whether an outbreak explodes or dies out is decided before any stochastic detail matters. |
| [Biology population dynamics](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/biology-population.md) | Stochastic / population | Biology | Lotka-Volterra-type competition sets coexistence conditions that a single-species fit would miss. |

## Product and growth

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [App adoption growth](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/startup-growth.md) | Deterministic (Bass diffusion, archetype-first) | Product growth | A single well-chosen archetype (Bass ODE), calibrated on real signups and gated by BIC, answers ceiling and stall-timing questions. |

## Stochastic and risk

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Insurance ruin risk](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/insurance-ruin.md) | Stochastic | Insurance / risk | For rare-event solvency questions, deterministic averages are useless; ruin probability is a tail property that only a stochastic model can price. |
| [Retail inventory under uncertain demand](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/supply-chain-inventory.md) | Stochastic (+ optimization, control) | Retail operations | Demand randomness converts a restocking question into an (s,Q) policy built from newsvendor logic plus safety stock. |

## Optimization and queueing

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Coffee shop staffing](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/coffee-shop-staffing.md) | Optimization (+ queueing) | Service operations | An Erlang-C wait cliff embedded in an ILP shows lenses composing: queueing computes the wait, optimization schedules the staff. |

## Network

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Rumor spread in a school](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/network-rumor.md) | Network | Social dynamics | Who-connects-to-whom changes the answer: contact structure, not just counts, decides how far a rumor travels and whether a public announcement stops it. |

## Control

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Greenhouse night temperature](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/control-greenhouse.md) | Control | Agriculture / building systems | Keeping temperature above a setpoint against disturbances is a feedback problem; heater policy follows from the control view, not from prediction alone. |
| [Engineering control design](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/engineering-control.md) | Control (+ optimization) | Engineering | Settling time and overshoot constraints turn "make it stable" into a concrete, solvable design problem. |

## Game theory

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Two cafes pricing war](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/cafe-pricing-war.md) | Game theory | Economics / competition | A 20% price cut looks profitable when rivals are frozen; game theory reveals the rival's response term that single-actor optimization cannot see. |

## Causal inference

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Marketing attribution](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/marketing-attribution.md) | Causal inference | Digital marketing | Users who see retargeting ads buying 3x more is selection, not effect; backdoor confounding must be adjusted before spending follows. |

## Information theory

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Sensor placement](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/sensor-placement.md) | Information theory | Data centre monitoring | When you cannot measure everything, mutual information tells you which 3 sensor locations carry the most signal about overheating. |

## Reliability

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Delivery fleet preventive maintenance](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/fleet-maintenance.md) | Reliability | Logistics | Fixed-schedule versus run-to-failure becomes decidable once breakdown timing gets a Weibull hazard and costs go through renewal-reward analysis. |

## Physics, chemistry and climate

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Physics oscillator](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/physics-oscillator.md) | Deterministic | Physics | Damping and forcing terms are separated so the resonance question has an answer that a naive ODE fit does not. |
| [Chemistry reaction](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/chemistry-reaction.md) | Deterministic (+ stochastic) | Chemistry | Mass-action kinetics give a closed-form half-life, which is exactly what you check the numeric solver against. |
| [Climate energy balance](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/climate-energy.md) | Deterministic (+ thermodynamic) | Climate | A two-box energy balance makes the feedback sign, not the parameter values, the thing worth being careful about. |

## Probability and finance

| Example | Primary lens | Domain | One-line takeaway |
|---|---|---|---|
| [Bayesian probability](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/probability-bayes.md) | Bayesian | Probability | Posterior predictive checks catch a model that fits the mean but not the spread. |
| [Finance portfolio](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/finance-portfolio.md) | Stochastic (+ optimization) | Finance | Risk parity and mean-variance disagree about the same data, and the disagreement is the useful output. |

---

Full texts: [`examples/`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples) — all 18 files listed above are present in this
repository at commit `9c2990c2ce77a131bce18d4e0e1a1d0c7822be51`.

Lenses available to compose: see `skills/axiomize/perspectives/` — agent-based,
causal-inference, control, decision-theory, demographic, deterministic, game-theory,
information-theory, network, optimization, reliability, spatial, spc, stochastic,
thermodynamic. Most examples use two and reject at least one.

To add an example, follow the contract in [CONTRIBUTING.md](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/CONTRIBUTING.md).