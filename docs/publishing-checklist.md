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
| Current release | 1.2.1 |

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

Both registries publish by **OIDC trusted publishing**, not by a long-lived token, and
**both carry a build attestation**.

### Three mechanisms, not one

These get blurred together, and only the third is build provenance.

| Mechanism | What it proves | What it does **not** prove |
|---|---|---|
| `dist.integrity` (sha512) / `shasum` (sha1) on npm, `digests.sha256` on PyPI | The bytes you received are the bytes that were published. | How they were built, or by whom. |
| npm `dist.signatures` | The **registry** signed the packument entry, so the metadata was not altered in transit. A transport signature. | Anything about the build. npm signs every package, attested or not. |
| Build attestation | A named CI workflow, repository and commit produced this artifact, and a transparency log holds the statement. | That the build was correct. |

### npm

The npm tarball is published with `--provenance` under an explicit `--tag latest`. Two
Sigstore attestations are attached, and both are readable without any tooling:

```bash
curl -s https://registry.npmjs.org/-/npm/v1/attestations/axiomize-quantum-skills-2.0@1.2.1
```

That returns two bundles:

| `predicateType` | What it is |
|---|---|
| `https://github.com/npm/attestation/tree/main/specs/publish/v0.1` | npm's own publish attestation |
| `https://slsa.dev/provenance/v1` | full SLSA v1 build provenance |

The npm SLSA statement carries these fields, read from the live `1.2.1` response:

| Field | Value for 1.2.1 |
|---|---|
| `buildDefinition.buildType` | `https://slsa-framework.github.io/github-actions-buildtypes/workflow/v1` |
| `buildDefinition.externalParameters.workflow.path` | `.github/workflows/npm-publish.yml` |
| `buildDefinition.externalParameters.workflow.repository` | `https://github.com/Furox-Art/axiomize-quantum-skills-2.0` |
| `buildDefinition.internalParameters.github.event_name` | `workflow_dispatch` |
| `buildDefinition.resolvedDependencies[0]` | the repository at one `gitCommit` — **this pins the repo, not the workflow file** |
| `runDetails.builder.id` | `https://github.com/actions/runner/github-hosted` (a builder identifier, not a page) |
| `runDetails.metadata.invocationId` | the run that performed the upload |

Only a trusted-publishing upload on a GitHub-hosted runner produces a SLSA statement, so
its presence is the evidence that OIDC was used here. That is why the npm trusted
publisher for this package is evidently already registered.

Verify the digest independently:

```bash
npm view axiomize-quantum-skills-2.0@1.2.1 dist.integrity
curl -sLO "$(npm view axiomize-quantum-skills-2.0@1.2.1 dist.tarball)"
sha512sum axiomize_quantum_skills_2_0-1.2.1.tgz
```

For `1.2.1` the registry `integrity` value, the recomputed tarball SHA-512, and the `sha512`
digest inside both attestations are the same value.

Inspect the attestation without downloading the tarball:

```bash
# what the attestations endpoint says
curl -s https://registry.npmjs.org/-/npm/v1/attestations/axiomize-quantum-skills-2.0@1.2.1
# npm's own view of the same thing
npm audit signatures --package=axiomize-quantum-skills-2.0 2>/dev/null || \
  npm view axiomize-quantum-skills-2.0@1.2.1 dist.signatures
```

`npm audit signatures` verifies the **transport** signature. It does not evaluate the
Sigstore build provenance; only the attestations endpoint above does that.

### PyPI

