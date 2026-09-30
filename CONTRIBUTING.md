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

## Benchmark reports (`benchmarks/`)

The CI gate grades **every** case in `benchmarks/ideas.json` against a stored report in
`benchmarks/reports/<id>.md`. There are two halves to keeping it green.

### 1. Add the case

Append an object to the `cases` array in `benchmarks/ideas.json`:

```json
{
  "id": "physics-rc-discharge",
  "prompt": "Model this idea mathematically: ...",
  "must_contain": ["exponential|RC|time constant", "e\\^|exp\\(|1/e", "voltage"],
  "expected_archetype": "exponential RC discharge",
  "min_lenses_built": 1,
  "must_reject_at_least_one": false,
  "numeric_oracle": { "keyword": "voltage|remaining", "expected": 3.6788, "tolerance": 0.02 }
}
```

`id` must be unique and must be a valid filename stem. See the schema notes in
`benchmarks/rubric.md` for the human rubric layer that sits on top of this automated one.

### 2. Write the matching report

Create `benchmarks/reports/<id>.md` in the standard 8-phase structure (see
`examples/epidemic-sir.md`). The grader checks these mechanically:

| Check | Requirement |
|---|---|
| `must_contain` | each entry is a **literal alternative list**; the report needs one of them verbatim (case-insensitive) |
| `expected_archetype` | matched token-by-token with word boundaries, so **ASCII hyphens matter** |
| `min_lenses_built` | at least N built lenses under the perspective-models section |
| `must_reject_at_least_one` | a `Rejected lens: <reason>` line must be present |
| parameters | a table with a `Unit` column and at least one row marked `exo` or `endo` |
| assumptions | a `Violation consequence` column |
| falsifiability | a `Falsifiability` section |
| `numeric_oracle` | a number matching `expected` within `tolerance` |

### 3. Grade it locally

```bash
python skills/axiomize/tools/benchmark_runner.py --case-list
python skills/axiomize/tools/benchmark_runner.py --case physics-rc-discharge --report benchmarks/reports/physics-rc-discharge.md
```

Pass threshold is **score >= 7.5/10** (7.5 means 8 of 10 automated checks). Reproduce the
whole CI loop with:

```bash
ids="$(python -c "import json; print(' '.join(c['id'] for c in json.load(open('benchmarks/ideas.json', encoding='utf-8'))['cases']))")"
for id in $ids; do
  python skills/axiomize/tools/benchmark_runner.py --case "$id" --report "benchmarks/reports/$id.md" || exit 1
done
```

### Two gotchas that cost real debugging time

1. **A missing report file fails CI immediately** with `benchmark report not found: <path>`
   and exit code 1. Adding a case without its report is the single most common way to turn
   `main` red.
2. **The numeric oracle reads the *first* number after the keyword.** `numeric_oracle.keyword`
   is matched case-insensitively and without word boundaries, so it can fire on a substring
   inside an unrelated word (`Date` contains `ate`), and the first digit run within 128
   characters after that match is the candidate. Put the graded quantity immediately after
   the keyword, and make sure no earlier line already contains the keyword. Same trap for
   `must_contain` and `expected_archetype`: they see the whole document, so term order in
   the file changes what gets matched.

## Release scripts and the distribution name

The distribution is declared once, in `pyproject.toml` under `[project] name`
(currently `axiomize-quantum-skills-2.0`), and the import package is `axiomize`. Those two
names are not interchangeable:

- `importlib.metadata.version("<distribution name>")` must use the **distribution** name.
- A wheel **filename** escapes it: `-` and `.` both become `_`, so the artifact is
  `axiomize_quantum_skills_2_0-<version>-py3-none-any.whl` (PEP 427 / setuptools escaping),
  never `axiomize-*.whl`.

Getting this wrong fails every platform smoke job at once with `PackageNotFoundError`, or
silently globs zero wheels. `tests/test_ci_distribution_name_guard.py` enforces both rules
against every `.github/scripts/*.py`; if you touch those scripts, run it:

```bash
python -m pytest tests/test_ci_distribution_name_guard.py -q
```

## Style

- Markdown for docs; Python 3.9+ stdlib + numpy/scipy only.
- No comments in code unless explaining a non-obvious formula's origin.
- English for repo content.

## Submitting

1. Fork & branch (`feat/<topic>`).
2. Run all validate modes locally before the PR.
3. Describe what lens/example adds to coverage that no existing file provides.
