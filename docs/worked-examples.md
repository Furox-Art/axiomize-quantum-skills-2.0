# Worked Examples: Modeling and Reasoning Together

**These are illustrative sketches, not measured results.** Each one below is a short
narrative of what the two halves of Axiomize do together on a given problem. No numbers are
reported here, because none of these runs is recorded in the repository with its seed and
commit. For reports that *are* recorded and reproducible, use:

- [`example-gallery.md`](example-gallery.md) — 18 complete worked reports in
  [`examples/`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples), written to the 8-phase report contract
- [`benchmark-results.md`](benchmark-results.md) — 25 graded cases with script, version,
  commit and platform, plus the seed-controlled reasoning sweeps

The pattern in each sketch below is the same, and it is the thing worth taking away:

1. The modeling layer produces **several independent formulations** with explicit
   parameters, units and assumptions.
2. The reasoning layer keeps them **all alive**, spending evidence to separate them.
3. A formulation is **rejected with a stated reason**, not quietly dropped.
4. Collapse happens only when the evidence actually separates the candidates.

## Example 1: Drug dosing schedule

The reasoning layer holds three dosing strategies at once — fixed interval, weight-based,
response-adaptive. The modeling layer simulates each against the same patient cohort. The
weakest strategy is eliminated by accumulated evidence rather than by preference. What
survives is reported with its falsifiers: the observation that would show it is wrong.

A complete graded report along these lines is in the repository:
[`benchmarks/reports/biology-drug-dosing.md`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/benchmarks/reports/biology-drug-dosing.md)
— one-compartment pharmacokinetics, with a numeric oracle. It is a benchmark case rather
than one of the 18 gallery examples, which is why there is no matching file in `examples/`.

## Example 2: Supply chain under uncertainty

Multiple demand scenarios stay alive in parallel and each gets a full simulation. Only when
the data clearly favours one inventory policy does the system commit to it. The result is
a distribution over outcomes, not a single number presented as settled.

Complete report:
[`examples/supply-chain-inventory.md`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/supply-chain-inventory.md)
(newsvendor plus safety stock, queueing and control composed).

## Example 3: Epidemic threshold estimation

Competing R0 hypotheses are held simultaneously. Bayesian updates eliminate implausible
values as evidence accumulates, and the output is a **posterior distribution**, not a point
estimate dressed up as certainty.

Complete report:
[`examples/epidemic-sir.md`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/epidemic-sir.md)
(deterministic SIR with a stochastic check; also graded as the
`epidemic-threshold` benchmark case).

## Try it yourself

```bash
axiomize-reason score --evidence 0.9 --verification 0.85
```

```json
{"branch": "branch-1", "can_collapse": false, "reason": "leader score below collapse threshold"}
```

The threshold that governs that decision is calibrated against a recorded sweep, not chosen
by feel. See the collapse-threshold section of
[`benchmark-results.md`](benchmark-results.md).