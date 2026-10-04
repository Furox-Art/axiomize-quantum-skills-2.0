# Changelog

All notable changes to Axiomize are documented here. Axiomize follows semantic versioning; release claims are tied to exact-wheel CI/release evidence.

## How to read this file

This changelog covers **two version lineages** that share one history, which used to make
the version numbers ambiguous. They are now separated:

| Lineage | Range | Where it lives |
|---|---|---|
| **Current distribution** `axiomize-quantum-skills-2.0` | 1.0.0 (2026-09-19) → present | [Releases](#releases-axiomize-quantum-skills-20) below, up to and including the current version |
| **Upstream lineage** of the `Furox-Art/axiomize` repository | 1.0.0 (2026-08-24) → 1.12.2 (2026-09-05), then 2.0.0 and 2.1.0 (2026-09-16) | [Upstream lineage](#upstream-lineage-furox-artaxiomize) further down, marked with an H1 |

Two consequences worth stating plainly:

- The engine code that became this package shipped first as `Furox-Art/axiomize` at version
  1.12.2. Versions 1.13 through 2.1.0 therefore belong to that repository, **not** to a
  release of the `axiomize-quantum-skills-2.0` distribution on PyPI.
- The distribution name `axiomize-quantum-skills-2.0` restarted the numbering at 1.0.0 on
  2026-09-19. So `1.0.0`, `1.1.0` and `1.2.0` each appear twice below. The earlier of each
  pair is upstream history; the later one is a real release of this package, identifiable
  by its date and by the tag on the GitHub Releases page for this repository.
- The npm package `axiomize-quantum-skills-2.0` is published at `2.0.0`. That number is not
  part of this lineage and does not correspond to any release here. (Superseded: #25 pinned
  `package.json` to `1.2.0` and CI now enforces the lockstep, so the next npm release
  carries the current version. The registry still serves `2.0.0` until that publish
  happens.)

`python .github/scripts/check_release_contract.py` enforces the version lockstep across
`pyproject.toml`, `src/axiomize/__init__.py`, `.github/pypi-release-trigger`, `README.md` and
the first `## [x.y.z]` heading in this file. That is why the first release heading must
always be the current version.

## Unreleased

### Fixed (supply chain)

- **Corrected a false claim this project made about its own PyPI release.**
  `docs/publishing-checklist.md` said PyPI had *"no public per-artifact attestation API
  comparable to npm's"* and that the release was *"evidenced by the GitHub Actions run and
  the PyPI upload timestamp"*. Both were wrong. PyPI serves
  [PEP 740](https://peps.python.org/pep-0740/) attestations **per file**, and this package
  has one on both artifacts of `1.2.1`. Verified:

  ```
  GET /integrity/axiomize-quantum-skills-2.0/1.2.1/axiomize_quantum_skills_2_0-1.2.1-py3-none-any.whl/provenance -> 200
    in-toto v1, predicateType https://docs.pypi.org/attestations/publish/v1
    publisher: kind=GitHub repository=Furox-Art/axiomize-quantum-skills-2.0
               workflow=release.yml environment=pypi
    subject sha256 b9a764c5ea1f57c78815536e5d42c2ede51b870ab7f79c852a886988ab60d53a
    == PyPI digests.sha256 for the same file
  ```

  The claim came from reading a `404` as "no attestation". The `404` was the wrong URL
  shape: `/integrity/<project>/<version>/` is not an endpoint, while
  `/integrity/<project>/<version>/<filename>/provenance` is. Both shapes are now shown side
  by side with the interpretation spelled out, because that inversion is easy to repeat.
- **The three supply-chain mechanisms are now separated everywhere they appear** in
  `README.md`, `SECURITY.md` and `docs/publishing-checklist.md`: a **digest**
  (`dist.integrity`, `digests.sha256`) proves bytes match and nothing about the build;
  npm's **`dist.signatures`** is a registry *transport* signature present for every package
  and is never build provenance; a **build attestation** is the only one that names a
  workflow, repository and commit. `npm audit signatures` is labelled as verifying the
  transport signature only.
- **The trusted-publisher condition is stated, and its state reported per registry instead
  of generalised.** For this package it is satisfied on both registries, and the
  attestations are the evidence: npm's SLSA statement names
  `runDetails.builder.id = https://github.com/actions/runner/github-hosted` and
  `externalParameters.workflow.path = .github/workflows/npm-publish.yml`; PyPI's publisher
  block names `workflow=release.yml, environment=pypi`. Only a trusted-publishing upload
  produces either. A sibling repository by the same owner publishes identically on PyPI and
  has **no** npm trusted publisher, so its npm tarball is digest-only. The docs say
  explicitly that whether a package is attested is a per-registry fact to be measured, not a
  property of the owner or the CI system.
- **Supply-chain version references refreshed to `1.2.1`**, which is current on both
  registries, with npm `shasum`, integrity and the PyPI wheel digest re-measured. The
  `--provenance` and token-mode sections now name `1.2.1`.
- Per-channel guidance added: npm's SLSA v1 statement proves the resolved commit, which
  PyPI's PEP 740 publish attestation does not, so a consumer knows which to read.
- `SECURITY.md` gains a supply-chain section it previously lacked, covering the three
  mechanisms, the two endpoints, and the wrong-URL-shape trap.

### Added (supply chain)

- **`docs/check_attestation_claims.py`**, a regression guard for supply-chain claims, with
  a built-in negative control. It rejects any claim that names no channel, states no
  definite status, presents `dist.signatures` as provenance, calls a stale version current,
  or quotes a PyPI integrity URL without the wrong-URL-shape caveat.

  ```bash
  python docs/check_attestation_claims.py             # scan the docs
  python docs/check_attestation_claims.py --online    # also re-measure both registries
  python docs/check_attestation_claims.py --self-test # negative control
  ```

  `--self-test` feeds the guard six deliberately false claims and fails unless all six are
  rejected, one correct channel-scoped claim it must accept, and two same-word-different-
  meaning cases it must not flag (`docs/benchmark.md` measurement provenance,
  `docs/example-gallery.md` parameter provenance). The guard also inherits channel scope
  from headings, so a paragraph under `### npm` need not repeat the word. Not wired into
  CI, because this change set does not touch workflows; the step that would do it is noted
  here.

### Not claimed (supply chain)

- No security claim is weakened. Both registries remain described as attested, because both
  are.

### Fixed (documentation)

- **README no longer claims a command produces a plot it does not.** It said "that curve is
  produced by the command in step 3 below", but `axiomize validate --N 1000000` emits JSON
  and writes no file, and no in-repo script generates `docs/sir-demo.gif` or
  `docs/sir-example.png`. The plots are written by the `--plot` flag of the
  `axiomize-validate` console script, which the README and `docs/index.md` now show:
  `axiomize-validate --model sir --beta 0.3 --gamma 0.1 --N 1000000 --plot sir.png`.
  Verified: it writes a 47 kB PNG reporting `Peak infected = 300,465 at day 61.4`, the same
  curve and annotation as the committed snapshot. The snapshot is **not** byte-identical to a
  fresh run (47 061 B vs 46 701 B) because Matplotlib's PNG output varies by version, so no
  byte-equality is claimed.
- **README no longer implies the `[full]` extra installs FEniCS/DOLFINx.** `[full]` is
  exactly `["pymc>=5.0", "jax>=0.4"]`. FEniCS/DOLFINx has no pip extra and must be installed
  separately; the README now says so, matching `docs/index.md`.
- **`axiomize model --action plan` is now shown in a form that runs.** The README implied it
  could be called bare; it requires `--input-json` and exits 2 without it, and there is no
  `--idea` flag. The README now uses `axiomize intake` for the idea-first path and notes the
  `--input-json` requirement explicitly.
- **Attestation field reference corrected.** The README said `resolvedDependencies` pins the
  repository *and* the workflow file. It pins only the repository at one `gitCommit`; the
  workflow path is under `buildDefinition.externalParameters.workflow.path`. Both fields are
  now named correctly in the README and tabulated in `docs/publishing-checklist.md`.
- `docs/benchmark-results.md` said 12 of 25 cases carry a `numeric_oracle`. Measured from
  `benchmarks/ideas.json`: **11**.

### Changed (documentation)

- **Provenance refreshed from `338bc9e` to `9c2990c`** across `README.md`,
  `docs/tutorial.md`, `docs/benchmark-results.md`, `docs/index.md`, `docs/integrations.md`,
  `docs/example-gallery.md` and `docs/publishing-checklist.md`. The previous reference was
  seven commits behind `main` and had diverged. Every command in the README was re-run at
  `9c2990c` and the 25-case corpus re-graded: still 25/25 PASS at 10.0/10, all exiting 0.
- `docs/benchmark-results.md` now reports each case's **measured** check count (8 to 11)
  instead of implying `10.0/10` always means 10 of 10. The runner builds a variable number of
  checks per case, so the denominators differ.
- README coverage: the Interfaces table now lists the **7 previously undocumented console
  entry points** (`axiomize-validate`, `axiomize-fit`, `axiomize-csv-check`,
  `axiomize-benchmark`, `axiomize-to-latex`, `axiomize-index-reports`, `axiomize-sweep`), so it
  no longer implies a two-command CLI. "What you get" now covers `packs/` (13 domain packs),
  `skills/axiomize/templates/` (5 report templates), the Lean 4 backend
  (`formal/lean_adapter.py`), the OpenAI-compatible provider layer (`providers/`), the
  6-case reasoning corpus with its 4 JSON schemas, `axiomize-reason select|width`, and
  versioned portable runs with Model IR SHA-256 integrity metadata.
- README Documentation table now covers all 20 site pages grouped as `mkdocs.yml` does, so no
  page is undiscoverable.
- README shortened to fit the coverage above without padding: duplicated command blocks were
  replaced by links to `docs/tutorial.md`, "See it work" keeps one image instead of three, and
  the supply-chain detail moved to a new `docs/publishing-checklist.md#supply-chain` section
  with a verification recipe.

### Not changed, deliberately

- The **Honest limits** wording and the **benchmark labelling** are untouched. The
  contract-compliance framing, the synthetic-placeholder disclosure and the note that the
  human rubric layer is unscored were audited and are accurate. The single exception is the
  `[full]` bullet, where a factually wrong dependency claim had to be corrected.

### Added (documentation)

- `docs/publishing-checklist.md` gains a **Supply chain** section: the two attestation
  predicate types, a field-by-field table of the SLSA v1 statement as read from the live
  registry, digest verification commands, and an explicit statement that token-mode
  publishes carry no attestation while trusted-publishing ones do.## Unreleased

### Fixed

- **`Release (npm)` no longer reports a successful publish as a failure.** `npm publish`
  returns when the registry's write path accepts the tarball; the read path is a CDN that
  converges asynchronously. The verification step polled six times at a flat ten seconds —
  a sixty-second budget — and exited `1` when that budget ran out. Run `37120477453`
  published `axiomize-quantum-skills-2.0@1.2.0` successfully and was still failed by its own
  job with *"not publicly visible after 6 attempts"*, because the read path needed roughly
  95 seconds. The step now calls `.github/scripts/wait_for_npm_visibility.py`: twelve
  attempts with a growing backoff (5, 5, 10, 10, 15, 15, 20, 20, 25, 30, 35, 40 — 190s of
  waiting in total, against a 600s hard ceiling), first match wins. On a deadline miss it
  emits `::warning::` stating that the upload was not rolled back, and still exits non-zero,
  so a version that genuinely never appeared fails closed.
- The visibility check now reads the registry packument over HTTP instead of calling
  `npm view`, because `npm view` is served from npm's local `_cacache`: the check was a
  question about the runner's cache rather than about the registry, which is how a warm
  cache produces a false negative. One request also yields both `versions[<version>]` and
  `dist-tags.latest` from the same document, so the version and the tag cannot be read
  inconsistently, and a 404 is distinguishable from a 5xx or a dropped connection.
- The visibility probe no longer dies on a dropped connection. `http.client.HTTPException`
  — which includes `RemoteDisconnected`, the shape a CDN returns when it closes a
  connection mid-response — is not a `urllib.error.URLError`, so catching only the urllib
  classes let it escape as a traceback and fail the release job on the first flaky read.
  Found by running the new probe against the live registry, not by inspection.
- `tests/test_npm_publish_visibility.py` is the regression test, 15 cases covering both
  directions: absent-then-present is verified rather than misreported, and a version that
  never appears still fails closed. It drives the poll through injected `probe`/`sleep`/
  `clock` callables, so it needs no network and no wall-clock delay.
- The `Release (npm)` header claimed the npmjs.com trusted publisher *"is not yet
  registered, and mode 1 fails closed without it"*. That is no longer true: the published
  1.2.0 tarball carries a Sigstore attestation and a SLSA v1 provenance statement built on
  `https://github.com/actions/runner/github-hosted`, which only a trusted-publishing upload
  produces. The comment now says so, and describes token mode as the retained escape hatch
  it now is rather than the only working path.

### Changed

- **npm documentation corrected to match the registry.** npm's `latest` dist-tag is now
  `1.2.0`, matching PyPI, verified against `registry.npmjs.org`. The README, `docs/index.md`,
  `docs/integrations.md`, `docs/tutorial.md` and `docs/publishing-checklist.md` said npm was
  one release behind and unusable; they now describe it as a published, attested
  **thin Node launcher shim** that spawns the Python CLI and therefore needs the Python
  package on `PATH`. The npm version badge is back, now that the two registries agree.
- The `CHANGELOG` note above about the registry holding `2.0.0` "until that publish
  happens" is superseded: the publish happened, `latest` moved to `1.2.0`, and `2.0.0`
  survives only as a superseded, no-longer-tagged version.

### Added

- Nothing user-facing. The new script is release tooling.

### Not claimed

- The docs state that npm 1.2.0 carries Sigstore and SLSA v1 provenance because that was
  read from `https://registry.npmjs.org/-/npm/v1/attestations/axiomize-quantum-skills-2.0@1.2.0`,
  which returns two bundles. The tarball's SHA-512 was independently recomputed and matches
  both the registry `integrity` field and the digest inside those attestations. Token-mode
  publishes still carry no attestation, because there is no OIDC identity to sign one; the
  1.2.0 upload was not token mode.

### Changed

- **npm status corrected after #25.** #25 fixed `index.js` and pinned `package.json` to
  `1.2.0`, so the documentation no longer describes the npm CLI as broken in the source.
  It does describe it accurately for users, because the fix is **not yet published**:
  `registry.npmjs.org` still serves `2.0.0`, uploaded 2026-09-28, whose `index.js` is the
  old `proc.on('close', (code) =; }` and whose tarball is 303 files / 2.1 MB. So
  `npx axiomize-quantum` still fails while `node bin/axiomize-quantum.js` works from a
  checkout. Verified on the merged tree: `node --check` exits 0 on both JavaScript files,
  `node index.js --help` exits 0, a bad subcommand exits 2, `require('./index.js')`
  resolves, and `npm pack --dry-run` produces 6 files / 41.2 kB. PyPI 1.2.0 is the
  supported install.
- README, `docs/index.md`, `docs/tutorial.md`, `docs/integrations.md` and
  `docs/publishing-checklist.md` now say "npm is behind, PyPI is current" instead of either
  "npm is broken" or "npm works". Benchmark and command provenance now cites the merge
  commit rather than the pre-merge one, and the 25-case corpus was re-graded on the merged
  tree: still 25/25 PASS at 10.0/10 with identical lens counts.
- `SECURITY.md` records the exact API response behind its reporting guidance
  (`{"enabled":false}`), names the advisories endpoint so a reader can see it does not work
  yet, and states the single settings change that would fix it. The fallback instructions
  are unchanged because the setting is genuinely still disabled.

### Added

- `CITATION.cff` so the package can be cited, and `CODE_OF_CONDUCT.md`.
- Issue templates for bugs, feature requests and questions, plus `.github/ISSUE_TEMPLATE/config.yml`
  routing security reports and documentation questions to the right pages. Bare issues are
  now redirected to the templates.
- `docs/quickstart-model-ir.json`: a complete, copy-pasteable Model IR request used by the
  README and tutorial quickstarts.
- A documentation section that shows the engine working: the previously unreferenced
  `docs/sir-demo.gif`, `docs/sir-example.png` and `docs/report-sample.pdf` are now embedded
  with captions describing what they show.
- Repository metadata: topics covering the causal, dimensional, uncertainty and
  reproducibility surfaces, and a description that states the released version instead of
  claiming "Axiomize 2.0".

### Fixed

- **Every cross-repository link now points at this repository.** `docs/tutorial.md` told
  readers to `git clone https://github.com/Furox-Art/axiomize` — a different repository with
  a different release line — and to copy a skill path from it. It now clones this
  repository. `docs/example-gallery.md` linked all 13 of its example links plus its
  "full texts live in" link to the sibling repository, and `docs/benchmark-results.md`
  linked 11 of its report links there; both now resolve to files in this repository. The
  gallery's `#the-fifteen-lenses` anchor pointed at a heading that does not exist in the
  target README; the lens list is now stated locally.
- `docs/example-gallery.md` covered 11 of the 18 examples in `examples/`. All 18 are now
  listed, each verified to exist, each linked exactly once.
- **The tutorial's commands work against the current API.** `docs/tutorial.md` now records
  `intake`, `policy` and `model` (which did not exist when it was written), and each command
  in it was executed against 1.2.0 at commit `eb70a47` on CPython 3.12.10 before being
  documented. It gains a troubleshooting table covering the errors a new user actually hits,
  including the Model IR wrapper requirement, unknown units, and UTF-8 BOM input.
- `docs/integrations.md` listed 14 MCP tools; the server exposes 34. It listed 6 REST
  routes; 27 exist. Both are now accurate, with the route table verified against a live
  `axiomize serve`. The `{"command":"axiomize","args":["mcp"]}` config is verified by a real
  `initialize` + `tools/list` handshake.
- `docs/integrations.md` implied `axiomize solve --json` produces a run id you can pass to
  `axiomize reproduce`. It does not — the payload has no `run_id`. That is now stated.
- `docs/integrations.md` listed "Hermes Agent — SUPPORTED (built and tested here)" and
  checked boxes for Claude Code, Cursor, OpenCode and OpenCode. No field test against any of
  these is recorded in this repository, so the table now states what was actually exercised:
  MCP protocol conformance and live REST responses. The unverifiable row and the checkmarks
  are gone.
- `docs/integrations.md` and `SECURITY.md` now name the correct token environment variable
  (`AXIOMIZE_REST_TOKEN`, minimum 16 characters) and recommend the environment over
  `--auth-token`.
- `SECURITY.md` referred to GitHub private vulnerability reporting "when available". It is
  **not** enabled on this repository, so the policy now says so and gives the routes that do
  work, plus what a maintainer can do to close the gap.
- `mkdocs.yml` had no `site_url`, so the published `sitemap.xml` was an empty `<urlset/>` —
  zero URLs, silently. It now emits 20. Added the `search` plugin, so `/search/` resolves
  instead of 404ing.
- `mkdocs.yml` listed 6 pages in nav while 14 more were built but unreachable. All are now in
  the nav, grouped. `mkdocs build --strict` is clean with zero warnings.
- The documentation site homepage linked only the example gallery and PyPI. It now links
  the tutorial, integrations, benchmark results, security, contributing, code of conduct,
  changelog, citation and license.
- `docs/publishing-checklist.md` was a submission checklist for the sibling repository,
  including a "README GIF renders" item that could not pass here. It is rewritten for this
  package, with an explicit "do not claim" table.
- README no longer shows a PyPI downloads badge. `img.shields.io/pypi/dm/axiomize-quantum-skills-2.0`
  answers HTTP 200 while rendering `downloads: rate limited by upstream service` (or
  `downloads: inaccessible`), because shields.io scrapes a third-party download API.
  The README now links the PyPI and npm project pages, which always answer HTTP 200 and
  always carry the real numbers. No count is hardcoded. New
  `tests/test_readme_badges.py` fails if a dynamic download badge or a hand-copied
  download count reappears.
- README badge markup: `img.shields.io/badge/python-3.10%2B-informational` rendered the
  literal text `3.10%2B` instead of `3.10+`. Replaced with `img.shields.io/python-3.10+-blue`.
- The README described the package as "Axiomize 2.0" and documented `npx axiomize-quantum`
  as a working quickstart. It is neither: the released line is 1.2.0, and the published npm
  `index.js` fails `node --check` with a syntax error, so that command cannot run. The
  README now states the released version and lists the npm breakage under honest limits
  rather than advertising it as a way in.

### Changed

- README rewritten to document the surface that actually ships: 9 CLI entry points, 14
  `axiomize` subcommands, 34 MCP tools, the REST routes, and the two installable agent
  skills. It previously documented none of them.
- `docs/benchmark-results.md` no longer reports per-wave scores such as a "suite average
  9.21/10" attributed to blind-test sessions by independent agents. Those figures had no
  retained transcripts, could not be reproduced, and one was mis-stated in place. The page
  now carries a provenance block (script, package version, commit, Python, numeric stack)
  for a run that was actually executed and re-executed while writing it, plus the full
  25-case result table, the 12 cases that carry a numeric oracle, and an explicit statement
  of what the automated layer does not check. The stored reports are described as
  maintainer-authored rather than as independent-agent output.
- `docs/benchmark-results.md` described "skill version at test time: v1.3.0 content". No 1.3.0
  exists in this repository's release line; the claim is removed.
- `docs/example-gallery.md` labels its 18 examples as illustrative worked reports rather than
  measured results, and states the parameter-provenance conventions (`exo`/`endo`,
  `lit.`/`data`/`est.`).
- `docs/worked-examples.md` is labelled as illustrative sketches with no recorded run, and
  points at the graded corpus for reproducible numbers.
- This changelog now separates the upstream lineage from this distribution's releases, so a
  reader can tell which version numbers refer to a real release here.

## Releases (axiomize-quantum-skills-2.0)

## [1.2.1] - 2026-10-03

Documentation corrections and test coverage. No public API change: the console entry
points, the REST and MCP surface, the Model IR schema and the agent skills are
unchanged from 1.2.0, and every 1.2.0 call site keeps working.

The point of this release is that PyPI's project page renders `README.md` as the
`long_description`, and that text is frozen into the artifact at build time. The
1.2.0 upload therefore still shows the pre-correction README, including the
claims corrected below. Only a new upload changes it, which is why the
documentation fixes need a version bump even though no code changed.

### Fixed (documentation)

- README no longer claims a command produces a plot it does not. The plots are
  written by `axiomize-validate --plot`, and the README and `docs/index.md` now
  show that invocation.
- README no longer implies the `[full]` extra installs FEniCS/DOLFINx. `[full]` is
  exactly `pymc>=5.0` and `jax>=0.4`; FEniCS/DOLFINx has no pip extra.
- `axiomize model --action plan` is documented in a form that runs, and the
  idea-first path uses `axiomize intake`.
- The attestation field reference is corrected: `resolvedDependencies` pins the
  repository at one `gitCommit`; the workflow path lives under
  `buildDefinition.externalParameters.workflow.path`.
- The PyPI downloads badge is gone. `img.shields.io/pypi/dm/...` answers HTTP 200
  while rendering `downloads: rate limited by upstream service`, so the badge
  looked live and showed nothing. The package pages are linked instead.
- The Python version badge no longer renders the literal `3.10%2B`.
- The README no longer presents `npx axiomize-quantum` as a working quickstart.
  The published npm `index.js` failed `node --check` with a syntax error; the
  breakage is stated under honest limits instead of being advertised as a way in.
- `docs/benchmark-results.md` drops per-wave scores attributed to blind-test
  sessions that had no retained transcripts and could not be reproduced, and the
  "v1.3.0 content" claim is removed because no such release exists in this line.
- The sibling-repository page `docs/publishing-checklist.md` is rewritten for this
  package, including the "README GIF renders" item that could not pass here.

### Changed (documentation)

- README rewritten to document the surface that actually ships: 9 CLI entry
  points, 14 `axiomize` subcommands, 34 MCP tools, the REST routes and the two
  installable agent skills. It previously documented none of them.
- `docs/example-gallery.md` labels its examples as illustrative worked reports with
  stated parameter provenance; `docs/worked-examples.md` is labelled as sketches
  with no recorded run and points at the graded corpus.
- This changelog separates the upstream lineage from this distribution's releases,
  so a reader can tell which version numbers refer to a real release here.

### Added (tests)

- `ruff` and `mypy` gates in CI, which were declared in `pyproject.toml` and run
  nowhere. Type findings are pinned to measured counts in
  `.github/mypy-baseline.txt`, so new errors fail the build and existing ones
  cannot be quietly absorbed.
- A non-decreasing branch-coverage ratchet. The scope was widened to include
  `skills/axiomize/tools`, the 1315 statements the wheel ships behind seven of the
  nine console entry points, which `--cov=axiomize` had been excluding.
- A build job that asserts every declared console entry point resolves inside the
  built wheel and that the sdist can rebuild it.
- A real `npm test` contract suite (the previous script always exited non-zero and
  was never invoked), plus an `npm-contract` CI job.
- Distribution-name and README-badge regression guards.

### Fixed (CI and packaging)

- The npm launcher had a syntax error and spawned a Python module that does not
  exist, so `npx axiomize-quantum` never worked. Both are fixed and the published
  tarball is constrained to an explicit allowlist.
- `pages.yml` linked the staged skill pages at a different repository; a link
  leaving the site is not a broken link, so `mkdocs build --strict` never noticed.
- `docs/adaptive-workflow.md` was missing from `.gitignore` despite being a
  generated page, leaving a hand-edited duplicate one `git add -A` away.
- Publishing is driven by the version-bump trigger with a registry existence
  check, so a re-run cannot double-publish. `main` is protected by a ruleset
  requiring a pull request and the 19 quality checks.

### Not changed, deliberately

- No new runtime dependency, no changed default, no schema or protocol change.
  This is a patch release that carries documentation and CI corrections only.

## [1.2.0] - 2026-09-30

### Added

- causal estimators now carry external-reference checks against statsmodels: front-door
  (`x→m`, `m→y` and direct-effect) point estimates and HC1 standard errors match statsmodels
  OLS, and binary AIPW matches a statsmodels Logit propensity plus two OLS outcome models
  (PR #19; `tests/test_numerical_reference.py::TestCausalExternalReference`)
- `exponential` and `student_t` log-likelihoods in the package-native Bayesian engine, both
  checked against `scipy.stats` (PR #20; `tests/test_bayesian_likelihoods.py`)
- optional Metropolis-adjusted Langevin sampling via `sampler: langevin` (alias `mala`); a
  non-finite gradient step falls back to random-walk Metropolis for that iteration. The
  default sampler is unchanged and remains Metropolis-Hastings (PR #20)
- benchmark corpus grown from 20 to 25 closed-form cases with formula-checked oracles
  (PR #21; `benchmarks/ideas.json`, `tests/test_benchmark_ideas.py`):
  - physics: RC discharge, `10/e` V
  - biology: three doublings, 8000 cells
  - chemistry: first-order half-life, `ln(2)/0.1` h
  - operations: M/M/1 queue wait, 0.8 h
  - causal: randomized difference in means, 4

## [1.1.1] - 2026-09-29

- Metadata-only patch release: refreshed PyPI keywords, classifiers, and discovery metadata; no functional API changes.

## [1.1.0] - 2026-09-27

### Changed

- calibrated the reasoning branch-controller default `collapse_score` from 0.78 to 0.65 using
  paired-sweep evidence (`benchmarks/reports/reasoning-threshold-sweep.md`): the 0.78 reference
  never fired under bounded noisy evidence, while 0.65 fires early in clear regimes with zero
  premature-wrong collapses; verification/margin/contradiction guards are unchanged
- `skills/quantum-reasoning/docs/MEASUREMENT.md` documents the calibrated threshold and its evidence

### Added

- offline ablation harness `axiomize.reasoning.ablation` comparing the branch controller against
  argmax-commit and top-2 beam baselines on deterministic ground-truth episodes, including
  regime-shift cases; report: `benchmarks/reports/reasoning-ablation.md`
- paired collapse-threshold sweep + safety-first `recommend_threshold` selector; report:
  `benchmarks/reports/reasoning-threshold-sweep.md`
- benchmark corpus broadened to 20 cases (physics/biology/chemistry/operations/causal) with
  stored blind-test reports for every case
- causal estimators now carry external-reference checks against statsmodels (IV/2SLS, HC1 OLS)
- community regression tests for numeric-oracle keyword alternatives (PR #11)
- README PyPI version/downloads badges

### Housekeeping

- CI action pins bumped (upload-artifact 7.0.1, download-artifact 8.0.1 via Dependabot)

## [1.0.0] - 2026-09-19

### First independent release

- first release under the distribution name `axiomize-quantum-skills-2.0`
- carries the full merged engine: Model IR, native model families, causal/Bayesian inference,
  uncertainty and provenance layers, plus `axiomize.reasoning` (quantum-inspired multi-branch
  hypothesis management) and the self-contained `skills/quantum-reasoning/` skill folder
- stored blind-test benchmark coverage completed: all 15 cases in `benchmarks/ideas.json`
  have reports and grade 10/10
- CI fully green across Python 3.10-3.13 and Linux/macOS/Windows wheel smoke;
  trusted-publishing release pipeline publishes the exact tested wheel to PyPI

# Upstream lineage: Furox-Art/axiomize

Everything below was released from the `Furox-Art/axiomize` repository, not from the
`axiomize-quantum-skills-2.0` distribution. No tag below exists on this repository's
Releases page, and none of these version numbers identifies a build of this package. The
code described here is what became this package at 1.0.0 on 2026-09-19.

## [2.1.0] - 2026-09-16

### Added

- the quantum-reasoning skill is now a self-contained skill folder, `skills/quantum-reasoning/`, holding `SKILL.md`, `VERSION`, `docs/` and `examples/` (moved from the flat `skills/quantum-reasoning-SKILL.md` file)
- `axiomize.reasoning.benchmark` is now an importable subpackage; the evaluator and submission validator still run standalone
- ported benchmark/submission contracts plus CLI and controller edge-branch tests: `tests/test_reasoning_benchmark.py`, `tests/test_reasoning_quantum.py`, `tests/test_reasoning_contracts.py`, `tests/test_reasoning_cli.py` — 89 reasoning tests, 98% coverage across the merged `axiomize.reasoning` and `axiomize.workflow.reasoning_adapter` modules (branch controller and adapter at 100%)
- `skills/quantum-reasoning/SKILL.md` frontmatter description now carries an explicit trigger phrase so skill loaders route it correctly
- `dist/` and `build/` are ignored; local wheel builds no longer show up as untracked files

### Changed

- `skills/axiomize/tools/check_skill.py` now validates every skill folder in the repo (frontmatter, folder/name match, trigger phrase and relative links) instead of only `skills/axiomize`
- both CI and the release workflow run the full quantum-reasoning contract (`tests/test_reasoning_quantum.py` + `tests/test_reasoning_benchmark.py`)
- the quantum-reasoning docs live only in `skills/quantum-reasoning/docs/`; the duplicated copies under `src/axiomize/reasoning/docs/` were removed
- relative links in the ported skill docs, examples and benchmark README now resolve inside the merged layout
- `pyproject.toml` ships the whole skill folder in the wheel as `axiomize/quantum-reasoning/`

## [2.0.0] - 2026-09-16

### Merged

- merged standalone `quantum-reasoning-skill` v0.3.1 into `axiomize.reasoning` (same `axiomize` repo name, now version 2.0)
  - `src/axiomize/reasoning/branch_controller.py` — deterministic branch score/prune/revive/collapse logic, ported verbatim
  - `src/axiomize/reasoning/benchmark/` — evaluator, submission validator, seed cases + JSON schemas
  - `src/axiomize/reasoning/docs/` — MEASUREMENT + COMPATIBILITY contracts
  - `skills/quantum-reasoning/` — model-facing protocol, docs and examples (moved from the standalone repo layout)
  - `tests/test_reasoning_quantum.py` — 8 ported tests, all passing
- previous `quantum-reasoning-skill` repo is superseded; its README now points here and the repo will be archived

## [1.12.2] - 2026-09-05

### Fixed / hardened

- synchronized the public README package line with the actual release version and made release CI enforce README/CHANGELOG/package/trigger version lockstep
- blocked the Release workflow from publishing when manually dispatched against any ref other than `refs/heads/main`
- rejected boolean values at shared finite numeric boundaries instead of silently coercing `True`/`False` to `1.0`/`0.0`
- bounded textual integer parsing before conversion so oversized integer strings fail before interpreter-dependent parsing limits are reached
- made run-manifest format-version validation exact, rejecting booleans and fractional values that previously could be accepted through `int(...)` coercion
- closed the superseded unmerged 1.12.0 scientific-maturity draft PR after the shipped 1.12.0/1.12.1 line replaced it

### Release gates

- full Python 3.10/3.11/3.12/3.13 validation
- security contract and dependency audit
- source and installed import-graph contracts
- exact built-wheel CLI/Model IR/export/surrogate/LaTeX/scientific stress checks
- Ubuntu/Linux, Windows and macOS exact-wheel CLI smoke
- Trusted Publishing-first PyPI publication and verification

## [1.12.1] - 2026-09-05

### Fixed

- PDE automatic solver planning now uses the same real `FEniCSAdapter.availability()` probe as the executable FEM path.
- DOLFINx-only installations are correctly routed to the bounded FEM executor instead of being misclassified as SciPy/method-of-lines only.
- a merely importable but unrunnable legacy FEniCS installation no longer causes the planner to advertise FEM execution incorrectly.
- public `general_engine.select_solver()` and direct `general_engine_core.select_solver()` now share the same PDE backend decision contract while preserving explicit user solver configuration.

## [1.12.0] - 2026-09-05

### Added

- all-family scientific benchmark/stress matrix with explicit per-case and total runtime budgets
- permanent exact-installed-wheel scientific stress gate in CI and release preflight
- Causal Engine 2.0:
  - DAG cycle validation
  - explicit/DAG-derived backdoor adjustment
  - post-treatment-adjustment rejection
  - AIPW doubly-robust, IPW and outcome-regression estimates for binary treatment
  - robust continuous-treatment backdoor regression
  - positivity/overlap, effective-sample-size and covariate-balance diagnostics
  - bounded intervention/counterfactual predictions
- package-native Bayesian Engine 2.0:
  - bounded multi-chain random-walk Metropolis
  - split R-hat, bulk ESS and MCSE
  - posterior interval summaries
  - posterior predictive RMSE, predictive coverage and Bayesian p-values
- real optional structured FEniCS/DOLFINx FEM executor for bounded scalar Poisson P1 problems on unit intervals/squares
- numerical-verification contracts for every Model IR family; stochastic between-seed variability remains explicitly separate from numerical error
- Modelica 3.6 textual export for supported ODE/DAE/algebraic models
- GraphML network export
- Graphviz DOT causal-DAG export
- `axiomize.portable-bundle.v1` export with canonical Model IR SHA-256 integrity metadata

### Changed

- runtime capability discovery now advertises Causal Engine 2.0, Bayesian diagnostics/PPC, all-family numerical verification and extended exports
- FEniCS availability is based on a real executable backend probe rather than module-name presence
- README, ROADMAP and CHANGELOG now describe the actual hardened scientific engine rather than the older prompt/skill-only architecture

### Release gates

- Python 3.10/3.11/3.12/3.13 validation
- security contract and dependency vulnerability audit
- source and installed import-graph contracts
- exact built wheel installation and full CLI/Model IR/export/surrogate/LaTeX checks
- all-family scientific stress matrix
- Ubuntu/Linux, Windows and macOS exact-wheel CLI smoke
- Trusted Publishing-first PyPI publication and verification

## [1.11.2] - 2026-09-05

### Security / correctness

- replaced permissive mathematical parsing paths with a bounded AST-whitelist boundary and explicit AST→SymPy construction
- removed arbitrary `eval()` use from Z3 constraint handling; added solver timeout and denominator-domain guards
- hardened Model IR namespaces, targets, bounds, finite values, solver settings and schema migrations
- prevented silent future-schema migration and schema-version relabeling
- made arbitrary Python and Lean execution explicit-trust operations with reduced environment inheritance and resource/time limits
- confined REST/MCP run-file access to configured run roots; added request/message/concurrency/read-time limits and safer errors
- added provider URL/redirect/request/response/timeout hardening
- added run-state content integrity verification and atomic persistence
- added hard non-bypassable limits for arrays, draws, networks, optimization, event queues, PDE work, causal matrices and other native executors
- hardened LaTeX conversion with a mathematical macro allow-list and `-no-shell-escape`
- corrected finite-horizon SIR validation versus asymptotic final-size theory
- hardened direct SciPy/CVXPy/CasADi/statsmodels/PyMC/benchmark/playground/CSV/parallel-sweep surfaces
- preserved first-occurrence order when duplicate data are merged with `sort_time=False`

### CI / supply chain

- immutable commit-SHA pinning for external GitHub Actions
- permanent security-contract scanner
- dependency vulnerability audit
- direct adversarial runtime regressions
- release verification hardened against PyPI propagation delay without weakening Trusted Publishing or exact-artifact gates

## [1.11.1] - 2026-09-05

### Added

- permanent exact-wheel/CLI matrix on Ubuntu/Linux, Windows and macOS in normal CI and release preflight
- platform-independent wheel smoke harness

### Fixed

- macOS ARM dependency compatibility by constraining the Darwin Z3 line to compatible 4.x releases
- release smoke SIR horizon corrected so it tests CLI portability rather than an intentionally truncated asymptotic final-size comparison

## [1.11.0] - 2026-09-05

### Added

- validated polynomial response-surface surrogate/reduced-order models
- deterministic Latin-hypercube training design through full Model IR execution
- explicit approval before multiplying full-model simulations
- untouched holdout validation with RMSE/NRMSE/MAE/max-error/R² thresholds
- default blocking of out-of-domain surrogate extrapolation
- exact source-model provenance and dataset hashes
- CLI/REST/MCP surrogate paths and installed-wheel release smoke

## [1.10.0]

### Added

- numerical/discretization verification separated from parameter/data/structural uncertainty
- PDE mesh-refinement studies with observed-order/Richardson-style estimates
- ODE/DAE tolerance refinement
- approval gating before repeated numerical solves
- CLI and REST numerical-verification services

## [1.9.0]

### Added

- native advanced-family execution for PDE, index-1 DAE, optimization, control, network, Bayesian, agent-based, discrete-event, hybrid, multiphysics and causal Model IR
- method-of-lines finite-difference PDE support with Dirichlet/Neumann boundary conditions
- solver fallback diagnostics and advanced family execution through the stable general-engine facade

## [1.8.0]

### Added

- canonical versioned Model IR / DSL as the single source of truth for deterministic scientific execution
- migration preview/approval contract and reproducible migration history
- model-family/domain recommendation and solver selection
- native algebraic, ODE and stochastic execution
- generic ODE fitting, scientific constraints/repair, residual diagnostics, AIC/BIC, stability/validity and nondimensionalization planning
- SINDy-style sparse dynamics discovery, experiment ranking, provenance and portable exports
- CLI `axiomize model` path and shared REST/MCP application services

## [1.7.0]

### Added

- adaptive weak/medium/strong workflow and user-controlled clarification
- explicit consumption policy: no silent extra agents, whole-analysis reruns or extra paid calls
- stronger reproducibility, uncertainty, hypothesis/falsifier and visualization workflow contracts

## [1.6.0]

### Added

- standardized `ScientificTool` interface and live backend availability probes
- SciPy, SymPy, statsmodels, Z3, CVXPY, CasADi, network/control and Bayesian scientific adapters
- dimensional validation and explicit validation statuses
- application services, CLI, REST, MCP, provider abstraction and portable run-state foundations

## [1.5.0] - 2026-08-24

### Added

- first-principles protocol for ideas with no matching archetype
- novel-domain benchmark reports and novel-territory report appendix

## [1.4.1] - 2026-08-24

### Fixed

- LaTeX converter hardening across worked examples/benchmark reports
- removed committed TeX build artifacts and expanded `.gitignore`

## [1.4.0] - 2026-08-24

### Added

- LaTeX/PDF export for reports
- sample rendered report

## [1.3.2] - 2026-08-24

### Added

- animated demo
- benchmark-report regression wired into CI

## [1.3.1] - 2026-08-24

### Added

- stored blind-test benchmark reports and benchmark results documentation
- epidemiology and operations domain packs

### Fixed

- stochastic fade-out theory, Erlang-C overflow, CSV check and fit-bound defects

## [1.3.0] - 2026-08-24

### Added

- decision-theory, demographic/actuarial and spatial-statistics lenses
- report benchmark runner
- machine-readable fitting output
- local Gradio playground
- project-management domain pack

## [1.2.0] - 2026-08-24

### Added

- reliability, statistical-process-control and thermodynamic lenses
- additional worked examples and domain packs
- benchmark dataset/scoring rubric
- CSV quality pre-check

## [1.1.0] - 2026-08-24

### Added

- game-theory, causal-inference and information-theory lenses
- expanded archetype catalog and worked examples
- model-comparison diagnostics, report indexing and GitHub Pages

## [1.0.0] - 2026-08-24

First tagged release: multi-perspective modeling workflow, rigor ladder, standardized report, bundled validation/fitting/sweep tools, worked examples and GitHub Actions CI.

[1.12.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.12.2
[1.12.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.12.1
[1.12.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.12.0
[1.11.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.2
[1.11.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.1
[1.11.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.11.0
[1.10.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.10.0
[1.9.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.9.0
[1.8.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.8.0
[1.7.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.7.0
[1.6.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.6.0
[1.5.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.5.0
[1.4.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.4.1
[1.4.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.4.0
[1.3.2]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.2
[1.3.1]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.1
[1.3.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.3.0
[1.2.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.2.0
[1.1.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.1.0
[1.0.0]: https://github.com/Furox-Art/axiomize/releases/tag/v1.0.0