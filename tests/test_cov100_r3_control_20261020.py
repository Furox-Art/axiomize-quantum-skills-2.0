"""Round-3 coverage completion for the closed-loop PID step analysis."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from axiomize.control.pid import closed_loop_step


def test_closed_loop_step_rejects_malformed_step_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import control

    mismatched = SimpleNamespace(y=np.array([1.0]))
    non_finite = SimpleNamespace(y=np.full(50, np.nan))
    for fake_response in (mismatched, non_finite):
        monkeypatch.setattr(
            control, "step_response", lambda *args, _fake=fake_response, **kwargs: _fake
        )
        with pytest.raises(RuntimeError, match="malformed or non-finite"):
            closed_loop_step(1.0, 1.0, 0.0, [1.0], [1.0], t_end=5.0, n=50)


def test_closed_loop_step_fully_settled_trajectory_needs_no_settling_time() -> None:
    result = closed_loop_step(1.0, 1.0, 500.0, [1.0], [1.0], t_end=5.0, n=50)
    assert result["points"] == 50
    assert result["settled"] is True
    assert result["settling_time"] == 0.0
    assert result["overshoot"] == 0.0
    assert 0.98 <= result["final"] <= 1.02
    assert result["final"] == pytest.approx(0.9901816356147582, abs=1e-6)
