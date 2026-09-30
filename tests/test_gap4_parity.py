"""GAP-4 ajan-saha parite testi: CLI / MCP / REST ayni core davranisi mi?

Kapsam (kod okuma ile dogrulandi):
- src/axiomize/cli.py -> cmd_solve: solve_sir_service, cmd_validate: validate_sir_service
- src/axiomize/server/rest_server.py -> POST /solve|/simulate|/model: solve_sir_service,
  /validate: validate_sir_service, /cross-validate: solve_sir_service(...)[cross_validation],
  /fit: fit_logistic_service, /falsify, /compare, GET /tools, /capabilities.
  NOT: /sensitivity ve /uncertainty rotasi YOK (404).
- src/axiomize/server/mcp_server.py -> _call_tool: solve/simulate/validate hepsi
  validate_sir_service cagirir (solve icin solve_sir_service DEGIL);
  uncertainty_analysis gercek servis cagirmaz, echo stub dondurur.
- src/axiomize/application/services.py -> tek core: solve_sir_service,
  validate_sir_service (= solve + validation_checks), fit_logistic_service,
  sensitivity_service, falsify_service, compare_service, tools/capabilities.

Bu dosya gercek durumu assert eder: parite olan yerde PASS, kirik yerde
acik mesajla FAIL (sahte PASS yok). Bilinen 3 kirik:
  1) MCP solve, solve degil validate dondurur (fazladan 'validation_checks').
  2) MCP uncertainty_analysis echo stub'dur, core servis cagirmaz.
  3) REST'te /sensitivity rotasi yoktur (404), oysa sensitivity_service + MCP vardir.
"""

from __future__ import annotations

import argparse
import io
import json
import threading
import urllib.request
from contextlib import redirect_stdout

import pytest

PAR = {"beta": 0.3, "gamma": 0.1, "I0": 10.0, "N": 100000.0, "days": 180.0}


def _cli_solve_output(params: dict) -> dict:
    from axiomize.cli import cmd_solve

    args = argparse.Namespace(
        beta=params["beta"], gamma=params["gamma"], I0=params["I0"],
        N=params["N"], days=params["days"], json=None,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = cmd_solve(args)
    assert rc == 0
    return json.loads(buf.getvalue())


def _cli_validate_output(params: dict) -> dict:
    from axiomize.cli import cmd_validate

    args = argparse.Namespace(
        beta=params["beta"], gamma=params["gamma"], I0=params["I0"],
        N=params["N"], days=params["days"], json=None,
    )
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_validate(args)
    return json.loads(buf.getvalue())


# /sensitivity runs a hardcoded 1000-sample Monte Carlo (mc_sensitivity(n=1000))
# over a full solve_sir each time, so it costs roughly 30s untraced and over a
# minute under --cov tracing regardless of N. The client timeout therefore needs
# real headroom, and transient connection-level failures need a retry: on Windows a
# slow handler shows up as ConnectionAbortedError (WinError 10053) or as a plain
# timeout, both of which are environment noise rather than a parity failure.
_REST_TIMEOUT = 300.0
_REST_ATTEMPTS = 3


def _rest_post(port: int, path: str, payload: dict) -> tuple[int, dict]:
    encoded = json.dumps(payload).encode("utf-8")
    last: Exception | None = None
    for _ in range(_REST_ATTEMPTS):
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}{path}",
            data=encoded,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=_REST_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8", "replace")
                try:
                    return resp.status, json.loads(raw)
                except ValueError:
                    # A 200 carrying an HTML or proxy error page is still an
                    # answer; report it instead of crashing on a decode error.
                    return resp.status, {"raw": raw}
        except urllib.error.HTTPError as exc:
            # A real HTTP status is an answer, not a transport failure: report it
            # rather than retrying, so the parity assertion still sees the code.
            body = exc.read().decode("utf-8", "replace")
            try:
                return exc.code, json.loads(body)
            except ValueError:
                return exc.code, {"raw": body}
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            last = exc
    raise AssertionError(
        f"REST {path} unreachable after {_REST_ATTEMPTS} attempts: {last!r}"
    ) from last


