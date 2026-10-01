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

Verified at 1.2.0, commit `eb70a47`, CPython 3.12.10. Quote that commit if you quote the
`12/12` result.

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
| "npm package ready to use" | The published `index.js` is currently broken; use PyPI |

## Keeping this honest

When you update the version, update this file's identity table, `docs/index.md`,
`README.md` and `docs/benchmark-results.md` in the same commit. `check_release_contract.py`
in CI enforces the version lockstep across `pyproject.toml`, `src/axiomize/__init__.py`,
`.github/pypi-release-trigger`, `README.md` and `CHANGELOG.md`.