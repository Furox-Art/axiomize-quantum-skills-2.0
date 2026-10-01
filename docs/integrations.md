# Using Axiomize with AI Agents

Axiomize is a scientific engine; AI providers are clients of it. All three interfaces call
the same core services, so validation behaviour never depends on which agent calls.

Everything on this page was verified against `axiomize-quantum-skills-2.0` **1.2.0** at
commit `eb70a47`, CPython 3.12.10 (Windows), with the default install (no `pymc`, no
`jax`).

## Capability discovery

Every agent should start here:

```bash
axiomize capabilities      # machine-readable JSON, includes axiomize_version
axiomize tools             # human-readable backend availability table
```

MCP: `axiomize.get_capabilities`, `axiomize.list_tools`
REST: `GET /capabilities`, `GET /tools`

Only backends that genuinely imported are reported as available. On a default install you
get sympy, scipy, statsmodels, cvxpy, casadi, z3, networkx, control and matplotlib;
`pymc`, `jax` and `fenics` report `UNAVAILABLE` until you install them.

## Via CLI

`axiomize` has 14 subcommands:

| Command | Purpose |
|---|---|
| `intake` | clarify a vague idea before modeling |
| `policy` | show the adaptive workflow policy and consumption guard |
| `model` | plan / validate / simulate / fit / compare / repair / export / stability / validity / discover / experiment-design / uncertainty / bifurcation / numerical-verify / stop-check / surrogate on a Model IR |
| `clean-data` | clean paired numeric observations with a preserved audit trail |
| `compare-runs` | explain why two recorded runs differ |
| `solve` | solve the backward-compatible reference SIR model |
| `fit` | fit backward-compatible logistic growth to a CSV of `(time, value)` |
| `validate` | backward-compatible SIR solve plus dimensional and cross-validation |
| `tools` | list scientific backends and availability |
| `capabilities` | machine-readable capability map |
| `reproduce` | inspect a stored run |
| `benchmark` | run the install-safe scientific benchmark suite |
| `serve` | start the REST API (v1) |
| `mcp` | serve MCP over stdio |

Auxiliary entry points also installed on `PATH`: `axiomize-reason`, `axiomize-validate`,
`axiomize-fit`, `axiomize-csv-check`, `axiomize-benchmark`, `axiomize-to-latex`,
`axiomize-index-reports`, `axiomize-sweep`.

```bash
axiomize solve --beta 0.3 --gamma 0.1 --N 1000000 --json out.json
axiomize validate --N 1000000
axiomize intake "my gym keeps losing members after 3 months; how do I stop the churn?"
axiomize model --input-json docs/quickstart-model-ir.json --action validate
```

Note on `solve --json`: it writes the result payload, and that payload contains
**no `run_id`**. Do not feed it straight to `axiomize reproduce` — that command takes a run
directory produced by a run-recording path, not a solve result.

## Via MCP (stdio)

Host configuration:

```json
{"command": "axiomize", "args": ["mcp"]}
```

Verified handshake:

```json
{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05",
 "serverInfo":{"name":"axiomize","version":"v1"},"capabilities":{"tools":{}}}}
```

**34 tools**, all under the `axiomize.` prefix:

| Group | Tools |
|---|---|
| Intake and policy | `intake`, `workflow_policy`, `get_capabilities`, `list_tools`, `select_tools` |
| Reference SIR / logistic | `solve`, `simulate`, `validate`, `cross_validate`, `fit_model`, `compare_models`, `sensitivity_analysis`, `uncertainty_analysis` |
| Model IR | `model_plan`, `model_validate`, `model_simulate`, `model_fit`, `model_compare`, `model_export`, `model_repair` |
| Model IR analysis | `model_stability`, `model_validity`, `model_bifurcation`, `model_uncertainty`, `model_numerical_verify`, `model_stop_check`, `model_surrogate`, `model_discovery`, `experiment_design` |
| Data and runs | `clean_data`, `falsify`, `reproduce`, `inspect_run`, `compare_runs` |

Structured JSON in, structured JSON out (API v1). Tools that can be expensive
(`experiment_design`, `model_uncertainty`, `model_validity`, `model_bifurcation`,
`model_numerical_verify`, `model_discovery`, `model_surrogate` generation) accept
`approve_heavy`; that gate is the consent boundary, not a formality.

## Via REST (v1)

```bash
axiomize serve --port 8899
```

Binds to loopback only by default. `--allow-remote` requires a bearer token of at least 16
characters. Supply it through the environment rather than the command line so it does not
land in shell history or process listings:

```bash
export AXIOMIZE_REST_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
axiomize serve --allow-remote --port 8899
```

The environment variable name defaults to `AXIOMIZE_REST_TOKEN`; change it with
`--auth-token-env`.

Every route is available both bare and under a `/v1/` prefix (verified: `GET /capabilities`
and `GET /v1/capabilities` both return 200).

| Method | Route | Notes |
|---|---|---|
| GET | `/capabilities`, `/tools` | capability map, backend availability |
| POST | `/intake`, `/workflow-policy` | clarify an idea; read the policy |
| POST | `/solve`, `/simulate`, `/validate`, `/cross-validate` | reference SIR |
| POST | `/fit`, `/sensitivity`, `/uncertainty`, `/compare`, `/falsify` | reference fits and diagnostics |
| POST | `/clean-data`, `/compare-runs` | data hygiene, run diffing |
| POST | `/model` | Model IR dispatch |
| POST | `/model/stability`, `/model/validity-scan`, `/model/bifurcation`, `/model/uncertainty`, `/model/numerical-verify`, `/model/surrogate`, `/model/repair`, `/model/compare`, `/model/discover`, `/model/experiment-design`, `/model/export`, `/model/stop-check` | Model IR sub-actions |
| GET | `/runs/{id}` | inspect a stored run |
| POST | `/runs/{id}/reproduce` | replay a stored run |

Verified live:

```bash
curl http://127.0.0.1:8899/capabilities
curl -X POST http://127.0.0.1:8899/solve -H 'content-type: application/json' -d '{"beta":0.3,"gamma":0.1,"N":100000}'
```

```json
{"status": "PASS", "final_size": 0.940469006945311, ...}
```

Unknown routes return 404; malformed bodies return 400 with a reason.

## Portable runs

A run (`run.json` plus `manifest.json`) can be zipped, moved to another machine, and
inspected by another agent. Start in one agent, continue in another: the science carries
the state, not the chat. See [portable-export.md](portable-export.md).

## Agent status

Honest assessment of what has actually been exercised against this package.

| Agent | MCP | CLI | REST | Status |
|---|---|---|---|---|
| Any MCP client | yes | yes | yes | protocol-level tested only |
| Any HTTP client | yes | yes | yes | protocol-level tested only |
| Claude Code | yes | yes | yes | not field-tested here |
| OpenAI Codex | yes | yes | yes | not field-tested here |
| Cursor | yes | yes | yes | not field-tested here |
| OpenCode | yes | yes | yes | not field-tested here |

The MCP handshake and `tools/list` were exercised directly against
`axiomize mcp`, and the REST routes above against a live `axiomize serve`. No claim is made
about any named host application beyond protocol conformance: this repository does not
record field tests with those products, so the table does not assert them.

## Provider keys

Optional. Without a provider configured, the engine runs only its deterministic backends.
`axiomize.capabilities` reports which guarded actions require consent and which extras are
present, so an agent can ask before spending anything:

```bash
axiomize policy
```