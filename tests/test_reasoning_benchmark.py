"""Ported quantum-reasoning benchmark + submission-validation contracts."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from axiomize.reasoning.benchmark import evaluate, validate_submission


CASES = [
    {"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]},
    {"id": "c2", "domain": "logic", "prompt": "yes?", "accepted_answers": ["yes"]},
]


def test_summary_computes_accuracy_and_telemetry() -> None:
    results = [
        {
            "case_id": "c1",
            "answer": "2",
            "tokens": 100,
            "tool_calls": 1,
            "latency_ms": 50,
            "branches_total": 4,
            "branches_distinct": 3,
            "revived_branches": 1,
            "recovered_errors": 1,
            "contradictions_found": 2,
            "contradictions_resolved": 2,
        },
        {
            "case_id": "c2",
            "answer": "no",
            "tokens": 200,
            "tool_calls": 3,
            "latency_ms": 150,
            "branches_total": 2,
            "branches_distinct": 1,
            "revived_branches": 0,
            "recovered_errors": 0,
            "contradictions_found": 1,
            "contradictions_resolved": 0,
        },
    ]
    summary = evaluate.summarize(CASES, results)
    assert summary["accuracy"] == 0.5
    assert summary["mean_tokens"] == 150.0
    assert summary["mean_tool_calls"] == 2.0
    assert summary["mean_latency_ms"] == 100.0
    assert summary["branch_diversity_ratio"] == 4 / 6
    assert summary["contradiction_resolution_rate"] == 2 / 3


def test_compare_reports_cost_and_accuracy_changes() -> None:
    baseline = {
        "accuracy": 0.5,
        "mean_tokens": 100.0,
        "mean_tool_calls": 1.0,
        "mean_latency_ms": 100.0,
        "branch_diversity_ratio": 0.4,
        "contradiction_resolution_rate": 0.5,
    }
    skill = {
        "accuracy": 0.75,
        "mean_tokens": 150.0,
        "mean_tool_calls": 2.0,
        "mean_latency_ms": 120.0,
        "branch_diversity_ratio": 0.7,
        "contradiction_resolution_rate": 0.8,
    }
    delta = evaluate.compare(baseline, skill)
    assert delta["accuracy_delta"] == 0.25
    assert delta["tokens_percent_change"] == 50.0
    assert delta["tool_calls_percent_change"] == 100.0
    assert delta["latency_percent_change"] == 20.0
    assert delta["branch_diversity_delta"] == pytest.approx(0.3)
    assert delta["contradiction_resolution_delta"] == pytest.approx(0.3)


def test_missing_result_fields_fail() -> None:
    with pytest.raises(ValueError):
        evaluate.summarize(CASES, [{"case_id": "c1", "answer": "2", "tokens": 1}])


def test_unknown_case_id_fails() -> None:
    with pytest.raises(ValueError):
        evaluate.summarize(
            CASES,
            [{"case_id": "missing", "answer": "2", "tokens": 1, "tool_calls": 0, "latency_ms": 1}],
        )


def _make_bundle(root: Path) -> Path:
    bundle = root / "provider-model-2026-09-07"
    bundle.mkdir()
    cases = [{"id": "c1", "domain": "math", "prompt": "1+1?", "accepted_answers": ["2"]}]
    baseline = [{"case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0, "latency_ms": 100}]
    skill = [{"case_id": "c1", "answer": "2", "tokens": 12, "tool_calls": 0, "latency_ms": 110}]
    (bundle / "cases.jsonl").write_text(json.dumps(cases[0]) + "\n", encoding="utf-8")
    (bundle / "baseline.jsonl").write_text(json.dumps(baseline[0]) + "\n", encoding="utf-8")
    (bundle / "skill.jsonl").write_text(json.dumps(skill[0]) + "\n", encoding="utf-8")
    meta = {
        "provider": "example",
        "model": "model",
        "run_date": "2026-09-07",
        "skill_version": "0.3.0",
        "repetitions_per_case": 1,
        "failures_recorded": True,
        "baseline": {
            "instruction_config": "baseline",
            "sampling": {},
            "tool_availability": [],
            "context_limit": 1000,
            "output_limit": 100,
        },
        "skill": {
            "instruction_config": "SKILL.md",
            "sampling": {},
            "tool_availability": [],
            "context_limit": 1000,
            "output_limit": 100,
        },
    }
    (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    payload = {
        "skill": evaluate.summarize(cases, skill),
        "baseline": evaluate.summarize(cases, baseline),
    }
    payload["comparison"] = evaluate.compare(payload["baseline"], payload["skill"])
    (bundle / "comparison.json").write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    (bundle / "README.md").write_text("Reproducible test bundle.\n", encoding="utf-8")
    return bundle


def test_valid_bundle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        validate_submission.validate_bundle(_make_bundle(Path(tmp)))


def test_missing_artifact_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle = _make_bundle(Path(tmp))
        (bundle / "README.md").unlink()
        with pytest.raises(ValueError):
            validate_submission.validate_bundle(bundle)


def test_tampered_comparison_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle = _make_bundle(Path(tmp))
        payload = json.loads((bundle / "comparison.json").read_text(encoding="utf-8"))
        payload["comparison"]["accuracy_delta"] = 99
        (bundle / "comparison.json").write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError):
            validate_submission.validate_bundle(bundle)


def test_unrecorded_failures_flag_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        bundle = _make_bundle(Path(tmp))
        meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
        meta["failures_recorded"] = False
        (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        with pytest.raises(ValueError):
            validate_submission.validate_bundle(bundle)


def test_seed_cases_and_schemas_are_shipped_and_valid() -> None:
    benchmark_dir = Path(evaluate.__file__).resolve().parent
    cases = evaluate.read_jsonl(benchmark_dir / "cases.jsonl")
    assert cases, "shipped seed cases must not be empty"
    for case in cases:
        evaluate.validate_case(case)
    schemas = sorted((benchmark_dir / "schemas").glob("*.json"))
    assert len(schemas) == 4
    for schema in schemas:
        json.loads(schema.read_text(encoding="utf-8"))