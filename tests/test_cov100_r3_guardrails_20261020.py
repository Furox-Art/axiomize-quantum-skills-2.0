"""Round-3 coverage completion for guard rails, causal, diagnostics and benchmarks."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from axiomize import causal_engine, dependency_policy, extended_export, limits, v120_runtime
from axiomize.bayesian import diagnostics
from axiomize.fitting.estimator import FitResult
from axiomize.model_ir import ModelFamily, ModelIR
from axiomize.reasoning.benchmark import evaluate, validate_submission
from axiomize.routing import router
from axiomize.runtime_guard import RuntimePatchError
from axiomize.uncertainty import quantify
from axiomize.validation import ledger


# --------------------------------------------------------------------------- #
# limits
# --------------------------------------------------------------------------- #

def test_bounded_int_reports_failed_string_conversion(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = "123456"
    real_int = int

    def failing_int(value=0, base=10):
        if value == sentinel:
            raise ValueError("synthetic conversion failure")
        return real_int(value, base)

    monkeypatch.setitem(limits.__dict__, "int", failing_int)
    with pytest.raises(ValueError) as excinfo:
        limits.bounded_int(sentinel, name="count", maximum=10**9)
    assert str(excinfo.value) == "count must be an integer"


def test_bounded_float_without_minimum_accepts_value_below_maximum() -> None:
    assert limits.bounded_float(0.25, name="level", maximum=1.0) == 0.25


# --------------------------------------------------------------------------- #
# dependency_policy
# --------------------------------------------------------------------------- #

def test_dependency_scan_accepts_explicit_empty_policies() -> None:
    findings = dependency_policy.scan_installed_dependencies(
        installed={"torch": "2.0.0"},
        forbidden={},
        minimums={},
    )
    assert findings == []


# --------------------------------------------------------------------------- #
# routing/router
# --------------------------------------------------------------------------- #

def test_classify_rejects_non_sequence_signals() -> None:
    with pytest.raises(ValueError, match="signals must be a sequence of strings"):
        router.classify({"signals": 42})


# --------------------------------------------------------------------------- #
# uncertainty/quantify
# --------------------------------------------------------------------------- #

def test_confidence_intervals_reject_too_many_parameters() -> None:
    params = {f"p{index}": (1.0, 0.1) for index in range(2001)}
    fit = FitResult(
        params=params,
        rmse=0.0,
        aic=0.0,
        bic=0.0,
        resid_autocorr=0.0,
        success=True,
        method="test",
        n=10,
        k=len(params),
    )
    with pytest.raises(ValueError, match="fit parameter count exceeds hard limit 2000"):
        quantify.confidence_intervals(fit)


# --------------------------------------------------------------------------- #
# validation/ledger
# --------------------------------------------------------------------------- #

def test_normalize_evidence_rejects_status_that_stays_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ledger, "_coerce_status", lambda value: None)
    with pytest.raises(ValueError, match="bilinmeyen status"):
        ledger._normalize_evidence("risk", "unresolvable-status")


# --------------------------------------------------------------------------- #
# causal_engine
# --------------------------------------------------------------------------- #

def test_logistic_irls_stops_at_iteration_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def never_converging_lstsq(matrix, target, rcond=None):
        calls.append(1)
        return np.full(matrix.shape[1], float(len(calls))), None, None, None

    monkeypatch.setattr(np.linalg, "lstsq", never_converging_lstsq)
    x = np.array([-3.0, -2.0, -1.0, 1.0, 2.0, 3.0])
    design = np.column_stack([np.ones_like(x), x])
    treatment = np.array([0.0, 0.0, 0.0, 1.0, 1.0, 1.0])
    beta, propensity = causal_engine._logistic_irls(design, treatment)
    assert len(calls) == 100
    assert beta.tolist() == [100.0, 100.0]
    assert np.all(np.isfinite(beta))
    assert np.all(propensity >= 1e-4)
    assert np.all(propensity <= 1 - 1e-4)
    assert propensity.shape == (6,)


def _causal_model(identification: dict) -> ModelIR:
    return ModelIR(
        name="causal-iv-list",
        domain="test",
        family=ModelFamily.CAUSAL,
        variables=[],
        parameters=[],
        equations=[],
        metadata={"causal": {
            "data": {
                "x": [0, 1, 0, 1, 0, 1],
                "y": [0, 1, 0, 1, 1, 0],
                "z": [1, 0, 1, 0, 1, 0],
            },
            "treatment": "x",
            "outcome": "y",
            "identification": identification,
        }},
    )


def test_iv_identification_accepts_list_instrument() -> None:
    model = _causal_model({"method": "iv", "instrument": ["z"]})
    result = causal_engine.estimate_causal_model(
        model, t_span=(0.0, 1.0), points=10, parameter_overrides=None, seed=7
    )
    assert result["causal_effect"]["method"] == "instrumental_variables_2sls"
    assert np.isfinite(result["causal_effect"]["estimate"])


# --------------------------------------------------------------------------- #
# bayesian/diagnostics
# --------------------------------------------------------------------------- #

def test_effective_sample_size_walks_the_full_geyer_sequence() -> None:
    rng = np.random.default_rng(0)
    chains = np.empty((2, 20000))
    for row in range(2):
        noise = rng.normal(size=20000)
        series = np.empty(20000)
        series[0] = noise[0]
        for index in range(1, 20000):
            series[index] = 0.999 * series[index - 1] + noise[index]
        chains[row] = series

    rhos = np.mean(
        np.vstack([diagnostics._autocorrelation(row, 1000) for row in chains]), axis=0
    )
    assert min(rhos[lag] + rhos[lag + 1] for lag in range(1, 1000, 2)) > 0
    ess = diagnostics.effective_sample_size(chains)
    assert 1.0 <= ess < 100.0
    assert ess < chains.size


# --------------------------------------------------------------------------- #
# extended_export
# --------------------------------------------------------------------------- #

def test_causal_dot_accepts_two_element_sequence_edges() -> None:
    model = ModelIR(
        name="dag",
        domain="test",
        family=ModelFamily.CAUSAL,
        variables=[],
        parameters=[],
        equations=[],
        metadata={"causal": {"dag_edges": [["a", "b"], ("b", "c")]}},
    )
    result = extended_export.export_causal_dot(model)
    assert result["status"] == "PASS"
    assert '"a" -> "b";' in result["content"]
    assert '"b" -> "c";' in result["content"]


# --------------------------------------------------------------------------- #
# skills/axiomize/tools/check_skill
# --------------------------------------------------------------------------- #

def test_check_links_skips_non_document_suffixes(tmp_path: Path) -> None:
    from axiomize.tools import check_skill

    doc = tmp_path / "page.md"
    doc.write_text("[img](missing.png) [style](theme.css)\n", encoding="utf-8")
    assert check_skill.check_links([doc]) == []


# --------------------------------------------------------------------------- #
# reasoning/benchmark/evaluate
# --------------------------------------------------------------------------- #

def test_read_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    rows_path = tmp_path / "rows.jsonl"
    rows_path.write_text('\n{"case_id": "c1"}\n\n', encoding="utf-8")
    assert evaluate.read_jsonl(rows_path) == [{"case_id": "c1"}]


def test_main_skips_non_mapping_payload_sections(
    monkeypatch: pytest.MonkeyPatch, capsys, tmp_path: Path
) -> None:
    cases = tmp_path / "cases.jsonl"
    cases.write_text('{"id": "c1"}\n', encoding="utf-8")
    skill = tmp_path / "skill.jsonl"
    skill.write_text('{"case_id": "c1"}\n', encoding="utf-8")
    monkeypatch.setattr(evaluate, "summarize", lambda cases, rows: ["not-a-mapping"])
    code = evaluate.main(["--cases", str(cases), "--skill", str(skill)])
    assert code == 0
    assert json.loads(capsys.readouterr().out) == {"skill": ["not-a-mapping"]}


# --------------------------------------------------------------------------- #
# reasoning/benchmark/validate_submission
# --------------------------------------------------------------------------- #

def _valid_metadata() -> dict:
    condition = {
        "instruction_config": "skill",
        "sampling": {"temperature": 0},
        "tool_availability": True,
        "context_limit": None,
        "output_limit": None,
    }
    return {
        "provider": "p",
        "model": "m",
        "run_date": "2026-10-20",
        "skill_version": "1.0.0",
        "repetitions_per_case": 1,
        "baseline": dict(condition),
        "skill": dict(condition),
        "failures_recorded": True,
    }


def test_validate_metadata_rejects_blank_provider() -> None:
    metadata = _valid_metadata()
    metadata["provider"] = "   "
    with pytest.raises(ValueError, match="metadata.provider must be a non-empty string"):
        validate_submission.validate_metadata(metadata)


def test_validate_submission_imports_sibling_when_run_as_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    benchmark_package = importlib.import_module("axiomize.reasoning.benchmark")

    module_path = Path(benchmark_package.__file__).parent / "validate_submission.py"
    spec = importlib.util.spec_from_file_location(
        "validate_submission_standalone_r3", module_path
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.syspath_prepend(str(module_path.parent))
    monkeypatch.setitem(sys.modules, spec.name, module)
    had_evaluate = "evaluate" in sys.modules
    try:
        spec.loader.exec_module(module)
        assert module.evaluate.read_jsonl is not None
        assert module.REQUIRED_FILES == {
            "metadata.json", "cases.jsonl", "baseline.jsonl", "skill.jsonl",
            "comparison.json", "README.md",
        }
    finally:
        if not had_evaluate:
            sys.modules.pop("evaluate", None)


# --------------------------------------------------------------------------- #
# v120_runtime
# --------------------------------------------------------------------------- #

def test_verify_patch_surface_reports_missing_intermediate() -> None:
    engine = SimpleNamespace(
        select_solver=lambda model: {},
        numerical_refinement=lambda **kwargs: {},
        export_model=lambda model, **kwargs: {},
        _simulate_once=lambda *args, **kwargs: None,
        _validated_span=lambda span: span,
        _validated_points=lambda points, model=None: points,
        _core=None,
    )
    with pytest.raises(RuntimePatchError, match="missing from the engine surface"):
        v120_runtime._verify_patch_surface(engine, SimpleNamespace())


def _installable_engine() -> SimpleNamespace:
    core = SimpleNamespace(
        select_solver=lambda model: {},
        export_model=lambda model, *, format="json": {},
    )
    return SimpleNamespace(
        select_solver=lambda model: {},
        numerical_refinement=lambda **kwargs: {},
        export_model=lambda model, *, format="json": {},
        _simulate_once=lambda *args, **kwargs: None,
        _validated_span=lambda span: span,
        _validated_points=lambda points, model=None: points,
        _core=core,
    )


def _install_with(monkeypatch: pytest.MonkeyPatch, fake_infer):
    from axiomize.bayesian import engine_v2

    monkeypatch.setattr(engine_v2, "infer_bayesian_model", fake_infer)
    advanced = SimpleNamespace(
        _estimate_causal=lambda *args, **kwargs: {},
        _infer_bayesian=lambda *args, **kwargs: {},
    )
    v120_runtime.install(_installable_engine(), advanced)
    return advanced


def test_install_averages_acceptance_rate_by_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_infer(*args, **kwargs):
        return {"diagnostics": {"acceptance_rate_by_chain": [0.2, 0.6]}, "samples": 10}

    advanced = _install_with(monkeypatch, fake_infer)
    result = advanced._infer_bayesian("model")
    assert result["samples"] == 10
    assert result["diagnostics"]["acceptance_rate_by_chain"] == [0.2, 0.6]
    assert result["diagnostics"]["acceptance_rate"] == pytest.approx(0.4)


def test_install_keeps_non_mapping_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_infer(*args, **kwargs):
        return {"diagnostics": "unavailable", "samples": 3}

    advanced = _install_with(monkeypatch, fake_infer)
    result = advanced._infer_bayesian()
    assert result == {"diagnostics": "unavailable", "samples": 3}
    assert "acceptance_rate" not in result


def test_install_keeps_empty_acceptance_rate_series(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_infer(*args, **kwargs):
        return {"diagnostics": {"acceptance_rate_by_chain": []}}

    advanced = _install_with(monkeypatch, fake_infer)
    result = advanced._infer_bayesian()
    assert result["diagnostics"] == {"acceptance_rate_by_chain": []}
