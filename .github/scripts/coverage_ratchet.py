#!/usr/bin/env python3
"""Branch-coverage ratchet: the floor may rise, never fall.

Why a ratchet file rather than a bare ``--cov-fail-under``: that flag alone
cannot distinguish "coverage went up" from "the floor was quietly lowered in the
same PR that lost coverage". This script makes lowering the floor an explicit,
failing act.

Behaviour
---------
* Reads the required floor from ``.github/coverage-floor.txt``.
* Runs ``pytest`` with the coverage settings declared in ``pyproject.toml``
  (``[tool.coverage.*]``) and the requested marker filter.
* Fails when the measured total is below the floor.
* When the measured total is above the floor, prints the new value and how to
  commit it, but does not rewrite the file: a human decides whether the jump
  came from real new tests.
* Fails when the floor in this branch is *lower* than the floor recorded on the
  base branch, which is the case this script exists to catch.

Usage::

    python .github/scripts/coverage_ratchet.py
    python .github/scripts/coverage_ratchet.py --pytest-args "-m 'not network'"
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FLOOR_FILE = ROOT / ".github" / "coverage-floor.txt"


def _parse_floor(text: str) -> float | None:
    """Read the floor from the first non-comment, non-blank line.

    The file is mostly prose that mentions numbers ("the old 68%"), so scanning
    for the first number anywhere in the text would pick up a figure from a
    comment and silently gate on the wrong value.
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)", stripped)
        if match:
            return float(match.group(1))
    return None


def read_floor() -> float:
    floor = _parse_floor(FLOOR_FILE.read_text(encoding="utf-8"))
    if floor is None:
        raise SystemExit(
            f"FAIL: {FLOOR_FILE.relative_to(ROOT)} has no bare numeric floor line"
        )
    return floor


def read_base_floor() -> float | None:
    """Return the floor recorded on the merge base, if it can be determined.

    Uses the git history rather than an API call so the check also works in a
    fork or a local clone. Returns None when the base is unavailable, which
    downgrades this to the "measured >= floor" check alone.
    """
    for ref in ("origin/main", "main", "HEAD~1"):
        try:
            proc = subprocess.run(
                ["git", "show", f"{ref}:.github/coverage-floor.txt"],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                check=False,
                timeout=60,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        base = _parse_floor(proc.stdout)
        if base is not None:
            return base
    return None


def measured_total() -> float | None:
    """Run the suite and return the measured branch-coverage percentage."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q", "--cov", "--cov-report="],
        cwd=str(ROOT),
        check=False,
        env={**os.environ, "PYTEST_ADDOPTS": ""},
    )
    if proc.returncode != 0:
        # pytest already printed why; a collection error or a failing test is
        # not a coverage verdict and must not be silently treated as one.
        return None
    report = subprocess.run(
        [sys.executable, "-m", "coverage", "report", "--precision=2"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )
    match = re.search(r"^TOTAL\s+\d+\s+\d+\s+\d+\s+\d+\s+([0-9.]+)%", report.stdout, re.MULTILINE)
    if not match:
        return None
    return float(match.group(1))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the measured value into the floor file (only when it is higher)",
    )
    parser.add_argument(
        "--skip-base-check",
        action="store_true",
        help="do not compare against the base branch (used when there is no base)",
    )
    args = parser.parse_args(argv)

    try:
        floor = read_floor()
    except SystemExit as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"required floor : {floor:.2f}%")

    if not args.skip_base_check:
        base = read_base_floor()
        if base is not None:
            print(f"base floor     : {base:.2f}%")
            if floor < base:
                print(
                    f"FAIL: coverage floor was lowered from {base:.2f}% to {floor:.2f}%.\n"
                    "Coverage is a ratchet: the floor may be raised, never lowered. If a "
                    "code deletion legitimately reduces coverage, raise this floor in a "
                    "separate, explained change.",
                    file=sys.stderr,
                )
                return 1
        else:
            print("base floor     : <unavailable, ratchet-down check skipped>")

    measured = measured_total()
    if measured is None:
        print("FAIL: could not determine measured coverage (see pytest output above)", file=sys.stderr)
        return 1

    print(f"measured       : {measured:.2f}%")
    if measured < floor:
        print(
            f"FAIL: measured {measured:.2f}% is below the {floor:.2f}% floor",
            file=sys.stderr,
        )
        return 1

    if measured > floor:
        new_floor = f"{measured:.2f}"
        if args.write:
            # Replace the bare numeric line only, leaving the prose intact: the
            # comment records why the floor is what it is and must survive.
            lines = FLOOR_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
            for index, line in enumerate(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    newline = "\n" if line.endswith("\n") else ""
                    lines[index] = new_floor + newline
                    break
            else:  # pragma: no cover - read_floor already rejected this file
                print("FAIL: no numeric floor line to update", file=sys.stderr)
                return 1
            FLOOR_FILE.write_text("".join(lines), encoding="utf-8")
            print(f"raised floor   : -> {new_floor}% (commit this file)")
        else:
            print(
                f"NOTE: {measured:.2f}% is above the floor. Re-run with --write to ratchet "
                f"the floor up to {new_floor}%."
            )

    print(f"PASS: {measured:.2f}% >= {floor:.2f}% required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