# --- smoke: uc katman da import edilebiliyor ve ayni core modulu goruyor ---

def test_adapter_import_smoke():
    import axiomize.cli  # noqa: F401
    import axiomize.server.mcp_server  # noqa: F401
    import axiomize.server.rest_server  # noqa: F401
    from axiomize.application import services  # noqa: F401

    assert hasattr(services, "solve_sir_service")
    assert hasattr(services, "validate_sir_service")
    assert hasattr(services, "sensitivity_service")


# --- PARITE OLANLAR (PASS beklenir) ---

def test_cli_solve_matches_core_service():
    """CLI solve, solve_sir_service ile birebir ayni sonucu verir (PASS)."""
    from axiomize.application import services

    assert _cli_solve_output(PAR) == services.solve_sir_service(dict(PAR))


def test_cli_validate_matches_core_service():
    """CLI validate, validate_sir_service ile birebir aynidir (PASS)."""
    from axiomize.application import services

    assert _cli_validate_output(PAR) == services.validate_sir_service(dict(PAR))


def test_mcp_validate_matches_core_service():
    """MCP validate, validate_sir_service ile aynidir (PASS)."""
    from axiomize.application import services
    from axiomize.server import mcp_server

    assert mcp_server._call_tool("axiomize.validate", dict(PAR)) == \
        services.validate_sir_service(dict(PAR))


def test_rest_solve_matches_core_service_live():
    """REST POST /solve, solve_sir_service ile birebir aynidir (canli, PASS)."""
    from axiomize.application import services
    from axiomize.server.rest_server import start_server

    srv = start_server("127.0.0.1", 0)
    port = srv.server_address[1]
    thr = threading.Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    try:
        code, body = _rest_post(port, "/solve", dict(PAR))
        assert code == 200, f"REST /solve HTTP {code}: {body}"
        assert body == services.solve_sir_service(dict(PAR))
    finally:
        srv.shutdown()


# --- PARITE KIRIKLARI (FAIL beklenir; mesajlar eksigi gosterir) ---

def test_mcp_solve_matches_solve_service():
    """MCP solve, CLI/REST solve ile ayni core ciktiyi vermeli.

    GERCEK: MCP _call_tool('axiomize.solve') validate_sir_service cagirir,
    CLI/REST solve_sir_service cagirir -> fazladan 'validation_checks' anahtari.
    Bu test parite kirik oldugu icin FAIL verir (duzeltme: MCP solve'un
    solve_sir_service cagirmasi gerekir).
    """
    from axiomize.application import services
    from axiomize.server import mcp_server

    mcp_out = mcp_server._call_tool("axiomize.solve", dict(PAR))
    core_out = services.solve_sir_service(dict(PAR))
    assert mcp_out == core_out, (
        "PARITE KIRIK (MCP solve vs core solve): MCP 'axiomize.solve' "
        f"validate donduruyor; farkli anahtarlar={sorted(set(mcp_out) ^ set(core_out))} "
        "(beklenen: MCP solve == solve_sir_service)"
    )


def test_mcp_uncertainty_calls_core_service():
    """MCP uncertainty_analysis gercek core servis cagirmali.

    GERCEK: _call_tool('axiomize.uncertainty_analysis') echo stub dondurur
    ({'note': ..., 'echo': ...}), hicbir application servisini cagirmaz.
    Bu test parite kirik oldugu icin FAIL verir.
    """
    from axiomize.server import mcp_server

    out = mcp_server._call_tool("axiomize.uncertainty_analysis", {"fit": {}})
    assert "echo" not in out, (
        f"PARITE KIRIK (MCP uncertainty): echo stub donduruluyor: {out} "
        "(beklenen: gercek core servis ciktisi, 'echo' anahtari olmamali)"
    )
    assert any(k in out for k in ("intervals", "ci", "quantiles", "uncertainty")), (
        f"PARITE KIRIK (MCP uncertainty): belirsizlik araliklari yok: {sorted(out)}"
    )


