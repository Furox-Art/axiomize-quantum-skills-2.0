#!/usr/bin/env python3
"""Guard every supply-chain provenance/attestation claim in the docs.

Why this exists
---------------
Three different mechanisms get blurred into the single word "attested":

1. a **digest** (``dist.integrity`` / ``digests.sha256``) -- proves the bytes you
   received are the bytes that were published, and nothing about how they were built;
2. npm's ``dist.signatures`` -- a **registry transport signature** over the
   packument, present for every package whether or not CI ever built it;
3. a **build attestation** (Sigstore/in-toto on npm, PEP 740 on PyPI) -- the only one
   of the three that names a CI workflow, repository and commit.

Measured state of this project, re-checkable with ``--online``:

==========  ==============  ==============================================
Channel     Attested?       Endpoint
==========  ==============  ==============================================
npm         yes, 2 bundles  ``/-/npm/v1/attestations/<pkg>@<ver>`` -> 200
PyPI        yes, per file   ``/integrity/<proj>/<ver>/<file>/provenance`` -> 200
==========  ==============  ==============================================

Rules enforced on the prose of the documents that state *current* facts:

- a supply-chain provenance/attestation claim must name a channel, because a claim
  naming no channel cannot be checked against either registry;
- it must state a definite status, not a vague gesture;
- ``dist.signatures`` must never be presented as attestation or provenance, anywhere;
- a version called "current" must be the pinned current version;
- if a non-``/provenance`` PyPI integrity URL is quoted at all, the docs must say that
  ``404`` is a missing endpoint rather than an absent attestation. Reading it the other
  way produced a real false claim in this repository, which is why it is a rule.

Deliberate exclusions, because they are not the same claim: ``docs/benchmark.md`` uses
"provenance" for *measurement* lineage, ``docs/worked-examples.md`` and
``docs/example-gallery.md`` for *parameter* lineage, and ``CHANGELOG.md`` records what was
written when. The trigger below requires a supply-chain token, so the first two are
skipped, and the changelog is scanned only for the ``dist.signatures`` blur.

Runnable four ways::

    python docs/check_attestation_claims.py             # scan the repo docs
    python docs/check_attestation_claims.py --online    # also re-measure both registries
    python docs/check_attestation_claims.py --json     # machine-readable
    python docs/check_attestation_claims.py --self-test # negative control

``--self-test`` is the negative control: it feeds this guard deliberately false claim texts
and fails if any is accepted. A guard that cannot be shown to reject a known lie is not a
guard.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Bumped together with the release.
CURRENT_VERSION = "1.2.1"

DIST = "axiomize_quantum_skills_2_0"
PROJECT = "axiomize-quantum-skills-2.0"

#: Documents that state current facts. Strict rules apply to their prose.
CURRENT_FACT_DOCS = ("README.md", "SECURITY.md")
CURRENT_FACT_GLOBS = ("docs/**/*.md",)

#: History. Only the dist.signatures blur rule applies.
HISTORY_DOCS = ("CHANGELOG.md",)

#: A line is about supply-chain provenance only with a supply-chain token present. This
#: is what keeps "provenance for every number" and "parameter provenance" out.
SUPPLY_CHAIN = re.compile(
    r"attestation|attested|sigstore|in-toto|\bslsa\b|pep[ -]?740|"
    r"\bnpm\b|\bpypi\b|registry|tarball|dist\.signatures|dist\.integrity|trusted publish",
    re.I,
)

#: The word that carries the claim, on top of the supply-chain context.
CLAIM = re.compile(r"provenance|attestation|attested|sigstore|in-toto|\bslsa\b|pep[ -]?740", re.I)

#: A claim must name a channel. "both registries" and "each channel" are explicit
#: multi-channel scope and are just as checkable as naming one.
CHANNEL = re.compile(
    r"\bpypi\b|\bnpm\b|both registr|each registr|either registr|both channels?|per channel|"
    r"each channel",
    re.I,
)

#: A heading names the channel for everything under it, so a paragraph beneath
#: ``### npm`` does not have to repeat the word.
HEADING_CHANNEL = re.compile(r"^#{1,6}\s*(.*)$")

#: A claim must be definite. Copulas are deliberately not status words: "the npm
#: attestation status is complicated" has a copula and no status, which is the failure.
STATUS_NEGATIVE = re.compile(
    r"\b(?:no|not|none|never|without|absent|absence|404|pending|unattested|cannot|can't|"
    r"neither|nor|only|do not|does not|fails?)\b",
    re.I,
)
STATUS_AFFIRMATIVE = re.compile(
    r"\b(?:attested|yes|carry|carries|carried|serves|attaches|publishes|provides|exists|"
    r"returns|verified|evidence|same|match|matches|equal|equals|identical|agree|agrees)\b",
    re.I,
)

NEGATION = re.compile(
    r"\b(?:not|no|never|rather than|instead|is not|does not|cannot|unrelated|transport|"
    r"neither|instead of)\b",
    re.I,
)

ONLINE_EXPECTATIONS = {
    "npm": (f"https://registry.npmjs.org/-/npm/v1/attestations/{PROJECT}@{CURRENT_VERSION}", 200),
    "pypi": (
        f"https://pypi.org/integrity/{PROJECT}/{CURRENT_VERSION}/{DIST}-{CURRENT_VERSION}-py3-none-any.whl/provenance",
        200,
    ),
}


def _strip_code_fences(lines: list[str]) -> list[bool]:
    inside = False
    flags: list[bool] = []
    for line in lines:
        if line.lstrip().startswith("```"):
            inside = not inside
            flags.append(True)
            continue
        flags.append(inside)
    return flags


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|")


def current_fact_files() -> list[Path]:
    found: list[Path] = []
    for rel in CURRENT_FACT_DOCS:
        path = ROOT / rel
        if path.is_file():
            found.append(path)
    for pattern in CURRENT_FACT_GLOBS:
        for path in sorted(ROOT.glob(pattern)):
            if path.is_file() and path not in found:
                found.append(path)
    return found


def history_files() -> list[Path]:
    return [ROOT / rel for rel in HISTORY_DOCS if (ROOT / rel).is_file()]


def _logical_units(lines: list[str]) -> list[tuple[int, str, str]]:
    """Group wrapped prose into logical units.

    Markdown hard-wraps at ~80 columns, so a rule that only inspected one physical line
    would demand the channel word and the status word land together -- a formatting rule,
    not a truth rule.
    """
    in_code = _strip_code_fences(lines)
    units: list[tuple[int, str, str]] = []
    buffer: list[str] = []
    start = 0

    def flush() -> None:
        nonlocal buffer, start
        if buffer:
            units.append((start, "prose", " ".join(buffer)))
            buffer = []

    for index, line in enumerate(lines, 1):
        if in_code[index - 1]:
            flush()
            units.append((index, "code", line))
            continue
        stripped = line.strip()
        if not stripped:
            flush()
            continue
        if _is_table_row(line) or stripped.startswith("#"):
            flush()
            units.append((index, "table" if _is_table_row(line) else "other", line))
            continue
        if stripped.startswith(("-", "*", ">", "|")) and buffer:
            flush()
        if not buffer:
            start = index
        buffer.append(stripped)
    flush()
    return units


def _heading_channel(units: list[tuple[int, str, str]]) -> str:
    """Channels named by headings, in order, for scope inheritance.

    Returns a concatenation of every heading seen so far. A paragraph under
    ``### npm`` inherits npm; one under ``## Supply chain`` inherits whatever the
    section's own headings named. Accumulating rather than resetting keeps a claim in
    a chapter intro scoped by the chapter title.
    """
    channels: list[str] = []
    for _number, kind, text in units:
        if kind == "other":
            match = HEADING_CHANNEL.match(text)
            if match:
                title = match.group(1)
                if re.search(r"\bnpm\b", title, re.I):
                    channels.append("npm")
                if re.search(r"\bpypi\b", title, re.I):
                    channels.append("PyPI")
    return " ".join(channels)


def _prose_problems(path: Path) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    units = _logical_units(path.read_text(encoding="utf-8").splitlines())
    inherited = _heading_channel(units)
    problems: list[str] = []
    for number, kind, text in units:
        if kind != "prose":
            continue
        if not (SUPPLY_CHAIN.search(text) and CLAIM.search(text)):
            continue
        scoped = f"{text} {inherited}"
        if not CHANNEL.search(scoped):
            problems.append(
                f"{rel}:{number}: supply-chain provenance/attestation claim names no "
                f"channel (PyPI or npm), so it cannot be checked against either: {text}"
            )
        elif not (STATUS_NEGATIVE.search(text) or STATUS_AFFIRMATIVE.search(text)):
            problems.append(
                f"{rel}:{number}: supply-chain provenance/attestation claim states no "
                f"definite status: {text}"
            )
    return problems


def _signature_problems(path: Path) -> list[str]:
    """The dist.signatures blur rule, applied everywhere including code blocks.

    Two passes, because the two contexts fail differently:
    - prose is checked as joined logical units, so a sentence that hard-wraps between
      ``dist.signatures`` and its negation is not mistaken for an unqualified claim;
    - code blocks are checked line by line, minus shell lines, because
      ``npm view ... dist.signatures`` is an instruction to inspect, not a claim.
    """
    rel = path.relative_to(ROOT).as_posix()
    command = re.compile(r"^\s*(?:\$\s*)?(?:npm|curl|python|node|gh)\s")
    problems: list[str] = []

    def flagged(text: str, number: int) -> bool:
        return "dist.signatures" in text and not NEGATION.search(text)

    for number, kind, text in _logical_units(path.read_text(encoding="utf-8").splitlines()):
        if kind == "prose" and flagged(text, number):
            problems.append(
                f"{rel}:{number}: dist.signatures presented without a negation; it is a "
                f"registry transport signature and never build provenance: {text}"
            )
        elif kind == "code" and flagged(text, number) and not command.match(text):
            problems.append(
                f"{rel}:{number}: dist.signatures presented without a negation; it is a "
                f"registry transport signature and never build provenance: {text.strip()}"
            )
    return problems


def _version_problems(path: Path) -> list[str]:
    """Flag a stale version only where that version is the one called current."""
    rel = path.relative_to(ROOT).as_posix()
    problems: list[str] = []
    for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        segments = line.split("|") if _is_table_row(line) else [line]
        for segment in segments:
            for sentence in re.split(r"(?<=[.!?])\s+", segment):
                if "current" not in sentence.lower():
                    continue
                if re.search(r"\b(?:was|were|superseded|no longer|not the)\b", sentence, re.I):
                    continue
                for raw in re.findall(r"`(\d+\.\d+\.\d+)`|\b(\d+\.\d+\.\d+)\b", sentence):
                    found = raw[0] or raw[1]
                    if found and found != CURRENT_VERSION:
                        problems.append(
                            f"{rel}:{index}: calls {found} the current release; the current "
                            f"release is {CURRENT_VERSION}: {sentence.strip()}"
                        )
    return sorted(set(problems))


def _pypi_404_trap_problems(path: Path) -> list[str]:
    """A PyPI integrity 404 means 'no such URL', not 'no attestation'."""
    text = path.read_text(encoding="utf-8")
    if "pypi.org/integrity" not in text:
        return []
    if not re.search(r"pypi\.org/integrity/[^\s)`\"']*/(?![^\s)`\"']*provenance)", text):
        return []
    if re.search(r"not an endpoint|no such URL|means .{0,40}no such|absence of a collection|not evidence", text, re.I):
        return []
    return [
        f"{path.relative_to(ROOT).as_posix()}: quotes a PyPI integrity URL without "
        f"'/provenance'. That 404 means 'no such URL', not 'no attestation', and the docs "
        f"must say so."
    ]


def findings(strict_paths: list[Path] | None = None, all_paths: list[Path] | None = None) -> list[str]:
    problems: list[str] = []
    strict = strict_paths if strict_paths is not None else current_fact_files()
    everything = all_paths if all_paths is not None else (strict + history_files())
    for path in strict:
        problems += _prose_problems(path)
        problems += _version_problems(path)
        problems += _pypi_404_trap_problems(path)
    for path in everything:
        problems += _signature_problems(path)
    return problems


def _status(url: str, timeout: float = 40.0) -> int | None:
    request = urllib.request.Request(url, headers={"User-Agent": "axiomize-attestation-guard"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def online_problems() -> list[str]:
    problems: list[str] = []
    for channel, (url, expected) in ONLINE_EXPECTATIONS.items():
        observed = _status(url)
        if observed is None:
            problems.append(f"{channel}: could not reach {url} (network error); verdict withheld")
        elif observed != expected:
            problems.append(
                f"{channel}: {url} returned HTTP {observed}, the docs state {expected}. "
                f"Either the registry changed or the docs are stale."
            )
        else:
            print(f"  {channel:5} HTTP {observed} as documented   {url}")
    return problems


NEGATIVE_CONTROLS: tuple[tuple[str, str], ...] = (
    ("unscoped attestation claim", "The release is attested, so you can trust it.\n"),
    ("dist.signatures presented as provenance", "npm `dist.signatures` is a provenance attestation for the tarball.\n"),
    ("stale version called current", f"`1.2.0` is the current release on both registries.\n"),
    ("vague gesture, no definite status", "npm and PyPI attestation status is complicated.\n"),
    ("attestation claimed with no channel", "Every artifact carries an attestation; verify before installing.\n"),
    ("PyPI 404 quoted without the wrong-URL-shape caveat",
     "Check https://pypi.org/integrity/axiomize-quantum-skills-2.0/1.2.1/ for the attestation.\n"),
)

POSITIVE_CONTROL = (
    "PyPI publishes every artifact with a PEP 740 provenance attestation; npm carries\n"
    "Sigstore attestations including SLSA v1, and its attestations endpoint returns `200`.\n"
)

#: Must be skipped, not flagged: same word, different meaning.
NON_SUPPLY_CHAIN: tuple[tuple[str, str], ...] = (
    ("measurement provenance", "### Provenance\n"),
    ("parameter provenance", "**Parameter provenance.** Examples tag each parameter.\n"),
)


def self_test() -> int:
    failures: list[str] = []
    scratch = ROOT / "docs" / ".attestation-guard-selftest.md"
    try:
        for description, text in NEGATIVE_CONTROLS:
            scratch.write_text(text, encoding="utf-8")
            if not findings(strict_paths=[scratch], all_paths=[scratch]):
                failures.append(f"  ACCEPTED a false claim ({description}): {text.strip()}")
            else:
                print(f"  rejected: {description}")
        scratch.write_text(POSITIVE_CONTROL, encoding="utf-8")
        if not findings(strict_paths=[scratch], all_paths=[scratch]):
            print("  accepted: a correct channel-scoped claim")
        else:
            failures.append("  REJECTED a correct, channel-scoped claim: the guard is too strict")
        for description, text in NON_SUPPLY_CHAIN:
            scratch.write_text(text, encoding="utf-8")
            if findings(strict_paths=[scratch], all_paths=[scratch]):
                failures.append(f"  false positive: flagged '{description}': {text.strip()}")
            else:
                print(f"  correctly skipped: {description}")
    finally:
        scratch.unlink(missing_ok=True)
    if failures:
        print("FAIL negative control:")
        print("\n".join(failures))
        return 1
    print(
        f"OK: {len(NEGATIVE_CONTROLS)} false claims rejected, "
        f"{len(NON_SUPPLY_CHAIN)} unrelated senses skipped, correct claim accepted"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard supply-chain attestation claims.")
    parser.add_argument("--online", action="store_true", help="also re-measure both registries")
    parser.add_argument("--self-test", action="store_true", help="run the negative control only")
    parser.add_argument("--json", action="store_true", help="emit findings as JSON")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()

    strict = current_fact_files()
    everything = strict + history_files()
    problems = findings(strict_paths=strict, all_paths=everything)
    if args.online:
        print(f"re-measuring both registries for {CURRENT_VERSION}:")
        problems += online_problems()

    if args.json:
        print(json.dumps({
            "current_version": CURRENT_VERSION,
            "strict": [p.relative_to(ROOT).as_posix() for p in strict],
            "problems": problems,
        }, indent=2))
        return 1 if problems else 0

    print(f"current version pinned to {CURRENT_VERSION}")
    print(f"scanned {len(strict)} current-fact file(s), {len(everything) - len(strict)} history file(s)")
    if problems:
        print(f"\nFAIL: {len(problems)} problem(s):")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("\nPASS: every supply-chain provenance claim names a channel and a definite status")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())