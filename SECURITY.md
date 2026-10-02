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

## Security model

Axiomize distinguishes three classes of execution:

1. **Deterministic scientific expressions** are parsed through a restricted mathematical
   grammar and explicit symbol namespace.
2. **Potentially expensive computations** require approval when applicable and are always
   subject to non-bypassable hard resource ceilings.
3. **Arbitrary code / theorem elaboration** is not an operating-system sandbox. It requires
   explicit trust and runs with reduced environment exposure, time limits, and
   process/resource controls where the platform supports them.

Network-facing REST service binding is loopback-only by default. Remote binding requires an
explicit opt-in and a bearer token of at least 16 characters; pass the token via the
`AXIOMIZE_REST_TOKEN` environment variable (or `--auth-token-env`) rather than
`--auth-token`, so it does not end up in shell history. File-backed run inspection is
confined to the configured run root.

Fuller detail, including what is explicitly out of scope, is in
[docs/security.md](docs/security.md), [docs/security-non-goals.md](docs/security-non-goals.md)
and [docs/security-maintenance.md](docs/security-maintenance.md). The 1.11.2 hardening pass
is recorded in [docs/security-audit-1.11.2.md](docs/security-audit-1.11.2.md).

## Reporting something that is not a vulnerability

Bugs and documentation errors belong in public issues. Use the issue templates so the
report is actionable:

| Template | Use it for |
|---|---|
| Bug report | something in the engine, tools, or skills is wrong |
| Feature request | a capability you want |
| Question | you need help using what already exists |

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md).