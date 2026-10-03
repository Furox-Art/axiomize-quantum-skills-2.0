# Your First Axiomize Session

A beginner walkthrough. Every command in this page was executed against
`axiomize-quantum-skills-2.0` **1.2.0** at commit `9c2990c` on CPython 3.12.10 (Windows),
with numpy 2.5.3 and scipy 1.18.1. If a command here stops working, that is a documentation
bug worth reporting.

There are two ways in. **Track A** installs the Python engine. **Track B** installs the
Markdown skill for an AI agent. They are independent; many people use both.

---

## Track A: the Python engine

### A1. Install

```bash
pip install axiomize-quantum-skills-2.0
```

Python 3.10 or newer. This pulls in NumPy, SciPy, SymPy, NetworkX, statsmodels,
Matplotlib, Control, CVXPY, CasADi and z3-solver. Optional extras:

```bash
pip install axiomize-quantum-skills-2.0[full]      # adds pymc and jax
pip install axiomize-quantum-skills-2.0[playground] # adds gradio and pandas
```

### A2. Check what actually works on your machine

Optional scientific backends are only reported as available if they really imported.

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
lean         ...        available
networkx     3.7        available
control      0.10.2     available
matplotlib   3.11.2     available
pymc                    UNAVAILABLE (pymc not installed)
fenics                  UNAVAILABLE (fenics not installed)
```

If a backend you need says `UNAVAILABLE`, install its extra. Do not assume it is there.

### A3. Run the self-test

```bash
axiomize benchmark
```

```json
{"status": "PASS", "passed": 12, "total": 12, ...}
```

Twelve install-safe scientific cases (deterministic model, nonlinear ODE, optimization,
regression, and so on). All twelve pass. Every case exits non-zero if a sanity check
fails, so this is a real gate, not a smoke test that always says OK.

### A4. Ask the engine to validate something

The backward-compatible reference model is SIR. This one is fully specified:

```bash
axiomize validate --N 1000000
```

```json
{
  "status": "PASS",
  "final_size": 0.9404340723379753,
  "asymptotic_final_size": 0.9404805152899381,
  "cross_validation": {
    "status": "PASS",
    "difference": 1.1102230246251565e-16,
    "recommended_action": []
  },
  "numeric_theory_check": {
    "status": "INCONCLUSIVE",
    "recommended_action": [
      "finite simulation horizon has not reached the asymptotic SIR state; extend days before comparing it to final-size theory"
    ]
  }
}
```

Read that output carefully, because the engine is being deliberately honest with you:

- `cross_validation` PASS — two independent methods agree to machine precision.
- `numeric_theory_check` **INCONCLUSIVE** — the closed-form final-size formula has not
  converged yet at this horizon, and the engine tells you which knob to turn.

That `INCONCLUSIVE` is the behaviour you should want. An engine that reported PASS here
would be lying to you.

### A5. Start from a vague idea

You do not have to write a model by hand first.

```bash
axiomize intake "my gym keeps losing members after 3 months; how do I stop the churn?"
```

```json
{
  "status": "NEEDS_INPUT",
  "questions": [
    {"field": "system_boundary",
     "question": "What exactly are we modeling, and what is outside the system?"}
  ],
  "remaining_questions": 5,
  "rigor_recommendation": {"level": "medium", "reasons": ["default balanced depth"]}
}
```

The engine refuses to model something it does not understand. It asks what the system
boundary is, and recommends a depth:

| Level | When it is recommended | Old name |
|---|---|---|
| `weak` | quick exploration, small everyday problem, low stakes | `basic` |
| `medium` | no special signal; balanced analysis | `standard` |
| `strong` | research/publication, high stakes, causal claims, real experiments | `research` |

Override it with `--rigor strong`. You can also inspect the full interaction policy, which
lists every action that needs your consent:

```bash
axiomize policy
```

### A6. Validate a model you wrote

A Model IR request is JSON. A complete working one ships with the repository:

```bash
git clone https://github.com/Furox-Art/axiomize-quantum-skills-2.0
cd axiomize-quantum-skills-2.0
axiomize model --input-json docs/quickstart-model-ir.json --action validate
```

```json
{"status": "PASS", "model_ir": {"name": "member-churn-decay", "domain": "social", ...}}
```

Then simulate it:

```bash
axiomize model --input-json docs/quickstart-model-ir.json --action simulate
```

The output is the full time series. To see just the end state:

```bash
python -c "import json,subprocess,sys; d=json.loads(subprocess.run([sys.executable,'-m','axiomize.cli','model','--input-json','docs/quickstart-model-ir.json','--action','simulate'],capture_output=True,text=True).stdout); print('status:',d['status'],'| x_end:',round(d['states']['x'][-1],3))"
```

```text
status: PASS | x_end: 990.05
```

Other useful `--action` values on the same file: `stability`, `validity`,
`numerical-verify`, `uncertainty`, `export`, `compare`, `surrogate`. Some require
`--approve-heavy` or `--approve-migration`, which is the consent gate doing its job.

Useful fields when writing your own Model IR:

| Field | Notes |
|---|---|
| `independent_unit` | must be a unit the engine knows, e.g. `day` |
| `variables[].unit` | must be known, e.g. `persons`, `cells`, `mol`, `dimensionless` |
| `parameters[].unit` | rate units are written `1/day`, `1/s`, `1/hour`, `1/year` |
| `constraints[]` | each needs `name`, `expression`, `relation`, `threshold`; `scientific_basis` is optional (it defaults to empty) but it is how a constraint explains itself, so fill it in |

An unknown unit fails loudly rather than silently passing:

```text
axiomize.validation.dimensions.DimensionalMismatch: unknown unit: 'members'
```

That is intentional. `persons` is the correct unit for a head count; `members` is not a
quantity the dimensional engine can reason about.

### A7. Score a reasoning branch

The reasoning side is a separate command:

```bash
axiomize-reason score --evidence 0.9 --verification 0.85
```

```json
{"branch": "branch-1", "can_collapse": false, "reason": "leader score below collapse threshold"}
```

It declines to collapse. That is correct: a branch needs verification and margin, not just
high evidence. The collapse threshold is calibrated, not guessed — the sweep evidence is
in `benchmarks/reports/reasoning-threshold-sweep.md`.

### A8. Call it from an AI agent instead

```json
{"command": "axiomize", "args": ["mcp"]}
```

That serves MCP over stdio with 34 tools. There is also a REST API:

```bash
axiomize serve --port 8899
```

```bash
curl http://127.0.0.1:8899/capabilities
curl -X POST http://127.0.0.1:8899/solve -H 'content-type: application/json' -d '{"beta":0.3,"gamma":0.1,"N":100000}'
```

Loopback only by default. See [integrations.md](integrations.md) for the full surface.

---

## Track B: the agent skill

The skill is plain Markdown. You do not need the Python package for the agent to follow
the protocol, though the engine is what makes its validation real.

### B1. Install the skills

```bash
git clone https://github.com/Furox-Art/axiomize-quantum-skills-2.0
cp -r axiomize-quantum-skills-2.0/skills/axiomize          ~/.config/opencode/skills/  # opencode
cp -r axiomize-quantum-skills-2.0/skills/quantum-reasoning ~/.config/opencode/skills/
```

For Claude Code the destination is `~/.claude/skills/`:

```bash
cp -r axiomize-quantum-skills-2.0/skills/axiomize          ~/.claude/skills/
cp -r axiomize-quantum-skills-2.0/skills/quantum-reasoning ~/.claude/skills/
```

Two skills are installed:

| Skill | Folder | What it does |
|---|---|---|
| `axiomize` | `skills/axiomize/` | Turns a vague idea into candidate mathematical models, compares them, states what would falsify each |
| `quantum-reasoning` | `skills/quantum-reasoning/` | Keeps several hypotheses alive, prunes by evidence, collapses late |

Restart your agent so it rediscovers the skills.

### B2. Ask a real question

> Model this idea mathematically: my gym keeps losing members after 3 months; how do I
> stop the churn?

The agent should announce a rigor level (`medium` unless it says otherwise) and work
through the workflow. The skill's own phase list is:

| Phase | What happens |
|---|---|
| 0 | Clarify the idea, choose depth |
| 1 | Decompose into sub-problems, identify data needs |
| 2 | Parameters, assumptions, provenance |
| 3 | Build multiple candidate models |
| 4 | Data quality, fitting, computation |
| 5 | Compare, rank, reject |
| 6 | Error search, uncertainty, sensitivity, falsification |
| 7 | Hypotheses and empirical test plan |
| 8 | Reproducibility and delivery |

Reports written to that structure (Phase 1-8 plus a confidence ledger) follow the
8-phase report layout; the closest thing to a filled-in one is
[examples/epidemic-sir.md](https://github.com/Furox-Art/axiomize-quantum-skills-2.0/blob/main/examples/epidemic-sir.md).

### B3. Control the depth mid-session

| You say | You get |
|---|---|
| "just quickly" | `weak` — top parameters, plain words |
| *(nothing)* | `medium` — the full discipline |
| "this is for my thesis" | `strong` — model criticism, uncertainty intervals, reproducibility notes |
| "deeper" / "quicker" | moves one level in either direction, at any point |

### B4. Check the agent is being honest

Every report has a **confidence ledger**: each claim tagged `established` / `assumption` /
`speculation`. Never act on a speculation-tagged claim for an expensive decision. The skill
also requires that at least one candidate lens is **rejected with a stated reason** — an
analysis that only ever confirms one model has not been compared.

### B5. Give it real data

Point it at a CSV of observations and it calibrates instead of guessing:

> Here's `monthly_signups.csv` — fit the growth model to these real numbers.

Fitted values come back with confidence intervals and explicit fit-quality scores. See
[integrations.md](integrations.md) for the CLI (`axiomize fit`) and MCP equivalents.

---

## Where next

| I want to… | Go to |
|---|---|
| Read a complete worked report | [example-gallery.md](example-gallery.md) |
| See benchmark numbers and reproduce them | [benchmark-results.md](benchmark-results.md) |
| Wire up an agent | [integrations.md](integrations.md) |
| Understand the trust boundaries | [security.md](security.md) |
| See the real browsing docs | <https://furox-art.github.io/axiomize-quantum-skills-2.0/> |

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError: No module named 'axiomize'` | You installed the skill but not the package. `pip install axiomize-quantum-skills-2.0` |
| `unknown unit: '<name>'` | Unit is not in the dimensional table. Check `axiomize tools`, and use a quantity unit (`persons`, `mol`, `dimensionless`) |
| `request requires a model_ir (or model) JSON object` | Your JSON needs a `model_ir` wrapper object, not a bare model. Copy `docs/quickstart-model-ir.json` |
| `needs a model_ir ... JSONDecodeError: Unexpected UTF-8 BOM` | Your editor wrote a UTF-8 BOM. Save as plain UTF-8, no BOM |
| `MigrationApprovalRequired` | Your IR uses a legacy field layout. Re-run with `--approve-migration` to see the preview diff, then update |
| `npx axiomize-quantum` exits `127` saying it could not launch | The npm package is a launcher shim: install the Python package first (`pip install axiomize-quantum-skills-2.0`) so the CLI is on `PATH` |
| `npx axiomize-quantum` fails with `SyntaxError: Unexpected token ';'` | You have the superseded `2.0.0` pinned. `npm install axiomize-quantum-skills-2.0@1.2.0`, or check `npm view axiomize-quantum-skills-2.0 dist-tags` |