@pytest.mark.network
def test_rest_sensitivity_route_exists_live():
    """REST sensitivity endpointi core sensitivity_service'e bagli olmali.

    Marked `network` for cost, not for flakiness. The endpoint runs a hardcoded
    1000-sample Monte Carlo per call, so one request costs ~30s and the coverage
    job does not need to pay that. It is no longer unreliable: _rest_post retries
    transport-level failures and allows a 300s timeout, both of which were added
    after the endpoint turned out to be slower than the old 60s client timeout
    under --cov tracing.

    TODO: give /sensitivity a sample-count parameter so this test can use a small
    budget instead of paying for the full Monte Carlo.

    GERCEK: rest_server.py'de /sensitivity rotasi yok (404); oysa
    sensitivity_service ve MCP sensitivity_analysis mevcut.
    Bu test parite kirik oldugu icin FAIL verir.
    """
    from axiomize.server.rest_server import start_server

    srv = start_server("127.0.0.1", 0)
    port = srv.server_address[1]
    thr = threading.Thread(target=srv.serve_forever, daemon=True)
    thr.start()
    try:
        code, body = _rest_post(
            port, "/sensitivity",
            {"params": {"beta": 0.3, "gamma": 0.1}, "N": 100000.0, "I0": 10.0},
        )
        assert code == 200, (
            f"PARITE KIRIK (REST sensitivity): HTTP {code}: {body} "
            "(beklenen: 200 + sensitivity_service ciktisi)"
        )
        assert "local" in body and "mc_screening" in body, (
            f"PARITE KIRIK (REST sensitivity): beklenen anahtarlar yok: {sorted(body)}"
)
    finally:
        srv.shutdown()


# --- _rest_post transport hardening (cheap, runs no real computation) ---


class _FakeResponse(io.BytesIO):
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()
        return False


def test_rest_post_retries_transport_failures_then_succeeds(monkeypatch):
    """A Windows connection abort is environment noise, not a parity failure."""
    seen = {"n": 0}

    def flaky(req, timeout=None):
        seen["n"] += 1
        if seen["n"] < 3:
            raise ConnectionAbortedError(10053, "software caused connection abort")
        return _FakeResponse(json.dumps({"local": {}, "mc_screening": {}}).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", flaky)
    code, body = _rest_post(1, "/sensitivity", {})

    assert code == 200
    assert sorted(body) == ["local", "mc_screening"]
    assert seen["n"] == 3


def test_rest_post_gives_up_after_the_attempt_limit(monkeypatch):
    """Bounded retry: a permanently unreachable route must fail, not hang."""
    seen = {"n": 0}

    def always_aborts(req, timeout=None):
        seen["n"] += 1
        raise ConnectionAbortedError(10053, "abort")

    monkeypatch.setattr(urllib.request, "urlopen", always_aborts)
    with pytest.raises(AssertionError, match="unreachable after 3 attempts"):
        _rest_post(1, "/sensitivity", {})
    assert seen["n"] == _REST_ATTEMPTS


def test_rest_post_does_not_retry_a_real_http_status(monkeypatch):
    """A 404 is an answer the parity assertion must see, so it must not be retried."""
    seen = {"n": 0}

    def not_found(req, timeout=None):
        seen["n"] += 1
        raise urllib.error.HTTPError(
            req.full_url, 404, "Not Found", {}, io.BytesIO(b'{"error": "no route"}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", not_found)
    code, body = _rest_post(1, "/sensitivity", {})

    assert code == 404
    assert body == {"error": "no route"}
    assert seen["n"] == 1


def test_rest_post_returns_raw_body_when_a_response_is_not_json(monkeypatch):
    monkeypatch.setattr(
        urllib.request,
        "urlopen",
        lambda req, timeout=None: _FakeResponse(b"<html>gateway timeout</html>"),
    )
    code, body = _rest_post(1, "/sensitivity", {})
    assert code == 200
    assert body == {"raw": "<html>gateway timeout</html>"}
