"""Coverage hardening for POSIX sandbox resource limiting."""

from __future__ import annotations

import sys
import types


from axiomize.execution import sandbox


def _fake_resource(*, with_nproc: bool = True, failures: set[int] | None = None):
    module = types.ModuleType("resource")
    module.RLIMIT_CPU = 1
    module.RLIMIT_AS = 2
    module.RLIMIT_FSIZE = 3
    if with_nproc:
        module.RLIMIT_NPROC = 4
    module.calls: list[tuple[int, tuple[int, int]]] = []
    failures = failures or set()

    def setrlimit(which, limits):
        index = len(module.calls)
        module.calls.append((which, limits))
        if index in failures:
            raise OSError("not permitted")

    module.setrlimit = setrlimit
    return module


def test_resource_limiter_noop_outside_posix(monkeypatch):
    monkeypatch.setattr(sandbox.os, "name", "nt")
    assert sandbox._resource_limiter(30.0) is None


def test_resource_limiter_sets_all_limits(monkeypatch):
    fake = _fake_resource()
    monkeypatch.setitem(sys.modules, "resource", fake)
    monkeypatch.setattr(sandbox.os, "name", "posix")

    limiter = sandbox._resource_limiter(60.2)
    assert callable(limiter)
    assert limiter() is None
    assert fake.calls == [
        (fake.RLIMIT_CPU, (62, 62)),
        (fake.RLIMIT_AS, (2 * 1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024)),
        (fake.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024)),
        (fake.RLIMIT_NPROC, (64, 64)),
    ]


def test_resource_limiter_without_nproc(monkeypatch):
    fake = _fake_resource(with_nproc=False)
    monkeypatch.setitem(sys.modules, "resource", fake)
    monkeypatch.setattr(sandbox.os, "name", "posix")

    limiter = sandbox._resource_limiter(0.1)
    assert limiter() is None
    assert len(fake.calls) == 3
    assert fake.calls[0][1] == (2, 2)


def test_resource_limiter_swallows_platform_errors(monkeypatch):
    fake = _fake_resource(failures={0, 1, 2, 3})
    monkeypatch.setitem(sys.modules, "resource", fake)
    monkeypatch.setattr(sandbox.os, "name", "posix")

    limiter = sandbox._resource_limiter(5.0)
    assert limiter() is None
    assert len(fake.calls) == 4
