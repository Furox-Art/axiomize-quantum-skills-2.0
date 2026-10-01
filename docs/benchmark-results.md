# Benchmark Results

Every number on this page comes from a run that was executed and re-executed while writing
it. The command, the commit, the version and the platform are given so you can reproduce
it and get the same answer.

There are two separate things here, and they measure different things:

1. **The 25-case corpus** (`benchmarks/ideas.json` + `benchmarks/reports/`) — reports graded
   against the [rubric](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/benchmarks/rubric.md)
   by `skills/axiomize/tools/benchmark_runner.py`. This runs in CI on every push.
2. **The offline reasoning sweeps** — deterministic, seed-controlled experiments on
   synthetic episodes with known ground truth and no LLM calls.

---

## 1. Reproducible grading run

### Provenance

| Field | Value |
|---|---|
| Package | `axiomize-quantum-skills-2.0` **1.2.0** |
| Repository commit | `eb70a4766717d61ed10ffcfb618251162700c9b9` |
| Grading script | `skills/axiomize/tools/benchmark_runner.py` |
| Corpus | `benchmarks/ideas.json` — 25 cases |
| Reports | `benchmarks/reports/<id>.md` — 25 matching reports, 0 missing |
| Python | CPython 3.12.10, Windows AMD64 |
| Numeric stack | numpy 2.5.3, scipy 1.18.1 |
| Date run | during the OSS visibility pass on top of `eb70a47` |

### Reproduce a single case

```bash
python skills/axiomize/tools/benchmark_runner.py --case physics-rc-discharge --report benchmarks/reports/physics-rc-discharge.md
```

```text
must_contain[1]: exponential|RC|time constant                PASS
must_contain[2]: e\^|exp\(|1/e                               PASS
must_contain[3]: voltage                                     PASS
archetype 'exponential RC discharge' present                 PASS
perspectives built >= 1 (found 2)                            PASS
parameter Unit column non-empty                              PASS
assumptions have consequences column                         PASS
falsifiability section                                       PASS
numeric oracle voltage|remaining ~ 3.6788 +/-0.02            PASS

automated score: 9/9 -> 10.0/10 (PASS; human rubric layer still required)
```

The script exits non-zero on failure, and CI runs it over the whole corpus.

### Reproduce the whole corpus

```bash
ids="$(python -c "import json; print(' '.join(c['id'] for c in json.load(open('benchmarks/ideas.json', encoding='utf-8'))['cases']))")"
for id in $ids; do
  python skills/axiomize/tools/benchmark_runner.py --case "$id" --report "benchmarks/reports/$id.md" || exit 1
done
```

### Result

All 25 cases graded `PASS` at **10.0/10** on the automated layer, every one exiting 0.

| Case | `expected_archetype` | Lenses req. | Lenses found | Numeric oracle | Automated score |
|---|---|---|---|---|---|
| epidemic-threshold | SIR | 2 | 4 | no | 10.0/10 |
| barista-staffing | M/M/c queueing | 2 | 4 | no | 10.0/10 |
| app-adoption-ceiling | Bass diffusion / logistic | 2 | 4 | no | 10.0/10 |
| duopoly-price-cut | Bertrand duopoly | 1 | 5 | no | 10.0/10 |
| reserve-ruin | compound Poisson / ruin theory | 2 | 4 | no | 10.0/10 |
| greenhouse-setpoint | feedback control / Newton cooling | 2 | 4 | no | 10.0/10 |
| school-rumor-reach | rumor dynamics on networks | 2 | 4 | no | 10.0/10 |
| ad-lift-causal | causal identification | 2 | 4 | no | 10.0/10 |
| physics-pendulum-drift | damped harmonic oscillator | 2 | 2 | yes | 10.0/10 |
| chemistry-batch-yield | batch reactor kinetics | 2 | 2 | yes | 10.0/10 |
| biology-predator-prey | Lotka-Volterra predator-prey | 2 | 2 | no | 10.0/10 |
| physics-heat-conduction | steady-state heat conduction | 2 | 2 | yes | 10.0/10 |
| operations-inventory | EOQ inventory optimization | 2 | 2 | no | 10.0/10 |
| chemistry-equilibrium | chemical equilibrium | 2 | 2 | yes | 10.0/10 |
| causal-confounding | confounding bias | 2 | 2 | no | 10.0/10 |
| physics-oscillator-ringdown | damped harmonic oscillator | 2 | 2 | yes | 10.0/10 |
| biology-drug-dosing | one-compartment pharmacokinetics | 2 | 2 | no | 10.0/10 |
| chemistry-catalyst-deactivation | catalyst deactivation kinetics | 2 | 2 | no | 10.0/10 |
| operations-airline-overbooking | binomial overbooking / newsvendor | 2 | 2 | yes | 10.0/10 |
| causal-training-productivity | program evaluation under selection bias | 2 | 2 | no | 10.0/10 |
| physics-rc-discharge | exponential RC discharge | 1 | 2 | yes | 10.0/10 |
| biology-doubling-culture | exponential bacterial growth | 1 | 3 | yes | 10.0/10 |
| chemistry-first-order-half-life | first-order chemical half-life | 1 | 3 | yes | 10.0/10 |
| operations-mm1-wait | M/M/1 queue | 1 | 3 | yes | 10.0/10 |
| causal-randomized-ate | randomized average treatment effect | 1 | 3 | yes | 10.0/10 |

12 of the 25 cases carry a `numeric_oracle`, so their headline number is checked against a
closed-form value within a stated tolerance rather than only checked for presence.

### What 10.0/10 does and does not mean

This is the part that matters, so read it before quoting the number.

