# Axiomize Quantum Skills 2.0

A scientific modeling engine with explicit units, dimensional and numerical validation,
calibration and uncertainty analysis — plus a reasoning protocol that refuses to commit to
the first plausible answer.

Two pieces ship together:

| Piece | What it is |
|---|---|
| **Axiomize** | Versioned Model IR; algebraic, ODE, stochastic, PDE, optimization, control, network, Bayesian and causal execution; dimensional checks; fit; sensitivity; uncertainty; portable export |
| **Quantum Reasoning** | A protocol and deterministic branch controller that keeps several hypotheses alive, scores them against evidence, prunes weak ones, and collapses only when the evidence supports it |

Use it when both the **mathematical formulation** and the **reasoning path** matter: model
selection, parameter estimation, sensitivity analysis, uncertainty quantification, Bayesian
and causal reasoning, hypothesis comparison, and reproducible scientific workflows.

"Quantum" here is a metaphor for deferring commitment. It runs on classical models and
classical hardware.

## See it work

The reference SIR model, animated. beta = 0.3, gamma = 0.1, so R0 = 3.0.

![Animated SIR epidemic curve, R0=3.0](sir-demo.gif)

The static plot below is the same parameter run at full resolution, peak annotated:

![SIR beta=0.3 gamma=0.1 R0=3.00, peak 300,465 at day 61](sir-example.png)

The plot is written by the `--plot` flag of the `axiomize-validate` console script, not by
`axiomize validate` (which emits JSON and writes no file):

```bash
axiomize-validate --model sir --beta 0.3 --gamma 0.1 --N 1000000 --plot sir.png
```

```text
Peak infected          = 300,465 at day 61.4
plot saved -> sir.png
```

Re-running with those parameters reproduces the same curve and the same peak annotation.
The committed PNG is a snapshot, so its bytes are not expected to match a fresh run exactly:
Matplotlib's PNG output varies by version.

A sample of the LaTeX report the engine converts a finished analysis into:
[report-sample.pdf](report-sample.pdf) (source: [report-sample.tex](report-sample.tex)).

## Quick start

```bash
pip install axiomize-quantum-skills-2.0
```

Python 3.10+. Then:

```bash
axiomize tools        # which scientific backends are really installed
axiomize benchmark    # install-safe self-test
axiomize validate --N 1000000
```

Verified at version 1.2.0, commit `9c2990c`, CPython 3.12.10:

```json
{"status": "PASS", "passed": 12, "total": 12, ...}
```

```json
{"status": "PASS", "cross_validation": {"status": "PASS", ...},
 "numeric_theory_check": {"status": "INCONCLUSIVE", ...}}
```

The `INCONCLUSIVE` is intentional: the closed-form final-size formula has not converged at
that horizon, and the engine says so instead of reporting a pass it has not earned.

Full walkthrough: [tutorial.md](tutorial.md).

## What ships

- **15 mathematical perspectives** under `skills/axiomize/perspectives/`, plus archetype
  and first-principles routing.
- **Two agent skills** as plain Markdown: `skills/axiomize/` (modeling) and
  `skills/quantum-reasoning/` (branch management). Install them without the Python package.
- **18 worked examples** in `examples/`.
- **Three interfaces** over one core: CLI (`axiomize`, 14 subcommands), MCP over stdio
  (34 tools), and a loopback-by-default REST API (v1).
- **A 25-case closed-form benchmark corpus** graded in CI, with reproducible provenance in
  [benchmark-results.md](benchmark-results.md).

## Honest limits

- The engine does not choose your model. `axiomize model --action plan` ranks candidate
  families and then returns `NEEDS_MODEL_IR`.
- Optional backends (`pymc`, `jax`, FEniCS/DOLFINx) report `UNAVAILABLE` unless genuinely
  installed. Use `pip install axiomize-quantum-skills-2.0[full]` for `pymc` and `jax`.
- Benchmark scores measure report-contract compliance, not scientific correctness. The
  human rubric layer is defined but unscored.
- Arbitrary code and theorem elaboration are not an OS sandbox. See
  [security.md](security.md).
- The npm package is a thin Node launcher shim (6 files, about 44 kB) that spawns the
  Python CLI; it is not a second implementation, so the Python package must be installed
  and on `PATH`. PyPI and npm are both on `1.2.1` and both are attested.

## Links

| | |
|---|---|
| Repository | <https://github.com/Furox-Art/axiomize-quantum-skills-2.0> |
| PyPI | <https://pypi.org/project/axiomize-quantum-skills-2.0/> |
| Documentation | <https://furox-art.github.io/axiomize-quantum-skills-2.0/> |
| Tutorial | [tutorial.md](tutorial.md) |
| Example gallery | [example-gallery.md](example-gallery.md) |
| Benchmark results | [benchmark-results.md](benchmark-results.md) |
| Integrations | [integrations.md](integrations.md) |
| Security | [security.md](security.md) · [SECURITY.md on GitHub](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/SECURITY.md) |
| Contributing | <https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/CONTRIBUTING.md> |
| Code of Conduct | <https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/CODE_OF_CONDUCT.md> |
| Changelog | <https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/CHANGELOG.md> |
| Citation | <https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/CITATION.cff> |
| License | MIT |