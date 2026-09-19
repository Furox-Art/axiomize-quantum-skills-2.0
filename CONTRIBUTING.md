# Contributing to Axiomize

Thanks for helping make idea-to-model rigor a standard agent capability.

## Adding a perspective (the most valuable PRs)

Each file in `skills/axiomize/perspectives/` follows a fixed contract. A new lens PR must include **all** sections:

```
# Perspective: <Name> (<one-line essence>)

## When Applicable
- Explicit triggers tied to the Phase 2 classifications (flow / interaction / decision / uncertainty)
- What questions this lens answers that others cannot

## Model Forms
- The 2-4 canonical formalisms, with checklists for building them correctly
- Concrete functional forms (not "model it appropriately")

## Standard Analysis Output
- Numbered list of artifacts every analysis must produce

## Strengths / Blind Spots
- (+) what this view uniquely sees
- (-) what this view cannot see (honesty is the product)
```

Rules for perspective content:

1. Every equation symbol must be defined inline.
2. Units are mandatory where dimensional.
3. Include an "analysis ladder" (cheap → expensive methods) if more than one fidelity level exists.
4. No filler prose, a domain expert should be able to build a first model from your file alone.

Candidate lenses not yet covered: queueing networks beyond M/M/c, survival analysis with competing risks beyond reliability scope.

## Adding worked examples (`examples/`)

Follow the 8-phase structure exactly as in `examples/epidemic-sir.md`. Requirements:

- Real-ish parameter ranges with source classes (`lit.` / `data` / `est.`)
- At least two perspectives actually built, plus at least one **explicitly rejected with a one-line reason**
- A falsifiability section naming observations that would kill the model
- If you add runnable tooling, extend `skills/axiomize/tools/validate.py` (see below)

## Extending `skills/axiomize/tools/validate.py`

Every new model mode must print sanity checks and exit non-zero when they fail. Accepted checks: conservation laws, bounds/monotonicity, agreement with a closed-form theory result (within stated tolerance), or distributional consistency across Monte Carlo runs. CI runs all modes, keep default parameters under ~60s total runtime.

## Adding benchmark cases and reports

Add a case to `benchmarks/ideas.json` with a unique `id`, its `idea`,
`must_contain` terms, `expected_archetype`, and the required `min_lenses_built`
and `must_reject_at_least_one` settings. Add the matching report at
`benchmarks/reports/<id>.md`; CI grades every case against that exact path, so a
missing report fails with `benchmark report not found`.

List the available case IDs and grade one report locally with the same commands
used by CI:

```bash
python skills/axiomize/tools/benchmark_runner.py --case-list
python skills/axiomize/tools/benchmark_runner.py --case biology-predator-prey --report benchmarks/reports/biology-predator-prey.md
```

The report should include the case's required terms and archetype, a parameter
table with a non-empty `Unit` column and `exo`/`endo` classifications, a
`Violation consequence` column, a `## 4. Perspective models` section with at
least the case's `min_lenses_built` lens subsections, and a falsifiability
section. When `must_reject_at_least_one` is true, include a rejected lens and
the reason. The automated checks pass at **7.5/10 or higher**; this is only the
automated layer, and the human rubric still applies.

Two easy-to-miss details: spell archetype names with the exact ASCII hyphen
when specified (for example, `Lotka-Volterra`, not `Lotka–Volterra`), and
commit the matching report file for every case or CI fails. `must_contain` and
numeric-oracle `keyword` strings can use `|` to specify alternatives; each
alternative is matched literally.

## Style

- Markdown for docs; Python 3.9+ stdlib + numpy/scipy only.
- No comments in code unless explaining a non-obvious formula's origin.
- English for repo content.

## Submitting

1. Fork & branch (`feat/<topic>`).
2. Run all validate modes locally before the PR.
3. Describe what lens/example adds to coverage that no existing file provides.
