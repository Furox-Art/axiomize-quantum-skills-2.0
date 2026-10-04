# Security Policy

## Supported versions

The latest published Axiomize release is the supported line. Security fixes are developed on
protected branches and released as patch versions when they affect distributed code.

| Version | Supported |
|---|---|
| 1.2.x | yes |
| < 1.2 | no |

A fix affecting distributed runtime behavior ships as a patch version built and tested from
the final merged commit on `main`. Unmerged branch artifacts are not release evidence.

## Reporting a vulnerability

Please do not publish an exploit or a sensitive reproduction in a public issue.


**Current state of this repository:** GitHub's private vulnerability reporting is **not
enabled** here. Verified against the GitHub API while this paragraph was written:

```
GET /repos/Furox-Art/axiomize-quantum-skills-2.0/private-vulnerability-reporting
{"enabled":false}
```

So `https://github.com/Furox-Art/axiomize-quantum-skills-2.0/security/advisories/new`
will not open a private channel for you. Until the maintainer enables it, use one of these
instead:

1. **Preferred:** open a regular issue that contains only a one-line summary with no
   exploit detail and a pointer such as "contact me via my GitHub profile to arrange a
   private channel", then continue in private through the reporter's GitHub profile.
2. **Alternative:** if you have an existing private channel with the maintainer
   (`@Furox-Art`), use it directly.

We are aware this is weaker than private advisory reporting and are working on it. The
maintainer can close the gap for everyone with one settings change: **Settings ->
Code security -> Security -> Enable private vulnerability reporting.** Once that is on,
this section should be replaced with a direct link to the advisories endpoint.

Whatever route you use, please include:

- the affected version (`pip show axiomize-quantum-skills-2.0`) and the commit if you built
  from source;
- the entry point — CLI subcommand, MCP tool, or REST route;
- a minimal reproduction;
- the impact you observed;
- any mitigation you propose.

Reports are evaluated against the actual trust boundary: Model IR, REST/MCP inputs, provider
endpoints, generated-code execution, formal-tool adapters, file paths, and document
conversion are all treated as untrusted-input surfaces unless explicitly documented
otherwise.

## Supply chain

Both registries publish by OIDC trusted publishing, and **both attach a build
attestation**. Three mechanisms are easy to confuse, and only the third is build
provenance:

| Mechanism | Proves | Does **not** prove |
|---|---|---|
| `dist.integrity` / `digests.sha256` | The bytes you received are the bytes that were published. | How they were built. |
| npm `dist.signatures` | The **registry** signed the packument; the metadata was not altered in transit. A transport signature, **not** provenance. | Anything about the build. npm signs every package. |
| Build attestation | A named CI workflow, repository and commit produced the artifact. | That the build was correct. |

Verify by hand:

```bash
# npm: two bundles, including a full SLSA v1 build provenance statement
curl -s https://registry.npmjs.org/-/npm/v1/attestations/axiomize-quantum-skills-2.0@1.2.1

# PyPI: one bundle per file, predicate https://docs.pypi.org/attestations/publish/v1
curl -s https://pypi.org/integrity/axiomize-quantum-skills-2.0/1.2.1/axiomize_quantum_skills_2_0-1.2.1-py3-none-any.whl/provenance
```

PyPI serves attestations **per file**, so the path ends in `/<filename>/provenance`.
`https://pypi.org/integrity/axiomize-quantum-skills-2.0/1.2.1/` is not an endpoint and
returns `404`; that means "no such URL", not "no attestation".

