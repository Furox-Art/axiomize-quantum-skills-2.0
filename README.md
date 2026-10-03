# Axiomize Quantum Skills — 2.0

This is not a separate product. It ships [axiomize](https://github.com/Furox-Art/axiomize) and [quantum-reasoning-skill](https://github.com/Furox-Art/quantum-reasoning-skill) together. Install those repositories when you need only one of them. This repository is not a second MCP registration.

Current package line: **1.2.1**

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/python-3.10%2B-blue)
![CI](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/actions/workflows/ci.yml/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/axiomize-quantum-skills-2.0)](https://pypi.org/project/axiomize-quantum-skills-2.0/)
[![npm](https://img.shields.io/npm/v/axiomize-quantum-skills-2.0)](https://www.npmjs.com/package/axiomize-quantum-skills-2.0)
[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://furox-art.github.io/axiomize-quantum-skills-2.0/)

Download numbers live on the package pages themselves, where they are always current:
[PyPI](https://pypi.org/project/axiomize-quantum-skills-2.0/) ·
[npm](https://www.npmjs.com/package/axiomize-quantum-skills-2.0)

**PyPI and npm are both on `1.2.0`.** The npm package is a **thin Node launcher shim**, not
the engine: six files, about 44 kB, one job — spawn the Python CLI. So install the Python
package first. It is published over OIDC trusted publishing and carries Sigstore and SLSA v1
provenance attestations; details and a verification recipe are in
[docs/publishing-checklist.md](docs/publishing-checklist.md#supply-chain).

**Documentation:** <https://furox-art.github.io/axiomize-quantum-skills-2.0/>

A scientific modeling engine with explicit units, dimensional and numerical validation,
calibration and uncertainty analysis — plus a reasoning protocol that refuses to commit to the
first plausible answer.

| Piece | What it is | Where |
|---|---|---|
| **Axiomize** | Deterministic engine: versioned Model IR; algebraic, ODE, stochastic, PDE, optimization, control, network, Bayesian and causal execution; dimensional checks; fit; sensitivity; uncertainty; portable export | `src/axiomize/`, CLI `axiomize` |
| **Quantum Reasoning** | A protocol and deterministic branch controller that keeps several hypotheses alive, scores them against evidence, prunes weak ones, and collapses only when the evidence supports it | `src/axiomize/reasoning/`, CLI `axiomize-reason` |

"Quantum" here is a metaphor for deferring commitment, not quantum computation. It runs on
classical models and classical hardware.

## See it work

The reference SIR model, animated. beta = 0.3, gamma = 0.1, so R0 = 3.0.

![Animated SIR epidemic curve, R0=3.0](docs/sir-demo.gif)

The plotted curve comes from the `axiomize-validate --plot` flag shown in step 3. The
static snapshot at full resolution, and the LaTeX sample it converts to, are in
[docs/index.md](docs/index.md#see-it-work).

## Quick start (verified against 1.2.0)

### Install

`pip install axiomize-quantum-skills-2.0`. Python 3.10+. NumPy, SciPy, SymPy, NetworkX,
statsmodels, Matplotlib, Control, CVXPY, CasADi and z3-solver come along automatically.

### 1. See what is actually installed

`axiomize tools` reports only backends that genuinely imported:

```text
sympy        1.14.0     available
scipy        1.18.1     available
statsmodels  0.15.0     available
cvxpy        1.9.3      available
jax          unknown    UNAVAILABLE (No module named 'jax')
lean         Lean (version 4.30.0, x86_64-w64-windows-gnu, ...) available
pymc                    UNAVAILABLE (pymc not installed)
fenics                  UNAVAILABLE (fenics not installed)
```

The full list has 13 entries. `axiomize capabilities` is the machine-readable equivalent and
leads with `"axiomize_version": "1.2.0"`.

### 2. Run the install-safe benchmark suite

`axiomize benchmark` → `{"status": "PASS", "passed": 12, "total": 12}`.

### 3. Validate a model, and plot it

```bash
axiomize-validate --model sir --beta 0.3 --gamma 0.1 --N 1000000 --plot sir.png
```

```text
=== SIR validation ===
horizon                = 180 days  (final-size theory is the t->infinity limit)
R0                     = 3.000  (outbreak)
Peak infected          = 300,465 at day 61.4
Final size (simulated) = 0.9404
Final size (theory)    = 0.9405
Theory match           = True

--- sanity checks ---
population_conserved                PASS
compartments_nonnegative            PASS
R_monotonic_increase                PASS

plot saved -> sir.png
```

`axiomize-validate` also takes `--model gillespie` (extinction risk) and `--model queue`
(Erlang-C staffing cliff), plus `--sweep` and `--seed`. The `--plot` flag is what writes a
PNG; `axiomize validate --N 1000000` emits JSON only and writes no file. That JSON form
cross-checks two independent methods (`cross_validation` PASS, agreeing to 1e-16) then
declares `numeric_theory_check` **INCONCLUSIVE**, because the finite horizon has not reached
the asymptotic SIR state — see
[docs/tutorial.md](docs/tutorial.md#a4-ask-the-engine-to-validate-something) for it in full.

### 4. Work with your own model

```bash
axiomize model --input-json docs/quickstart-model-ir.json --action validate
```

`docs/quickstart-model-ir.json` is a complete, copy-pasteable request. To start from a
plain-language idea instead, `axiomize intake "<your idea>"` asks clarifying questions and
recommends a depth. Note `axiomize model` requires `--input-json` and has no `--idea` flag.

### 5. Score a reasoning branch

`axiomize-reason score --evidence 0.9 --verification 0.85` →
`{"branch": "branch-1", "can_collapse": false, "reason": "leader score below collapse threshold"}`
— it declines to collapse, which is correct: a branch needs verification and margin, not just
high evidence. The other two subcommands are `select` (rank model candidates from a
`{"candidates": [...]}` file) and `width` (an uncertainty band from a list of scores).

Every command above was run against `axiomize-quantum-skills-2.0` 1.2.0 at commit `9c2990c`
on CPython 3.12.10 (Windows). [docs/tutorial.md](docs/tutorial.md) is the full walkthrough
with real output for each step.

## Interfaces

| Interface | Entry point |
|---|---|
| Main CLI | `axiomize` — 14 subcommands: `intake`, `policy`, `model`, `clean-data`, `compare-runs`, `solve`, `fit`, `validate`, `tools`, `capabilities`, `reproduce`, `benchmark`, `serve`, `mcp` |
| Validation and data tools | `axiomize-validate` (reference model sanity checks, `--sweep`, `--plot`), `axiomize-fit` (calibrate to a CSV, `--selftest`, `--compare`, `--plot`), `axiomize-csv-check` (data-quality pre-check before fitting) |
| Benchmarks and reports | `axiomize-benchmark` (grade a report against a case), `axiomize-to-latex` (report → LaTeX/PDF), `axiomize-index-reports` (build a report index) |
| Parallel execution | `axiomize-sweep` (`--job sweep` or `--job mc`) — the skill's subagent-dispatch pattern applied to parameter grids |
| Reasoning | `axiomize-reason` — `score`, `select`, `width` |
| MCP (stdio) | `axiomize mcp` — 34 tools; host config `{"command": "axiomize", "args": ["mcp"]}` |
| REST (v1) | `axiomize serve` — loopback-only unless `--allow-remote` with a bearer token |

All of them call the same core services, so validation behaviour never depends on the
caller. [docs/integrations.md](docs/integrations.md) has every subcommand, MCP tool and
REST route.

The agent skills are plain Markdown protocols and install without the Python package:

```bash
git clone https://github.com/Furox-Art/axiomize-quantum-skills-2.0
cp -r axiomize-quantum-skills-2.0/skills/axiomize          ~/.config/opencode/skills/
cp -r axiomize-quantum-skills-2.0/skills/quantum-reasoning ~/.config/opencode/skills/
```

## What you get

- **15 mathematical perspectives** under `skills/axiomize/perspectives/`, plus archetype and
  first-principles routing, and **5 report templates** in
  [`skills/axiomize/templates/`](skills/axiomize/templates/) — the 10-section
  [report](skills/axiomize/templates/report.md), parameters, assumptions, glossary, subagent brief.
- **13 domain packs** in [`packs/`](packs/): curated bundles of which archetypes, lenses and
  examples matter in a given domain — epidemiology, operations, economics, ecology, project
  management, physics, chemistry, biology, climate, engineering, finance, probability, plus the
  [index](packs/domain-packs.md).
- **18 worked examples** in [`examples/`](examples/), indexed by
  [docs/example-gallery.md](docs/example-gallery.md).
- **A 25-case closed-form benchmark corpus** with stored reports, graded in CI, plus a 6-case
  reasoning corpus with 4 JSON schemas under `src/axiomize/reasoning/benchmark/`
  (`evaluate.py`, `validate_submission.py`).
- **Versioned portable runs**: `axiomize.portable-bundle.v1` exports and run bundles carry a
  canonical Model IR SHA-256, so a run can be zipped, moved and re-inspected elsewhere. See
  [docs/portable-export.md](docs/portable-export.md).
- **Optional backends**, reported honestly by `axiomize tools`: a real **Lean 4** proof checker
  (`formal/lean_adapter.py`) and an **OpenAI-compatible provider layer** (`providers/`) for
  model-backed steps, both behind the consumption guard in `axiomize policy`.
- **Explicit honesty rules**: rejected lenses must carry a reason, every quantity carries a
  unit, and every model states what observation would falsify it.

## Benchmarks

The 25-case corpus is graded in CI by `skills/axiomize/tools/benchmark_runner.py`
(also `axiomize-benchmark`). Re-graded at commit `9c2990c`, axiomize 1.2.0, CPython 3.12.10
(Windows), numpy 2.5.3 / scipy 1.18.1:

```bash
python skills/axiomize/tools/benchmark_runner.py --case physics-rc-discharge --report benchmarks/reports/physics-rc-discharge.md
```

```text
automated score: 9/9 -> 10.0/10 (PASS; human rubric layer still required)
```

All 25 cases pass at 10.0/10, each against its own check count (8 to 11). **This is a
contract-compliance measurement, not a measure of modeling quality**: the automated layer
checks structure — literal alternative lists present, lens count, unit column,
violation-consequence column, falsifiability section, numeric oracle within tolerance. A
structurally perfect report about a wrong model still scores 10.0/10. The human rubric layer
in [benchmarks/rubric.md](benchmarks/rubric.md) is not recorded for these cases; see
[docs/benchmark-results.md](docs/benchmark-results.md) for the provenance-stamped run.

## Honest limits

- The engine does not choose a model for you. `axiomize model --action plan` ranks
  candidate families and then returns `NEEDS_MODEL_IR`; deterministic execution starts
  only after you supply an explicit Model IR.
- Optional backends (`pymc`, `jax`, FEniCS/DOLFINx) are reported `UNAVAILABLE` unless
  actually installed. The `[full]` extra installs `pymc` and `jax` only — FEniCS/DOLFINx
  has no pip extra and must be installed separately. `[playground]` adds `gradio` and
  `pandas`.
- Arbitrary code and theorem elaboration are **not** an OS sandbox. They require explicit
  trust. See [SECURITY.md](SECURITY.md) and [docs/security.md](docs/security.md).
- **The npm package is a launcher shim, not a second implementation.** It is 6 files and
  about 44 kB, and it does one thing: spawn the Python CLI. If the Python package is not
  installed, `npx axiomize-quantum` exits `127` with a message telling you to install it.
  There is no JavaScript engine here; use the `axiomize` console script or `python -m
  axiomize.cli` directly if you do not want the extra hop.
- npm also still holds `2.0.0`, published before the launcher fix, whose `index.js` is the
  old syntactically invalid one. It is **not** the `latest` dist-tag any more, so a plain
  `npm install axiomize-quantum-skills-2.0` resolves to `1.2.0`. If you have pinned or
  installed `2.0.0`, upgrade.

## Documentation

The published site carries 20 pages; the `mkdocs.yml` nav is the source of truth.

| Group | Pages |
|---|---|
| Home | [index](docs/index.md) |
| Workflow | [workflow](docs/index.md) · [adaptive](docs/adaptive-workflow.md) · [rigor](docs/rigor.md) · [archetypes](docs/archetypes.md) |
| Guides | [tutorial](docs/tutorial.md) · [worked examples](docs/worked-examples.md) · [example gallery](docs/example-gallery.md) · [integrations](docs/integrations.md) · [portable export](docs/portable-export.md) |
| Reference | [benchmark results](docs/benchmark-results.md) |
| Security | [overview](docs/security.md) · [versioning](docs/security-versioning.md) · [CI contract](docs/security-ci-contract.md) · [release checklist](docs/security-release-checklist.md) · [maintenance](docs/security-maintenance.md) · [non-goals](docs/security-non-goals.md) · [1.11.2 audit](docs/security-audit-1.11.2.md) |
| Publishing | [publishing checklist](docs/publishing-checklist.md) |

The workflow, rigor and archetypes pages are staged into `docs/` from `skills/axiomize/` at
build time; their repository paths are `skills/axiomize/{SKILL,adaptive-workflow,rigor,archetypes}.md`.

## Contributing, citing, licence

[CONTRIBUTING.md](CONTRIBUTING.md) has the perspective and example contracts;
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) governs participation; [SECURITY.md](SECURITY.md)
takes vulnerability reports. Cite via [CITATION.cff](CITATION.cff); release history is in
[CHANGELOG.md](CHANGELOG.md). MIT — [LICENSE](LICENSE), Copyright (c) 2026 Furkan.