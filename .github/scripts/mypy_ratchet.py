#!/usr/bin/env python3
"""Type-check ratchet: findings may fall, never rise.

``src/axiomize`` and ``skills/axiomize/tools`` carry pre-existing type errors in
code this CI change does not own, so a plain ``mypy`` invocation would be red on
arrival and would train everyone to ignore it. A bare baseline file has the
opposite failure: it hides new errors of the same shape as the old ones.

This script therefore pins each tree to an exact count and fails when the count
grows, while printing the new findings so the cause is visible. Lowering a
number here is allowed only when the findings were actually removed, which the
diff of the tree shows.

The repository-owned Python under ``.github/scripts`` is held to zero with a
hard gate, because that is code this change is responsible for.

Usage::

    python .github/scripts/mypy_ratchet.py            # check
    python .github/scripts/mypy_ratchet.py --report   # counts only, never fails
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASELINE_FILE = ROOT / ".github" / "mypy-baseline.txt"

#: Held to zero. Owned by this repository's CI.
STRICT_TARGETS = (".github/scripts",)

#: Pinned to the recorded count. Owned by the library change stream.
BASELINED_TARGETS = ("src/axiomize", "skills/axiomize/tools")

ERROR_LINE = re.compile(r": error: ")


def _run_mypy(target: str) -> tuple[int, list[str]]:
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", target, "--no-pretty", "--no-error-summary"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    lines = [line for line in (proc.stdout + proc.stderr).splitlines() if ERROR_LINE.search(line)]
    return len(lines), lines


def _parse_baseline() -> dict[str, int]:
    """Read ``target count`` pairs from the baseline file."""
    entries: dict[str, int] = {}
    for line in BASELINE_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        target, _, count = stripped.rpartition(" ")
        try:
            entries[target.strip()] = int(count)
        except ValueError:
            raise SystemExit(
                f"FAIL: {BASELINE_FILE.relative_to(ROOT)} line is not '<target> <count>': {stripped!r}"
            ) from None
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        action="store_true",
        help="print counts without failing (used by the informational step)",
    )
    args = parser.parse_args(argv)

    baseline = _parse_baseline()
    failures: list[str] = []

    for target in STRICT_TARGETS:
        count, lines = _run_mypy(target)
        if count:
            failures.append(f"{target}: {count} type error(s), gate is zero\n    " + "\n    ".join(lines))
        else:
            print(f"mypy {target:28s} {count:>4} finding(s)  [gate: 0]  OK")

    for target in BASELINED_TARGETS:
        count, lines = _run_mypy(target)
        allowed = baseline.get(target)
        if allowed is None:
            failures.append(
                f"{target}: no baseline recorded in {BASELINE_FILE.relative_to(ROOT)}; "
                f"measured {count}"
            )
            print(f"mypy {target:28s} {count:>4} finding(s)  [no baseline]")
            continue
        if count > allowed:
            new = lines[allowed:]
            failures.append(
                f"{target}: {count} finding(s) exceeds the baseline of {allowed}\n"
                "    New findings:\n    " + "\n    ".join(new)
            )
            print(f"mypy {target:28s} {count:>4} finding(s)  [baseline: {allowed}]  FAIL")
        else:
            trend = "improved" if count < allowed else "at baseline"
            print(f"mypy {target:28s} {count:>4} finding(s)  [baseline: {allowed}]  OK ({trend})")

    if failures:
        if args.report:
            for failure in failures:
                print(f"REPORT: {failure}", file=sys.stderr)
            return 0
        print(f"FAIL: {len(failures)} type-check target(s) regressed:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print("PASS: no type-check target regressed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