If you are triaging a report about a tampered artifact, the npm or PyPI attestation is
where the build identity is; the digest only tells you whether the bytes moved.
[docs/publishing-checklist.md](docs/publishing-checklist.md#supply-chain) has the field
tables and the trusted-publisher conditions.

## Security model

Axiomize distinguishes three classes of execution:

1. **Deterministic scientific expressions** are parsed through a restricted mathematical
   grammar and explicit symbol namespace.
2. **Potentially expensive computations** require approval when applicable and are always
   subject to non-bypassable hard resource ceilings.
3. **Arbitrary code / theorem elaboration** is not an operating-system sandbox. It requires
   explicit trust and runs with reduced environment exposure, time limits, and
   process/resource controls where the platform supports them.

<Network-facing REST service binding is loopback-only by default. Remote binding requires an
explicit opt-in and a bearer token of at least 16 characters; pass the token via the
`AXIOMIZE_REST_TOKEN` environment variable (or `--auth-token-env`) rather than
`--auth-token`, so it does not end up in shell history. File-backed run inspection is
confined to the configured run root.

Fuller detail, including what is explicitly out of scope, is in
[docs/security.md](docs/security.md), [docs/security-non-goals.md](docs/security-non-goals.md)
and [docs/security-maintenance.md](docs/security-maintenance.md). The 1.11.2 hardening pass
is recorded in [docs/security-audit-1.11.2.md](docs/security-audit-1.11.2.md).

## REST server trust boundary

The REST server binds `127.0.0.1` by default and **never** serves without a
bearer token, including on loopback.

### Why loopback still requires a token

A loopback bind is not a private channel. Any process on the host, and any web
page the user has open, can send a request to `http://127.0.0.1:<port>`. A
browser refuses to *read* a cross-origin response, but it will *send* a
"simple" request whose `Content-Type` is `text/plain` without a CORS preflight.
An unauthenticated `POST /v1/solve` is therefore reachable from a web page, and
this API exposes solve, fit, falsify and approval-gated Monte Carlo routes.

Two independent gates close that:

1. **`Content-Type` is checked before authentication.** A request declaring
   `text/plain`, `application/x-www-form-urlencoded`, `multipart/form-data` or
   `text/html` is refused with `415`. This API only speaks JSON, so a forged
   cross-origin request is rejected as malformed before any credential
   comparison happens.
2. **Every mutating request requires a token.** When the operator supplies no
   token, `start_server` mints a 256-bit one (`secrets.token_urlsafe(32)`) and
   exposes it as `server.generated_token`. Requests must present it as
   `Authorization: Bearer <token>` or `X-Axiomize-Token: <token>`.

### Read gating

`GET` routes require the token when — and only when — the operator supplied
their own `auth_token`, or when `require_token_for_reads=True` is passed
explicitly. When Axiomize generated the token itself, read-only discovery stays
open so the local workflow and the release smoke contract work unchanged.

**Known residual risk.** In that default loopback mode, recorded run contents
and results under `--run-root` are readable by other local processes and user
accounts. A browser cannot exploit this, because it cannot read a cross-origin
response at all, but a co-resident process can. Operators who share a host
should supply an explicit `auth_token`, which turns on read gating too.

### Overriding the default

| Goal | Flag | Notes |
| --- | --- | --- |
| Authenticate with a chosen secret | `--auth-token <value>` | Also turns on read gating; `server.generated_token` is then `None` |
| Authenticate from the environment | `--auth-token-env <NAME>` | Default name `AXIOMIZE_REST_TOKEN`; keeps the secret out of argv and shell history |
| Accept a generated token | *(nothing)* | `axiomize serve` prints the generated token to **stderr**, once |
| Protect reads with a generated token | `require_token_for_reads=True` | Library callers only; implies an operator token when passed as a flag |
| Bind a non-loopback address | `--host <addr> --allow-remote` | Also requires a token of at least 16 characters |

`axiomize serve` prints the generated token on stderr so the local workflow
stays usable:

```console
$ axiomize serve
axiomize REST v1 on http://127.0.0.1:8765
no --auth-token was supplied; mutating routes require this generated token:
  Authorization: Bearer <generated>
```

Callers embedding the server as a library read `server.auth_token` (the
effective token) or `server.generated_token` (set only when Axiomize minted it).

`start_server` is the only supported way to construct the server. A server
built by calling `BoundedThreadingHTTPServer` directly with `auth_token=None`
**fails closed** on mutating routes with `401` rather than serving an
unauthenticated surface.

## Run-path confinement

Any function that touches the filesystem on behalf of a caller-supplied
identifier confines it with `axiomize.runs.state.resolve_run_directory`, which
rejects absolute paths, NUL bytes, and any component that escapes the root.

Confinement is applied **in the service layer, not only at the transport edge**,
so a new caller cannot bypass it:

- `compare_runs_service(payload, *, run_root=None)` confines `before_dir` and
  `after_dir` when `run_root` is supplied. Both the REST and MCP transports
  always supply it. Passing `run_root=None` is an explicit trust decision
  reserved for local operator use (`axiomize compare-runs` on the operator's own
  machine, where the paths came from the command line, not from a network peer).
- `import_run(bundle, dest, *, run_root=None)` accepts **only** `.zip`
  bundles. `shutil.unpack_archive` dispatches on the file suffix, and its
  tar/tar.gz path calls `tarfile.extractall` without a member filter, which
  writes outside the destination on Python 3.10-3.13. Every member is also
  resolved and confirmed to stay inside the destination before anything is
  written, so a rejected bundle leaves no partial output.

## Runtime dependency policy

`axiomize.dependency_policy` is a fail-closed, data-driven policy over the
resolved dependency graph. It reads installed versions with
`importlib.metadata` and imports nothing it judges, so it is safe to call from
`start_server` and from CI. It performs no network access; the floors are
reviewed by hand against an advisory database.

- **`FORBIDDEN_IN_RUNTIME`** — `gradio` must not be present in the runtime
  graph at all. Gradio is a local web-UI framework used only by the optional
  playground demo and is not imported by `axiomize`. It carries a large
  advisory history (SSRF, path traversal, arbitrary file upload and deletion,
  CORS-origin validation bypass, open redirect, zip-bomb DoS) and **multiple
  advisories are unpatched at every released version**, so no version bound can
  make it safe to keep. Presence is a `critical` finding regardless of version.
- **`RUNTIME_MINIMUMS`** — `pytest >= 9.0.3`, the first release containing the
  fix for CVE-2025-71176 / GHSA-6w46-j5rx-g56g (vulnerable tmpdir handling).
  A lower resolved version is a `high` finding.

`enforce_dependency_policy()` raises `InsecureDependencyGraph` listing every
finding. An unparsable version is treated as *not* satisfying a floor, so an
unknown environment is reported rather than assumed clean.

> **Open action for the `pyproject.toml` owner.** The policy is the runtime
> backstop; the declaration itself is still the primary control. As of `main`
> at `bddc37b` both declarations are still open, so neither is optional:
> 1. Remove `gradio>=4.0` from the `playground` extra in `pyproject.toml`. If
>    the playground must stay installable, move it to a separate distribution so
>    Gradio can never enter the runtime graph.
> 2. Raise the `pytest>=8.0` floor to `pytest>=9.0.3` in
>    `requirements-test.txt` to match `RUNTIME_MINIMUMS`.

## Reporting something that is not a vulnerability

Bugs and documentation errors belong in public issues. Use the issue templates so the
report is actionable:

| Template | Use it for |
|---|---|
| Bug report | something in the engine, tools, or skills is wrong |
| Feature request | a capability you want |
| Question | you need help using what already exists |

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).