The automated layer checks **contract compliance**:

- `must_contain` — one literal alternative from each list appears verbatim, case-insensitively
- `expected_archetype` — the archetype tokens appear
- lens count — at least `min_lenses_built` perspective subsections
- parameter table has a non-empty `Unit` column with at least one `exo` or `endo` row
- assumptions have a `Violation consequence` column
- a falsification section exists
- a numeric oracle value matches `expected` within `tolerance`

It does **not** check whether the model is scientifically correct. A structurally perfect
report built on a wrong model still scores 10.0/10. So:

- **Do** read 10.0/10 as "these stored reports satisfy the published report contract, and
  their headline number still agrees with closed-form theory within the stated tolerance".
- **Do not** read it as "the engine solves these problems".

The [rubric](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/benchmarks/rubric.md)
defines a human layer on top (symbol discipline, units, assumption honesty, comparison
honesty, plain-language opener; 0-2 each, combined to /20). **No human-layer scores are
recorded for these 25 cases.** Until they are, there is no human-verified quality number
to quote from this corpus, and this page does not invent one.

### Where the stored reports came from

They are **maintainer-authored worked reports** committed to the repository, written to the
report contract and re-graded in CI. They are not agent transcripts, and no claim is made
here that they were produced by independent or blind agents. The 8-phase structure and the
17 illustrative reports under `examples/` are related but separate artifacts; the graded
corpus is the 25 cases listed above.

---

## 2. Offline reasoning sweeps

These are deterministic experiments on synthetic episodes with known ground truth. No LLM
calls, no network. They calibrate two defaults in `axiomize.reasoning`.

### Branch-controller ablation

Report: [`benchmarks/reports/reasoning-ablation.md`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/benchmarks/reports/reasoning-ablation.md)

```bash
python -m axiomize.reasoning.ablation --seed 20260927 --mode sweep
```

Seed `20260927`, 400 episodes per cell, 8-round deadline. Policies compared: `argmax_commit`
(the trap — commits to the round-1 leader), `beam_top2` (keeps the top 2, no thresholds, no
revival), and the real `branch_controller`.

On the easy regime the three score 0.965 / 1.000 / 1.000 accuracy, but `argmax_commit`
converges in 1 round at 4 branch-cost while the controller uses 25.5 with 23 revivals — the
point of the experiment is the hard and regime-shift cells, where the controller holds
accuracy that the greedy baseline loses, not the easy cell. Per-cell numbers are in the
report; re-running the command above reproduces them from the seed.

### Collapse-threshold sweep

Report: [`benchmarks/reports/reasoning-threshold-sweep.md`](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/benchmarks/reports/reasoning-threshold-sweep.md)

```bash
python -m axiomize.reasoning.ablation --seed 20260927 --mode sweep
```

Same seed and episodes for every threshold, so the comparison is paired. This is the
evidence for `collapse_score` defaulting to 0.65 rather than the previous 0.78:

| collapse_score | easy-regime collapse rate | easy mean rounds | hard-regime premature-wrong |
|---|---|---|---|
| 0.60 | 0.990 | 5.30 | 0.000 |
| **0.65** | **0.950** | **5.85** | **0.000** |
| 0.78 (old default) | 0.000 | 8.00 | 0.000 |

The old 0.78 default never fired under bounded noisy evidence: accuracy was identical but
collapse rate was 0, so the engine always ran to the deadline. 0.65 collapses early in
clear regimes with zero premature-wrong collapses. Regenerating the report from the seed
reproduces these values.

**Honest caveat:** these are synthetic episodes written by the same author as the code being
calibrated, with ground truth known by construction. They demonstrate that the controller
logic implements its intended policy. They are not evidence that the policy helps on
real-world problems with unknown ground truth.

---

## 3. Install-safe benchmark suite

A separate, faster suite that ships with the package and checks the installed engine:

```bash
axiomize benchmark
```

```json
{"status": "PASS", "passed": 12, "total": 12}
```

12 of 12 cases pass on CPython 3.12.10 with numpy 2.5.3 / scipy 1.18.1 at commit
`eb70a47`. Cases include a deterministic model, a nonlinear ODE, an optimization problem and
a regression fit.

## 4. Numerical cross-checks in the test suite

Independently of the reports, the test suite checks numeric results against external
references rather than against itself:

- causal estimators against **statsmodels** OLS and Logit — front-door point estimates, HC1
  standard errors, and binary AIPW (`tests/test_numerical_reference.py`)
- Bayesian `exponential` and `student_t` log-likelihoods against **scipy.stats**
  (`tests/test_bayesian_likelihoods.py`)
- numeric verification against closed-form theory results across model families
  (`tests/test_numerical_reference.py`, `tests/test_numerical_verification.py`)

Run them with:

```bash
pytest tests/test_numerical_reference.py tests/test_bayesian_likelihoods.py -q
```

Verified `40 passed` at commit `eb70a47` on CPython 3.12.10.

---

## 5. Historical audit notes

Earlier revisions of this page carried per-wave scores (for example a "suite average
9.21/10") attributed to blind-test sessions by independent agents. Those figures are gone:
no session transcripts were retained, so the numbers cannot be reproduced or checked, and
several were mis-stated in place. What survives from that review is recorded in
[CHANGELOG.md](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/CHANGELOG.md)
as concrete fixes that are visible in the code and covered by tests — bounding work, hard
resource ceilings, AST-restricted expression parsing, removal of `eval` paths, platform
wheel smokes. Fixes you can see in a diff are evidence; scores you cannot recompute are
not.

If you re-run the corpus and get different numbers than the table above, please open an
issue with the output — that discrepancy would be a real finding.