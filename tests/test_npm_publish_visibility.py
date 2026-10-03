"""Regression test for the npm publication visibility poll.

Release (npm) run 37120477453 published ``axiomize-quantum-skills-2.0@1.2.0``
successfully and then failed its own job: the six-attempt, ten-second probe gave
up at roughly 60 seconds, while the registry's read path needed about 95 seconds
to converge. A version that was already published was reported as unpublished.

``wait_for_visibility`` takes its probe and its sleep as arguments, so both
directions are testable here with no network and no wall-clock delay:

* **absent, then present** -- the slow-but-successful publish must be verified,
  not misreported;
* **never present** -- a version that truly never appeared must still fail closed,
  or the workflow would report success for a release that did not happen.

Runnable both under pytest and as a script::

    python tests/test_npm_publish_visibility.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))

from wait_for_npm_visibility import (  # noqa: E402
    DEFAULT_SCHEDULE,
    MAX_TOTAL_WAIT_SECONDS,
    ProbeResult,
    emit_github_commands,
    packument_url,
    probe_registry,
    wait_for_visibility,
)

PACKAGE = "axiomize-quantum-skills-2.0"
VERSION = "1.2.0"


class FakeClock:
    """Monotonic clock advanced only by the sleeps the poll actually performs."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def scripted_probe(script: list[ProbeResult]):
    """Return a probe replaying ``script``, repeating its final entry forever."""
    calls = {"n": 0}

    def probe() -> ProbeResult:
        index = min(calls["n"], len(script) - 1)
        calls["n"] += 1
        return script[index]

    probe.calls = calls  # type: ignore[attr-defined]
    return probe


# --------------------------------------------------------------------------
# Direction 1: absent, then present. The publish succeeded; the read path was
# merely slow. This must be verified.
# --------------------------------------------------------------------------


def test_absent_then_present_is_verified_not_misreported() -> None:
    """A slow-but-successful publish must not be reported as a failure.

    The absent run is kept up until the cumulative wait first exceeds the ~95
    seconds the registry actually took to converge on the day of the failure, so
    the present read lands on the earliest probe that could have seen it.
    """
    absent = ProbeResult(
        False,
        latest="2.0.0",
        detail=f"{PACKAGE}@{VERSION} absent from packument (1 published version(s), latest=2.0.0)",
    )
    present = ProbeResult(
        True,
        latest=VERSION,
        detail=f"{PACKAGE}@{VERSION} present in packument",
    )
    clock = FakeClock()
    schedule = DEFAULT_SCHEDULE

    # Find the first probe whose cumulative wait covers the observed delay.
    target = next(i for i in range(1, len(schedule)) if sum(schedule[:i]) >= 95)
    script = [absent] * target + [present]
    probe = scripted_probe(script)

    outcome = wait_for_visibility(
        PACKAGE,
        VERSION,
        probe=probe,
        sleep=clock.sleep,
        schedule=schedule,
        now=clock.time,
    )

    assert outcome.ok, "a version that appeared within the budget must be verified"
    assert outcome.attempts == target + 1, f"first match must win; took {outcome.attempts} attempts"
    assert probe.calls["n"] == target + 1, "the poll must stop at the first present read"
    assert outcome.latest == VERSION
    assert outcome.waited_seconds == sum(schedule[:target]), "must wait only between failures"
    assert outcome.waited_seconds >= 95, (
        f"budget must span the observed ~95s propagation delay; waits were {outcome.waited_seconds}s"
    )


def test_default_schedule_outlives_the_observed_propagation_delay() -> None:
    """The shipped schedule must cover the delay that broke the previous loop."""
    total = sum(DEFAULT_SCHEDULE)
    assert total > 95, f"total wait {total}s does not cover the observed ~95s delay"
    assert len(DEFAULT_SCHEDULE) >= 12, "the loop must make at least 12 probes"
    assert DEFAULT_SCHEDULE == tuple(sorted(DEFAULT_SCHEDULE)), "backoff must be non-decreasing"
    assert DEFAULT_SCHEDULE[-1] > DEFAULT_SCHEDULE[0], "backoff must actually grow"
    assert total <= MAX_TOTAL_WAIT_SECONDS
    # The old loop allowed six probes over 60 seconds and could not see a 95s
    # propagation at all. That is the regression this replaces.
    assert len(DEFAULT_SCHEDULE) > 6
    assert total > 60


def test_a_present_read_on_the_first_attempt_never_sleeps() -> None:
    probe = scripted_probe([ProbeResult(True, VERSION, "present")])
    clock = FakeClock()

    outcome = wait_for_visibility(
        PACKAGE, VERSION, probe=probe, sleep=clock.sleep, schedule=DEFAULT_SCHEDULE, now=clock.time
    )

    assert outcome.ok
    assert outcome.attempts == 1
    assert clock.slept == [], "a first-attempt hit must not sleep"


