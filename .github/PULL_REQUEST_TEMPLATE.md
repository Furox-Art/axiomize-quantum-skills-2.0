# What does this PR change?

<!-- One paragraph. If it fixes an issue, end with "Closes #N". -->

## Type of change

- [ ] Bug fix
- [ ] New feature or capability
- [ ] Documentation only
- [ ] New perspective lens (see the contract in CONTRIBUTING.md)
- [ ] New worked example or benchmark case
- [ ] Tests only
- [ ] Build, CI or release tooling

## Checklist

- [ ] New/changed markdown passes `python skills/axiomize/tools/check_skill.py`
- [ ] Perspective files follow the contract in CONTRIBUTING.md (all four sections)
- [ ] Examples follow the 8-phase structure and include at least one rejected-lens rationale
- [ ] Benchmark cases: a matching `benchmarks/reports/<id>.md` exists and
      `python skills/axiomize/tools/benchmark_runner.py --case <id> --report <path>` exits 0
- [ ] Tool changes: sanity checks still exit non-zero on failure; default runtime < 60s
- [ ] Version bump (only if this is a release): `pyproject.toml`, `src/axiomize/__init__.py`,
      `.github/pypi-release-trigger`, `README.md` and `CHANGELOG.md` updated together, so
      `python .github/scripts/check_release_contract.py` passes
- [ ] No emojis in content; units stated wherever quantities appear

## If this touches documentation

- [ ] Every command in the docs was actually executed, and the platform and version are named
- [ ] Every relative link resolves; links out of `docs/` are absolute
- [ ] No benchmark number appears without script, version and commit
- [ ] No metric is hardcoded where a link to a live source would stay true
- [ ] New or renamed files are added to `mkdocs.yml` nav, and `mkdocs build --strict` is clean

## Verification

<!-- Paste the command output that shows this works, not a description of it. -->

```text
```

## Notes for the reviewer

<!-- Anything non-obvious, anything you deliberately left out, anything you are unsure about.
     Honest uncertainty is more useful here than confidence. -->