# Publishing Checklist (external distribution)

Prepared text for submitting Axiomize Quantum Skills to agent-skill registries and
community lists.

## Identity — use this, exactly

| Field | Value |
|---|---|
| Display name | Axiomize Quantum Skills |
| Repository | <https://github.com/Furox-Art/axiomize-quantum-skills-2.0> |
| Documentation | <https://furox-art.github.io/axiomize-quantum-skills-2.0/> |
| PyPI | `axiomize-quantum-skills-2.0` (<https://pypi.org/project/axiomize-quantum-skills-2.0/>) |
| Import package | `axiomize` |
| Skill folders | `skills/axiomize/`, `skills/quantum-reasoning/` |
| License | MIT |
| Current release | 1.2.0 |

**Do not link `Furox-Art/axiomize`.** That is a separate, related repository with its own
release line. This package is the distribution `axiomize-quantum-skills-2.0`, and every
submitted link must point at it.

## One-liner (for lists)

> axiomize-quantum-skills-2.0 — an agent skill plus scientific engine that turns a plain
> idea into competing mathematical models, compares them across 15 perspectives with
> explicit units and dimensional checks, and states what observation would falsify each one.

## Registry entry (awesome-list style)

```markdown
- [Axiomize Quantum Skills](https://github.com/Furox-Art/axiomize-quantum-skills-2.0) —
  Idea to mathematical model: decomposes the problem, matches canonical archetypes
  (SIR, newsvendor, M/M/c), builds candidate models from 15 perspectives, rejects at least
  one with a stated reason, validates with runnable Python and dimensional checks, and
  reports what would falsify each model. Ships a second skill that keeps several
  hypotheses alive until evidence separates them. MIT.
```

## Verified quickstart to quote

```bash
pip install axiomize-quantum-skills-2.0
axiomize tools        # which backends are really installed
axiomize benchmark    # -> {"status": "PASS", "passed": 12, "total": 12}
```

Verified at 1.2.0, commit `9c2990c`, CPython 3.12.10. Quote that commit if you quote the
`12/12` result.

## Supply chain

Both registries are published by **OIDC trusted publishing**, not by a long-lived token.

### npm

The npm tarball is published with `--provenance` under an explicit `--tag latest`. Two
Sigstore attestations are attached, and both are readable without any tooling:

```bash
curl -s https://registry.npmjs.org/-/npm/v1/attestations/axiomize-quantum-skills-2.0@1.2.0
```

That returns two bundles:

| `predicateType` | What it is |
|---|---|
| `https://github.com/npm/attestation/tree/main/specs/publish/v0.1` | npm's own publish attestation |
| `https://slsa.dev/provenance/v1` | full SLSA v1 build provenance |

Fields inside the SLSA statement, as read from the live response:

| Field | Value for 1.2.0 |
|---|---|
| `buildDefinition.buildType` | `https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1` |
| `buildDefinition.externalParameters.workflow.path` | `.github/workflows/npm-publish.yml` |
| `buildDefinition.externalParameters.workflow.repository` | `https://github.com/Furox-Art/axiomize-quantum-skills-2.0` |
| `buildDefinition.internalParameters.github.event_name` | `workflow_dispatch` |
| `buildDefinition.resolvedDependencies[0]` | the repository at one `gitCommit` — **this pins the repo, not the workflow file** |
| `runDetails.builder.id` | `https://github.com/actions/runner/github-hosted` (a builder identifier, not a page) |
| `runDetails.metadata.invocationId` | the run that performed the upload |

Only a trusted-publishing upload on a GitHub-hosted runner produces a SLSA statement, so
its presence is the evidence that OIDC was used.

Verify the digest independently:

```bash
npm view axiomize-quantum-skills-2.0@1.2.0 dist.integrity
curl -sLO "$(npm view axiomize-quantum-skills-2.0@1.2.0 dist.tarball)"
sha512sum axiomize-quantum-skills-2.0-1.2.0.tgz
```

For 1.2.0 the registry `integrity` value, the recomputed tarball SHA-512, and the `sha512`
digest inside both attestations are the same value.

### Token-mode publishes carry no attestation

The workflow's `use_token_fallback` input publishes with `NPM_TOKEN` and **without**
`--provenance`, because a Sigstore attestation is signed from the OIDC identity and a token
has none. If you are reading this page to decide whether a given tarball is attested, check
the endpoint above rather than assuming: `2.0.0` returns HTTP 404 (no attestation), `1.2.0`
returns two.

### PyPI

Published by trusted publishing against the `pypi` environment. There is no public
per-artifact attestation API on PyPI comparable to npm's; the release is evidenced by the
GitHub Actions run and the PyPI upload timestamp.

## Where to submit

| Target | What to send |
|---|---|
| awesome agent-skill lists | the registry entry above |
| opencode community showcases | repo + Documentation URL + the epidemiology example |
| r/ClaudeAI, r/LocalLLaMA | the quickstart plus one worked report |
| Hacker News | "Show HN" with the quickstart and the honesty about limits |
| PyPI description / keywords | already set in `pyproject.toml`; see the release checklist there |

## Before submitting — all verified

- [x] CI green on `main`
- [x] Latest GitHub release matches the PyPI version (1.2.0)
- [x] `pip install` + `axiomize tools` + `axiomize benchmark` verified from a clean venv
- [x] Documentation site builds and is live
- [x] Every README and docs link returns HTTP 200
- [x] LICENSE present (MIT)
- [x] `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `CITATION.cff` present
- [x] Every link in the example gallery resolves to a file in this repository

## Do not claim

These would be untrue, so leave them out:

| Do not claim | Why |
|---|---|
| "the benchmark suite scores 9.21/10" | Removed: not reproducible, no transcripts retained |
| "N independent agents produced these reports" | The stored reports are maintainer-authored |
| "supported by Claude Code / Cursor / OpenCode" | Only MCP protocol conformance was tested here |
| a stars, forks, or downloads figure | Do not hardcode; link the package page instead |
| "npm package ready to use" | npm 1.2.0 is published and attested, but it is only a launcher shim for the Python CLI. Say "PyPI 1.2.0 is the install; npm 1.2.0 is a Node launcher for it" |

## Keeping this honest

When you update the version, update this file's identity table, `docs/index.md`,
`README.md` and `docs/benchmark-results.md` in the same commit. `check_release_contract.py`
in CI enforces the version lockstep across `pyproject.toml`, `src/axiomize/__init__.py`,
`.github/pypi-release-trigger`, `README.md` and `CHANGELOG.md`.