# --------------------------------------------------------------------------
# Direction 2: never present. The publish genuinely did not land, or the registry
# never answered. This must fail closed.
# --------------------------------------------------------------------------


def test_never_present_fails_closed_after_the_whole_budget() -> None:
    """A version that never appears must still exit non-zero.

    Otherwise the workflow would report a successful release for a publish that
    did not happen, which is the failure mode the original exit-1 guarded.
    """
    probe = scripted_probe(
        [ProbeResult(False, latest="2.0.0", detail=f"{PACKAGE}@{VERSION} absent from packument")]
    )
    clock = FakeClock()

    outcome = wait_for_visibility(
        PACKAGE, VERSION, probe=probe, sleep=clock.sleep, schedule=DEFAULT_SCHEDULE, now=clock.time
    )

    assert not outcome.ok, "a version that never appears must not be reported as verified"
    assert outcome.attempts == len(DEFAULT_SCHEDULE)
    # Every probe but the last is followed by a sleep; sleeping after the final
    # probe could not change the answer, so it is skipped.
    assert outcome.waited_seconds == sum(DEFAULT_SCHEDULE[:-1])
    assert probe.calls["n"] == len(DEFAULT_SCHEDULE), "must exhaust the schedule before giving up"
    assert outcome.warnings, "a deadline miss must explain itself"


def test_never_present_emits_warning_annotations_not_a_bare_error() -> None:
    """The log must say the upload was not rolled back, and still fail the run.

    The point of the ``::warning::`` wording is that a reader is told the release
    may be fine and the check was merely slow, while the job still goes red.
    """
    probe = scripted_probe([ProbeResult(False, None, "HTTP 404 from https://registry.npmjs.org/pkg")])
    clock = FakeClock()
    outcome = wait_for_visibility(
        PACKAGE, VERSION, probe=probe, sleep=clock.sleep, schedule=(1, 1), now=clock.time
    )

    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        emit_github_commands(outcome, PACKAGE, VERSION)
    log = buffer.getvalue()

    assert "::warning::" in log, "a deadline miss must raise a warning annotation"
    assert "::error::" not in log, "a slow publish must not be logged as a hard error"
    assert "NOT rolled back" in log, "the warning must state the upload was not rolled back"


def test_probe_errors_are_retried_and_reported_distinctly_from_absence() -> None:
    """A registry that never answers must exhaust the budget, not pass.

    Every failure mode -- 404, 5xx, connection error -- is retried, because none of
    them is evidence that the version will never arrive. Exhausting the budget is
    what turns that into a failure.
    """
    for detail in (
        "HTTP 404 from https://registry.npmjs.org/pkg",
        "HTTP 503 from https://registry.npmjs.org/pkg",
        "network error from https://registry.npmjs.org/pkg: timed out",
    ):
        probe = scripted_probe([ProbeResult(False, None, detail)])
        clock = FakeClock()
        outcome = wait_for_visibility(
            PACKAGE, VERSION, probe=probe, sleep=clock.sleep, schedule=(1, 1, 1), now=clock.time
        )
        assert not outcome.ok, f"unreachable registry must fail closed: {detail}"
        assert detail in outcome.warnings[-2] or detail in outcome.detail, (
            f"the last probe detail must survive into the report: {detail}"
        )


def test_budget_is_never_overslept() -> None:
    """A budget shorter than the schedule must stop early rather than overrun it."""
    probe = scripted_probe([ProbeResult(False, None, "absent")])
    clock = FakeClock()

    outcome = wait_for_visibility(
        PACKAGE,
        VERSION,
        probe=probe,
        sleep=clock.sleep,
        schedule=(10, 10, 10, 10, 10),
        now=clock.time,
        deadline_seconds=25,
    )

    assert not outcome.ok
    assert clock.now <= 25, f"overslept the budget: {clock.now}s > 25s"
    assert outcome.attempts < 5, "must stop before the full schedule when the budget is smaller"


def test_negative_schedule_is_rejected() -> None:
    clock = FakeClock()
    probe = scripted_probe([ProbeResult(False, None, "absent")])
    try:
        wait_for_visibility(
            PACKAGE, VERSION, probe=probe, sleep=clock.sleep, schedule=(1, -5), now=clock.time
        )
    except ValueError:
        return
    raise AssertionError("a negative backoff entry must raise ValueError")


