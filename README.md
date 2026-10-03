# Axiomize Quantum Skills - 2.0

This is not a separate product. It ships [axiomize](https://github.com/Furox-Art/axiomize) and [quantum-reasoning-skill](https://github.com/Furox-Art/quantum-reasoning-skill) together. Install those repositories when you need only one of them. This repository is not a second MCP registration.

Current package line: **1.2.0**

![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/python-3.10%2B-blue)
![CI](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/actions/workflows/ci.yml/badge.svg)
[![PyPI](https://img.shields.io/pypi/v/axiomize-quantum-skills-2.0)](https://pypi.org/project/axiomize-quantum-skills-2.0/)
[![npm](https://img.shields.io/npm/v/axiomize-quantum-skills-2.0)](https://www.npmjs.com/package/axiomize-quantum-skills-2.0)
[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://furox-art.github.io/axiomize-quantum-skills-2.0/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Download numbers live on the package pages themselves, where they are always current:
[PyPI](https://pypi.org/project/axiomize-quantum-skills-2.0/) ·
[npm](https://www.npmjs.com/package/axiomize-quantum-skills-2.0)

**PyPI and npm are both on `1.2.0`.** Verified against the live registries: PyPI
`info.version` is `1.2.0` and the npm `latest` dist-tag is `1.2.0`.

The npm package is a **thin Node launcher shim, not the engine**. It contains six files
and about 44 kB and does one thing: spawn the Python CLI. So the Python package has to be
installed and on `PATH` for `npx axiomize-quantum` to do anything useful:

```bash
pip install axiomize-quantum-skills-2.0
npx axiomize-quantum --help
```

Supply chain: the `1.2.0` npm tarball was published over OIDC trusted publishing and
carries two Sigstore attestations — an npm publish attestation and a
[SLSA v1 provenance](https://slsa.dev/provenance/v1) statement. In that statement
`runDetails.builder.id` is the identifier `https://github.com/actions/runner/github-hosted`
(a SLSA builder ID, not a page to open), `internalParameters.github.event_name` is
`workflow_dispatch`, and `resolvedDependencies` pins this repository and
`.github/workflows/npm-publish.yml`. The tarball's SHA-512 was recomputed and matches both
the registry `integrity` field and the digest inside those attestations.
`npm install axiomize-quantum-skills-2.0 --provenance` fetches and verifies them. PyPI is
published by trusted publishing too.

**Documentation:** <https://furox-art.github.io/axiomize-quantum-skills-2.0/>

A scientific modeling engine with explicit units, dimensional and numerical validation,
calibration and uncertainty analysis — plus a reasoning protocol that refuses to commit to
the first plausible answer.

Two independent pieces ship together:

| Piece | What it is | Where |
|---|---|---|
| **Axiomize** | Deterministic engine: versioned Model IR, algebraic/ODE/stochastic/PDE/optimization/control/network/Bayesian/causal execution, dimensional checks, fit, sensitivity, uncertainty, portable export | `src/axiomize/`, CLI `axiomize` |
| **Quantum Reasoning** | A protocol and deterministic branch controller for keeping several hypotheses alive, scoring them against evidence, pruning weak ones, and collapsing only when evidence supports it | `src/axiomize/reasoning/`, CLI `axiomize-reason` |

"Quantum" here is a metaphor for deferring commitment, not quantum computation. It runs
on classical models and classical hardware. See
[skills/quantum-reasoning/SKILL.md](skills/quantum-reasoning/SKILL.md).

## See it work

The reference SIR model, animated. beta = 0.3, gamma = 0.1, so R0 = 3.0.

![Animated SIR epidemic curve, R0=3.0](docs/sir-demo.gif)

That curve is produced by the command in step 3 below. Here it is at full resolution, with
the peak annotated:

![SIR beta=0.3 gamma=0.1 R0=3.00, peak 300,465 at day 61](docs/sir-example.png)

A sample of the LaTeX report the engine converts a finished analysis into:
[report-sample.pdf](docs/report-sample.pdf) (source:
[report-sample.tex](docs/report-sample.tex)).

## Quick start (verified against 1.2.0)

### Install

```bash
pip install axiomize-quantum-skills-2.0
```

Requires Python 3.10+. NumPy, SciPy, SymPy, NetworkX, statsmodels, Matplotlib, Control,
CVXPY and CasADi are pulled in automatically; `z3-solver` is included.

### 1. See what is actually installed

Only backends that are genuinely importable are reported as available.

```bash
axiomize tools
```

```text
sympy        1.14.0     available
scipy        1.18.1     available
statsmodels  0.15.0     available
cvxpy        1.9.3      available
casadi       3.8.1      available
jax          unknown    UNAVAILABLE (No module named 'jax')
z3           5.1.0      available
...
```

Machine-readable version of the same thing:

```bash
axiomize capabilities      # -> {"axiomize_version": "1.2.0", ...}
```

### 2. Run the install-safe benchmark suite

```bash
axiomize benchmark
```

```json
{"status": "PASS", "passed": 12, "total": 12, ...}
```

### 3. Validate a model with dimensional and cross-checks

```bash
axiomize validate --N 1000000
```

```json
{
  "status": "PASS",
  "final_size": 0.9404340723379753,
  "asymptotic_final_size": 0.9404805152899381,
  "cross_validation": {"status": "PASS", "difference": 1.1102230246251565e-16},
  "numeric_theory_check": {"status": "INCONCLUSIVE", ...}
}
```

Note the deliberate honesty: cross-validation passes, but the numeric-theory check reports
`INCONCLUSIVE` and says why — the finite horizon has not yet reached the asymptotic SIR
state, so it should not be compared against final-size theory yet.

### 4. Validate your own Model IR

```bash
axiomize model --input-json docs/quickstart-model-ir.json --action validate
```

```json
{"status": "PASS", "model_ir": {"name": "member-churn-decay", "domain": "social", ...}}
```

`docs/quickstart-model-ir.json` is a complete, copy-pasteable request. To design one from
a plain-language idea instead:

```bash
axiomize intake "my gym keeps losing members after 3 months; how do I stop the churn?"
```

```json
{
  "status": "NEEDS_INPUT",
  "questions": [{"field": "system_boundary", "question": "What exactly are we modeling...?"}],
  "rigor_recommendation": {"level": "medium", "reasons": ["default balanced depth"]}
}
```

### 5. Score a reasoning branch

```bash
axiomize-reason score --evidence 0.9 --verification 0.85
```

```json
{"branch": "branch-1", "can_collapse": false, "reason": "leader score below collapse threshold"}
```

Every command shown above was executed against `axiomize-quantum-skills-2.0` 1.2.0 at
commit `338bc9e` on CPython 3.12.10 (Windows). The walkthrough continues in
[docs/tutorial.md](docs/tutorial.md).

## Interfaces

All three call the same core services, so validation behaviour never depends on the caller.

| Interface | Entry point |
|---|---|
| CLI | `axiomize` (14 subcommands: `intake`, `policy`, `model`, `clean-data`, `compare-runs`, `solve`, `fit`, `validate`, `tools`, `capabilities`, `reproduce`, `benchmark`, `serve`, `mcp`) |
| MCP (stdio) | `axiomize mcp` — 34 tools; see [docs/integrations.md](docs/integrations.md) |
| REST (v1) | `axiomize serve` — loopback-only by default; see [docs/integrations.md](docs/integrations.md) |

MCP host configuration:

```json
{"command": "axiomize", "args": ["mcp"]}
```

REST, verified live:

```bash
axiomize serve --port 8899
curl http://127.0.0.1:8899/capabilities
curl -X POST http://127.0.0.1:8899/solve -H 'content-type: application/json' -d '{"beta":0.3,"gamma":0.1,"N":100000}'
```

Agent skills are shipped as plain Markdown protocols and can be installed independently of
the Python package:

```bash
git clone https://github.com/Furox-Art/axiomize-quantum-skills-2.0
cp -r axiomize-quantum-skills-2.0/skills/axiomize          ~/.config/opencode/skills/
cp -r axiomize-quantum-skills-2.0/skills/quantum-reasoning ~/.config/opencode/skills/
```

## What you get

- 15 mathematical perspectives under `skills/axiomize/perspectives/`, plus archetype and
  first-principles routing.
- 18 worked examples in [`examples/`](examples/), indexed by
  [docs/example-gallery.md](docs/example-gallery.md).
- A 25-case closed-form benchmark corpus with stored reports, graded in CI.
- Explicit honesty rules: rejected lenses must carry a reason, every quantity carries a
  unit, and every model states what observation would falsify it.

## Benchmarks

The 25-case corpus is graded in CI by
`skills/axiomize/tools/benchmark_runner.py`. Result reproduced locally on commit `338bc9e`,
axiomize 1.2.0, CPython 3.12.10 (Windows), numpy 2.5.3 / scipy 1.18.1:

```bash
python skills/axiomize/tools/benchmark_runner.py --case physics-rc-discharge --report benchmarks/reports/physics-rc-discharge.md
```

```text
automated score: 9/9 -> 10.0/10 (PASS; human rubric layer still required)
```

All 25 cases pass the automated layer, 10.0/10 each. **This is a contract-compliance
measurement, not a measure of modeling quality**: the automated layer checks structure
(literal alternative lists present, lens count, unit column, violation-consequence column,
falsifiability section, numeric oracle within tolerance). A structurally perfect report
about a wrong model still scores 10.0/10. The human rubric layer described in
[benchmarks/rubric.md](benchmarks/rubric.md) is not recorded for these cases. See
[docs/benchmark-results.md](docs/benchmark-results.md) for the full, provenance-stamped run.

## Honest limits

- The engine does not choose a model for you. `axiomize model --action plan` ranks
  candidate families and then returns `NEEDS_MODEL_IR`; deterministic execution starts
  only after you supply an explicit Model IR.
- Optional backends (`pymc`, `jax`, FEniCS/DOLFINx) are reported `UNAVAILABLE` unless
  actually installed. Install them with `pip install axiomize-quantum-skills-2.0[full]`.
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

| Page | Contents |
|---|---|
| [Tutorial](docs/tutorial.md) | First session, end to end |
| [Example gallery](docs/example-gallery.md) | All 18 worked examples with provenance |
| [Benchmark results](docs/benchmark-results.md) | Reproducible grading run, with commit |
| [Integrations](docs/integrations.md) | MCP, REST and CLI surfaces |
| [Worked examples](docs/worked-examples.md) | Modeling + reasoning composed (illustrative) |
| [Portable export](docs/portable-export.md) | Versioned, integrity-tagged run bundles |
| [Security](docs/security.md) | Trust boundaries and input surfaces |
| [Publishing checklist](docs/publishing-checklist.md) | Registry/list submission checklist |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the perspective and example contracts, and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Security reports: [SECURITY.md](SECURITY.md).

## Citing

See [CITATION.cff](CITATION.cff). Release history: [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Furkan.