Published by trusted publishing against the `pypi` environment, and **attested too**. PyPI
serves [PEP 740](https://peps.python.org/pep-0740/) attestations **per file**, so the path
ends in `/<filename>/provenance`:

```bash
curl -s https://pypi.org/integrity/axiomize-quantum-skills-2.0/1.2.1/axiomize_quantum_skills_2_0-1.2.1-py3-none-any.whl/provenance
```

The statement is in-toto v1 with predicate type
`https://docs.pypi.org/attestations/publish/v1`, and the publisher block reads
`kind=GitHub`, `repository=Furox-Art/axiomize-quantum-skills-2.0`, `workflow=release.yml`,
`environment=pypi`. Its subject `sha256` equals the `digests.sha256` PyPI serves for the
same file.

```bash
# the digest the attestation must match
python -c "import json,urllib.request;d=json.load(urllib.request.urlopen('https://pypi.org/pypi/axiomize-quantum-skills-2.0/1.2.1/json'));print(d['urls'][0]['digests']['sha256'])"
```

Note that PyPI's predicate is a *publish* attestation, not SLSA: it records that the
upload came from the declared GitHub Actions workflow and environment. It does not carry
npm's `buildType`, `resolvedDependencies` or `runDetails` fields.

#### The URL shape, because the wrong one 404s misleadingly

```bash
# 200 -- a real attestation
curl -s -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/integrity/axiomize-quantum-skills-2.0/1.2.1/axiomize_quantum_skills_2_0-1.2.1-py3-none-any.whl/provenance

# 404 -- NOT an endpoint. Means "no such URL", not "no attestation".
curl -s -o /dev/null -w '%{http_code}\n' \
  https://pypi.org/integrity/axiomize-quantum-skills-2.0/1.2.1/
```

An earlier revision of this page claimed PyPI had "no public per-artifact attestation API
comparable to npm's". That was wrong: the per-file endpoint above exists and this package
has an attestation on it.

### What each channel gives you today

| Channel | Attestation | Predicate | Verifies build provenance? |
|---|---|---|---|
| npm | yes, 2 bundles | npm publish + SLSA v1 | **yes** — names workflow, repo and commit |
| PyPI | yes, per file | PEP 740 publish | partially — names workflow and environment, not the commit |

Neither channel is the weaker one in the way a digest-only channel would be, but they are
not equally detailed. If you need the resolved commit, npm's SLSA statement is the one
that carries it.

### The trusted-publisher condition, and its state here

An attestation only exists if the registry trusts a specific CI identity. For this project
that means a trusted publisher on each registry with:

| Field | Value |
|---|---|
| Owner | `Furox-Art` |
| Package / project | `axiomize-quantum-skills-2.0` |
| Workflow filename (npm) | `npm-publish.yml` |
| Workflow filename (PyPI) | `release.yml` |
| Environment | `npm` on npmjs.com, `pypi` on PyPI |

**State on this repository: satisfied on both registries.** That is not an assumption —
it is what the attestations report:

- npm's SLSA statement names `runDetails.builder.id =
  https://github.com/actions/runner/github-hosted` and
  `buildDefinition.externalParameters.workflow.path = .github/workflows/npm-publish.yml`
  with `event_name = workflow_dispatch`. Only a trusted-publishing upload on a
  GitHub-hosted runner produces that, so the npm trusted publisher is registered.
- PyPI's attestation publisher block reads `kind=GitHub`,
  `repository=Furox-Art/axiomize-quantum-skills-2.0`, `workflow=release.yml`,
  `environment=pypi`, which is only produced by trusted publishing.

**Do not read that as a general rule.** A sibling repository by the same owner publishes
the identical way on PyPI and has no npm trusted publisher at all, so its npm tarball is
digest-only. Whether a given package has an attestation is a per-registry fact to be
measured, not a property of the owner, the CI system, or the workflow file. Check the
endpoint; do not infer.

### Token-mode publishes carry no attestation

The workflow's `use_token_fallback` input publishes with `NPM_TOKEN` and **without**
`--provenance`, because a Sigstore attestation is signed from the OIDC identity and a token
has none. If you are reading this page to decide whether a given tarball is attested, check
the endpoint above rather than assuming: `2.0.0` returns HTTP 404 (no attestation),
`1.2.0` and `1.2.1` each return two.

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
- [x] Latest GitHub release matches the PyPI version (1.2.1)
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
| "npm package ready to use" | npm 1.2.1 is published and attested, but it is only a launcher shim for the Python CLI. Say "PyPI 1.2.1 is the install; npm 1.2.1 is a Node launcher for it" |

## Keeping this honest

When you update the version, update this file's identity table, `docs/index.md`,
`README.md` and `docs/benchmark-results.md` in the same commit. `check_release_contract.py`
in CI enforces the version lockstep across `pyproject.toml`, `src/axiomize/__init__.py`,
`.github/pypi-release-trigger`, `README.md` and `CHANGELOG.md`.