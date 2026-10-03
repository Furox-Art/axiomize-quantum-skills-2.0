#!/usr/bin/env python3
"""Wait until a freshly published npm version is readable from the public registry.

Why this exists
---------------
``npm publish`` returns when the registry's **write** path accepts the upload. The
**read** path is served from a CDN that converges asynchronously. Probing the read
path immediately after the upload therefore reads pre-upload state, and a workflow
that treats "not visible on the next look" as a hard error reports a successful
release as a failed one.

That is not hypothetical. Release (npm) run 37120477453 published
``axiomize-quantum-skills-2.0@1.2.0`` successfully -- the upload completed, the
version is on the registry today, and it carries Sigstore + SLSA provenance whose
provenance statement names that exact run -- yet the workflow's six-attempt,
ten-second probe gave up at roughly 60 seconds and failed the job with:

    The upload completed but axiomize-quantum-skills-2.0@1.2.0 is not publicly
    visible after 6 attempts.

A sibling repository observed the same shape with a propagation delay of about
95 seconds. A 60-second budget cannot cover that.

Direct registry read instead of ``npm view``
--------------------------------------------
The decision is made from an HTTP GET of the packument, not from ``npm view``:

1. **No local cache.** ``npm view`` is served through npm's ``_cacache``. The probe
   would then answer a question about the runner's cache state rather than about
   the registry. A cached packument can report "absent" long after the CDN has the
   version -- the exact false negative this script exists to eliminate -- and can
   equally report "present" from a pre-upload snapshot.
2. **One request, one consistent document.** The packument carries both
   ``versions[<version>]`` and ``dist-tags.latest``. Reading them from one response
   avoids a torn read where the version is visible but the tag has not moved yet, or
   the reverse.
3. **Unambiguous failure classes.** HTTP says 404 (the registry answered, the
   version is absent) as opposed to 5xx or a connection error (the registry did not
   answer). ``npm view`` collapses all three into one non-zero exit, so a timeout
   report cannot say which happened.
4. **It is the path a consumer takes.** ``npm install`` reads this same packument
   from this same CDN, so reading it directly is the closest available proxy for
   "what would a consumer resolve right now".
5. **No new dependency.** Standard-library ``urllib`` only, and the workflow has
   already provisioned Python.

Freshness is requested with a ``Cache-Control: no-cache`` header, which asks
intermediaries to revalidate. No cache-busting query string is added: fragmenting
the CDN cache would make the probe less representative of what ``npm install``
sees, and would be abusive to a shared cache.

Failure policy
--------------
First match wins: the first attempt that reads the version present ends the loop.
If the budget is exhausted the script emits ``::warning::`` and **exits non-zero**.
A version that genuinely never appeared must fail the run, so this fails closed; a
version that is merely slow to propagate now gets several minutes to appear, and
the warning text says the upload itself was not rolled back.

Runnable directly, with no network access, for a local sanity check::

    python .github/scripts/wait_for_npm_visibility.py --help
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Protocol, Sequence, cast

DEFAULT_REGISTRY = "https://registry.npmjs.org"

#: Seconds to wait *after* a failed attempt. Twelve entries means twelve probes;
#: the sleep after the final probe is skipped, so eleven waits are performed.
#: Growing rather than flat, because the first few seconds after an upload are the
#: ones most likely to be answered from a warm-but-stale cache and the tail is where
#: a slow propagation actually lands. Total wait: 190s, i.e. a three-minute budget on
#: top of the request time, against an observed delay near 95s and a sibling
#: observation in the same order of magnitude.
DEFAULT_SCHEDULE: tuple[int, ...] = (5, 5, 10, 10, 15, 15, 20, 20, 25, 30, 35, 40)

#: Hard ceiling on the total wait, so a future edit to ``DEFAULT_SCHEDULE`` cannot
#: quietly push a release job past its ``timeout-minutes``.
MAX_TOTAL_WAIT_SECONDS = 600


class ProbeResult:
    """Outcome of a single read of the registry."""

    __slots__ = ("present", "latest", "detail")

    def __init__(self, present: bool, latest: str | None = None, detail: str = "") -> None:
        self.present = present
        self.latest = latest
        self.detail = detail

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"ProbeResult(present={self.present!r}, latest={self.latest!r}, detail={self.detail!r})"


@dataclass
class WaitOutcome:
    """What the poll concluded, for the caller and for tests."""

    ok: bool
    attempts: int
    waited_seconds: int
    latest: str | None = None
    warnings: list[str] = field(default_factory=list)
    detail: str = ""


def packument_url(package: str, registry: str = DEFAULT_REGISTRY) -> str:
    """Return the packument URL for ``package``.

    A scoped name's ``/`` must be percent-encoded or the request addresses a
    nonexistent path, so the slash is encoded while the package's own characters
    are left alone.
    """
    base = registry.rstrip("/")
    encoded = package.replace("/", "%2F") if package.startswith("@") else package
    return f"{base}/{encoded}"


class _Response(Protocol):
    """The part of an HTTP response this script reads.

    Deliberately not modelled as a context manager: the body is read once and the
    response closed in a ``finally``, which keeps the injected test double to a bare
    ``read``.
    """

    status: int

    def read(self) -> bytes: ...


class _Opener(Protocol):
    """Stand-in for ``urllib.request.urlopen``, injectable so tests need no network."""

    def __call__(self, request: urllib.request.Request, timeout: float) -> _Response: ...


def _fetch_packument(
    url: str,
    timeout: float,
    opener: _Opener | None = None,
) -> tuple[int, bytes]:
    """GET ``url`` and return ``(status, body)``.

    Separated from :func:`probe_registry` so the exception translation below can be
    tested without a network. ``opener`` is injectable for exactly that reason.
    """
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            # Ask the CDN to revalidate rather than answer from a warm cache.
            "Cache-Control": "no-cache",
            "User-Agent": "axiomize-release-visibility-probe",
        },
    )
    # urlopen is an overloaded stdlib callable rather than a plain function, so it
    # does not structurally match the Protocol; the cast is the single point where
    # the stdlib enters the injectable world.
    fetch = opener if opener is not None else cast("_Opener", urllib.request.urlopen)
    response = fetch(request, timeout=timeout)
    try:
        status = int(getattr(response, "status", 200) or 200)
        return status, response.read()
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def probe_registry(
    package: str,
    version: str,
    registry: str = DEFAULT_REGISTRY,
    timeout: float = 20.0,
    opener: _Opener | None = None,
) -> ProbeResult:
    """Read the packument once and report whether ``version`` is publicly visible.

    Every transport failure is turned into a "not visible yet" result rather than
    being allowed to escape. A registry read can fail transiently for reasons that
    have nothing to do with whether the publish landed, and the whole point of the
    poll is to retry through exactly those. Notably ``http.client.HTTPException`` --
    which includes ``RemoteDisconnected``, the shape a CDN returns when it drops a
    connection mid-response -- is *not* a ``urllib.error.URLError``, so catching
    only the urllib classes lets it escape and kill the release job on the first
    flaky read.
    """
    url = packument_url(package, registry)
    try:
        status, payload = _fetch_packument(url, timeout, opener)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            # The registry answered and this package is not there at all.
            return ProbeResult(False, None, f"HTTP 404 from {url}")
        return ProbeResult(False, None, f"HTTP {exc.code} from {url}")
    except urllib.error.URLError as exc:
        return ProbeResult(False, None, f"network error from {url}: {exc.reason}")
    except http.client.HTTPException as exc:
        # RemoteDisconnected, BadStatusLine, IncompleteRead and friends. Not a
        # URLError, so it needs its own arm or it escapes as a traceback.
        return ProbeResult(False, None, f"HTTP protocol error from {url}: {type(exc).__name__}: {exc}")
    except TimeoutError as exc:
        return ProbeResult(False, None, f"timed out after {timeout}s reading {url}: {exc}")
    except OSError as exc:
        # ConnectionResetError, ssl errors, and anything else the socket layer raises.
        return ProbeResult(False, None, f"transport error from {url}: {type(exc).__name__}: {exc}")

    if status != 200:
        return ProbeResult(False, None, f"HTTP {status} from {url}")

    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return ProbeResult(False, None, f"unparseable packument from {url}: {exc}")

    if not isinstance(document, dict):
        return ProbeResult(False, None, f"packument from {url} is not a JSON object")

    tags = document.get("dist-tags")
    latest = tags.get("latest") if isinstance(tags, dict) else None
    if not isinstance(latest, str):
        latest = None

    versions = document.get("versions")
    if not isinstance(versions, dict):
        # A packument without a versions map cannot contain the version.
        return ProbeResult(False, latest, f"packument from {url} has no versions map")

    if version in versions:
        return ProbeResult(True, latest, f"{package}@{version} present in packument")

    known = len(versions)
    return ProbeResult(
        False,
        latest,
        f"{package}@{version} absent from packument ({known} published version(s), latest={latest or '<none>'})",
    )


def wait_for_visibility(
    package: str,
    version: str,
    probe: Callable[[], ProbeResult],
    sleep: Callable[[float], None],
    schedule: Sequence[int] = DEFAULT_SCHEDULE,
    now: Callable[[], float] = time.monotonic,
    *,
    deadline_seconds: float | None = None,
) -> WaitOutcome:
    """Poll ``probe`` until the version appears or the budget runs out.

    ``probe`` and ``sleep`` are injected so the loop can be driven deterministically
    by the regression test with no network and no wall-clock delay.
    """
    waits = [int(s) for s in schedule]
    if deadline_seconds is None:
        deadline_seconds = sum(waits)
    if any(s < 0 for s in waits):
        raise ValueError("schedule entries must be non-negative")

    start = now()
    waited = 0
    attempts = 0
    last_detail = "no probe was made"

    for index in range(len(waits)):
        attempts += 1
        result = probe()
        last_detail = result.detail or last_detail
        elapsed = now() - start
        sys.stdout.write(f"attempt {attempts}: {last_detail} (t+{elapsed:.0f}s)\n")
        sys.stdout.flush()

        if result.present:
            return WaitOutcome(
                ok=True,
                attempts=attempts,
                waited_seconds=waited,
                latest=result.latest,
                detail=last_detail,
            )

        if index == len(waits) - 1:
            # Final probe: sleeping now could not change the answer.
            break

        pause = waits[index]
        if elapsed + pause > deadline_seconds:
            # The next sleep would overrun the budget; stop instead of sleeping past it.
            break
        sleep(pause)
        waited += pause

    warnings = [
        f"{package}@{version} was not publicly visible within the propagation budget "
        f"({attempts} attempt(s), {waited}s of waiting, limit {int(deadline_seconds)}s).",
        "The upload itself was NOT rolled back: `npm publish` had already returned "
        "success, so the version may well be on the registry and simply not yet "
        "replicated to the CDN read path.",
        f"Last probe result: {last_detail}",
        "Re-check with: "
        f"curl -sf https://registry.npmjs.org/{package} | head -c 400  "
        f"(or: npm view {package}@{version} version)",
    ]
    return WaitOutcome(
        ok=False,
        attempts=attempts,
        waited_seconds=waited,
        warnings=warnings,
        detail=last_detail,
    )


def emit_github_commands(outcome: WaitOutcome, package: str, version: str) -> None:
    """Write ``::warning::`` / ``::notice::`` annotations for the run log."""
    if outcome.ok:
        sys.stdout.write(
            f"::notice::{package}@{version} is publicly visible after "
            f"{outcome.attempts} attempt(s), {outcome.waited_seconds}s of waiting."
        )
        sys.stdout.write("\n")
        return
    for line in outcome.warnings:
        sys.stdout.write(f"::warning::{line}\n")
    sys.stdout.write(
        "::warning::Failing the run because a version that never became readable must "
        "not be reported as a successful release. If you have confirmed the version is "
        "present on the registry, re-run this workflow; the idempotency gate will skip "
        "the upload.\n"
    )
    sys.stdout.flush()


def append_step_summary(
    outcome: WaitOutcome,
    package: str,
    version: str,
    mode: str,
    path: str | None,
) -> None:
    """Append the release summary, matching the shape the workflow used to write."""
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("\n### npm release visibility\n\n")
            handle.write(f"- credential mode: `{mode}`\n")
            if mode == "token":
                handle.write("- provenance: **not generated** (token mode has no OIDC identity)\n")
            else:
                handle.write("- provenance: attached\n")
            handle.write(f"- published: `{package}@{version}`\n")
            if outcome.ok:
                handle.write(
                    f"- publicly visible after {outcome.attempts} attempt(s), "
                    f"{outcome.waited_seconds}s of waiting\n"
                )
                handle.write(f"- `latest` now: `{outcome.latest or '<none>'}`\n")
                if outcome.latest and outcome.latest != version:
                    handle.write(
                        f"\n`latest` points at `{outcome.latest}`, a different version. "
                        "That is expected when the registry already held a numerically "
                        "higher version; see the workflow header.\n"
                    )
            else:
                handle.write(
                    f"- **not visible within the budget**: {outcome.attempts} attempt(s), "
                    f"{outcome.waited_seconds}s of waiting\n"
                )
                handle.write(f"- last probe: {outcome.detail}\n")
                handle.write(
                    "\nThe upload completed; the read path had not converged. See the "
                    "warnings in the log.\n"
                )
    except OSError as exc:
        sys.stderr.write(f"could not append the step summary: {exc}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Poll the npm registry until a published version is publicly readable, "
            "failing closed if it never appears."
        )
    )
    parser.add_argument("--package", required=True, help="npm package name")
    parser.add_argument("--version", required=True, help="exact version to wait for")
    parser.add_argument("--registry", default=DEFAULT_REGISTRY, help="registry base URL")
    parser.add_argument(
        "--schedule",
        default=",".join(str(s) for s in DEFAULT_SCHEDULE),
        help="comma-separated seconds to wait after each failed attempt",
    )
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=None,
        help="override the total waiting budget; defaults to the sum of the schedule",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="per-request timeout")
    parser.add_argument("--mode", default="oidc", choices=("oidc", "token"), help="credential mode")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        schedule = tuple(int(part) for part in args.schedule.split(",") if part.strip())
    except ValueError as exc:
        sys.stderr.write(f"--schedule must be a comma-separated list of integers: {exc}\n")
        return 2
    if not schedule:
        sys.stderr.write("--schedule must contain at least one entry\n")
        return 2
    if sum(schedule) > MAX_TOTAL_WAIT_SECONDS:
        sys.stderr.write(
            f"--schedule waits {sum(schedule)}s, above the {MAX_TOTAL_WAIT_SECONDS}s ceiling; "
            "a release job cannot afford a longer poll\n"
        )
        return 2

    outcome = wait_for_visibility(
        args.package,
        args.version,
        probe=lambda: probe_registry(args.package, args.version, args.registry, args.timeout),
        sleep=time.sleep,
        schedule=schedule,
        deadline_seconds=args.budget_seconds,
    )

    emit_github_commands(outcome, args.package, args.version)
    append_step_summary(
        outcome,
        args.package,
        args.version,
        args.mode,
        os.environ.get("GITHUB_STEP_SUMMARY"),
    )

    if outcome.ok:
        sys.stdout.write(f"npm publication verified: {args.package}@{args.version}\n")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