# --------------------------------------------------------------------------
# The probe's own transport handling. A CDN that drops a connection mid-response
# must be retried, not allowed to kill the release job.
# --------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False


def _packument(versions: dict[str, object], latest: str) -> bytes:
    return json.dumps({"versions": versions, "dist-tags": {"latest": latest}}).encode("utf-8")


def test_probe_reports_present_from_a_packument() -> None:
    body = _packument({VERSION: {"name": PACKAGE}}, VERSION)
    result = probe_registry(
        PACKAGE, VERSION, opener=lambda request, timeout: _FakeResponse(200, body)
    )
    assert result.present, result.detail
    assert result.latest == VERSION


def test_probe_reports_absent_and_carries_the_current_latest_tag() -> None:
    body = _packument({"2.0.0": {"name": PACKAGE}}, "2.0.0")
    result = probe_registry(
        PACKAGE, VERSION, opener=lambda request, timeout: _FakeResponse(200, body)
    )
    assert not result.present
    assert result.latest == "2.0.0", "the dist-tag must be read even when the version is absent"


def test_probe_does_not_crash_on_a_dropped_connection() -> None:
    """RemoteDisconnected is an HTTPException, not a URLError.

    Catching only ``urllib.error.*`` lets this escape as a traceback and fails the
    release job on the first flaky read, which is the failure mode the retry loop
    exists to absorb.
    """
    import http.client

    def opener(request: object, timeout: float) -> object:
        raise http.client.RemoteDisconnected("Remote end closed connection without response")

    result = probe_registry(PACKAGE, VERSION, opener=opener)
    assert not result.present
    assert "HTTP protocol error" in result.detail, result.detail
    assert "RemoteDisconnected" in result.detail, result.detail


def test_probe_survives_every_transport_failure_shape() -> None:
    import http.client
    import ssl
    import urllib.error

    shapes: list[tuple[BaseException, str]] = [
        (urllib.error.HTTPError("u", 404, "Not Found", {}, None), "HTTP 404"),
        (urllib.error.HTTPError("u", 503, "Unavailable", {}, None), "HTTP 503"),
        (urllib.error.URLError("connection refused"), "network error"),
        (http.client.RemoteDisconnected("dropped"), "HTTP protocol error"),
        (http.client.IncompleteRead(b"partial"), "HTTP protocol error"),
        (TimeoutError("timed out"), "timed out"),
        (ConnectionResetError("reset by peer"), "transport error"),
        (ssl.SSLError("handshake failure"), "transport error"),
    ]
    for exc, expected in shapes:
        def opener(request: object, timeout: float, _exc: BaseException = exc) -> object:
            raise _exc

        result = probe_registry(PACKAGE, VERSION, opener=opener)
        assert not result.present, f"{type(exc).__name__} must not read as present"
        assert expected in result.detail, f"{type(exc).__name__}: {result.detail}"


def test_probe_rejects_an_unparseable_or_shapeless_packument() -> None:
    for body in (b"<html>not json</html>", b'"a string"', b"{}", b'{"versions": []}'):
        result = probe_registry(
            PACKAGE, VERSION, opener=lambda request, timeout: _FakeResponse(200, body)
        )
        assert not result.present, f"a malformed packument must not read as present: {body!r}"


def test_a_non_200_status_is_not_treated_as_success() -> None:
    result = probe_registry(
        PACKAGE, VERSION, opener=lambda request, timeout: _FakeResponse(500, b"{}")
    )
    assert not result.present
    assert "HTTP 500" in result.detail


# --------------------------------------------------------------------------
# The probe itself: URL construction, so a scoped name or a stray slash cannot
# silently address the wrong document.
# --------------------------------------------------------------------------


def test_packument_url_encodes_a_scoped_name_only() -> None:
    # npm addresses a scoped packument with a percent-encoded slash and a literal
    # at-sign: /@scope%2Fpkg. Encoding the "@" as well addresses a different path.
    assert packument_url("lodash") == "https://registry.npmjs.org/lodash"
    assert packument_url("@scope/pkg") == "https://registry.npmjs.org/@scope%2Fpkg"
    assert packument_url("lodash", "https://registry.example.com/") == (
        "https://registry.example.com/lodash"
    )


def main() -> int:
    failures: list[str] = []
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        try:
            test()
        except Exception as exc:  # noqa: BLE001 - report every failure, not just the first
            failures.append(f"  {test.__name__}: {type(exc).__name__}: {exc}")
        else:
            print(f"PASS {test.__name__}")
    if failures:
        print(f"FAIL {len(failures)}/{len(tests)}:")
        print("\n".join(failures))
        return 1
    print(f"OK: {len(tests)} visibility-poll contract tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
