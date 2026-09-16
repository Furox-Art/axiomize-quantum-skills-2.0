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


class TestEvaluatorCli:
    def _write_cases(self, root: Path) -> Path:
        path = root / "cases.jsonl"
        path.write_text(json.dumps(CASES[0]) + "\n", encoding="utf-8")
        return path

    def test_main_writes_comparison_output(self, tmp_path: Path) -> None:
        cases = self._write_cases(tmp_path)
        skill = tmp_path / "skill.jsonl"
        skill.write_text(
            json.dumps({"case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0, "latency_ms": 100}) + "\n",
            encoding="utf-8",
        )
        output = tmp_path / "out" / "comparison.json"
        code = evaluate.main(
            ["--cases", str(cases), "--skill", str(skill), "--output", str(output)]
        )
        assert code == 0
        payload = json.loads(output.read_text(encoding="utf-8"))
        assert payload["skill"]["accuracy"] == 1.0

    def test_main_rejects_non_finite_measurements(self, tmp_path: Path) -> None:
        cases = self._write_cases(tmp_path)
        skill = tmp_path / "skill.jsonl"
        skill.write_text(
            json.dumps(
                {"case_id": "c1", "answer": "2", "tokens": 1, "tool_calls": 0, "latency_ms": float("inf")}
            )
            + "\n",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="not finite"):
            evaluate.main(["--cases", str(cases), "--skill", str(skill)])

    def test_read_jsonl_rejects_invalid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.jsonl"
        path.write_text("{not json}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="invalid JSON"):
            evaluate.read_jsonl(path)

    def test_read_jsonl_rejects_non_object_rows(self, tmp_path: Path) -> None:
        path = tmp_path / "rows.jsonl"
        path.write_text("[1, 2]\n", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON object"):
            evaluate.read_jsonl(path)

    def test_validate_case_requires_all_fields(self) -> None:
        with pytest.raises(ValueError, match="missing required field"):
            evaluate.validate_case({"id": "c1", "domain": "math", "prompt": "?"})

    def test_validate_case_requires_non_empty_accepted_answers(self) -> None:
        with pytest.raises(ValueError, match="accepted_answers"):
            evaluate.validate_case({"id": "c1", "domain": "math", "prompt": "?", "accepted_answers": []})

    def test_validate_result_rejects_negative_numbers(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            evaluate.validate_result(
                {"case_id": "c1", "answer": "2", "tokens": -1, "tool_calls": 0, "latency_ms": 1}
            )

    def test_validate_result_rejects_wrong_types(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            evaluate.validate_result(
                {"case_id": "c1", "answer": "2", "tokens": "many", "tool_calls": 0, "latency_ms": 1}
            )

    def test_validate_result_rejects_negative_telemetry(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            evaluate.validate_result(
                {
                    "case_id": "c1",
                    "answer": "2",
                    "tokens": 1,
                    "tool_calls": 0,
                    "latency_ms": 1,
                    "branches_total": -2,
                }
            )

    def test_validate_result_rejects_distinct_exceeding_total(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            evaluate.validate_result(
                {
                    "case_id": "c1",
                    "answer": "2",
                    "tokens": 1,
                    "tool_calls": 0,
                    "latency_ms": 1,
                    "branches_total": 2,
                    "branches_distinct": 5,
                }
            )

    def test_summarize_rejects_duplicate_case_ids(self) -> None:
        duplicated = [CASES[0], CASES[0]]
        with pytest.raises(ValueError, match="case ids must be unique"):
            evaluate.summarize(duplicated, [])

    def test_summarize_rejects_duplicate_results_for_one_case(self) -> None:
        row = {"case_id": "c1", "answer": "2", "tokens": 1, "tool_calls": 0, "latency_ms": 1}
        with pytest.raises(ValueError, match="duplicate result"):
            evaluate.summarize([CASES[0]], [row, row])

    def test_main_compares_against_baseline(self, capsys, tmp_path: Path) -> None:
        cases = self._write_cases(tmp_path)
        baseline = tmp_path / "baseline.jsonl"
        baseline.write_text(
            json.dumps({"case_id": "c1", "answer": "wrong", "tokens": 5, "tool_calls": 0, "latency_ms": 50}) + "\n",
            encoding="utf-8",
        )
        skill = tmp_path / "skill.jsonl"
        skill.write_text(
            json.dumps({"case_id": "c1", "answer": "2", "tokens": 10, "tool_calls": 0, "latency_ms": 100}) + "\n",
            encoding="utf-8",
        )
        code = evaluate.main(
            ["--cases", str(cases), "--skill", str(skill), "--baseline", str(baseline)]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["comparison"]["accuracy_delta"] == 1.0

    def test_validate_result_rejects_resolved_exceeding_found(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            evaluate.validate_result(
                {
                    "case_id": "c1",
                    "answer": "2",
                    "tokens": 1,
                    "tool_calls": 0,
                    "latency_ms": 1,
                    "contradictions_found": 1,
                    "contradictions_resolved": 3,
                }
            )

    def test_safe_mean_of_nothing_is_none(self) -> None:
        assert evaluate.safe_mean([]) is None


class TestSubmissionValidatorCli:
    def test_main_validates_every_bundle_in_root(self, tmp_path: Path) -> None:
        root = tmp_path / "community"
        root.mkdir()
        _make_bundle(root)
        assert validate_submission.main(["--root", str(root)]) == 0

    def test_main_fails_without_allow_empty_when_root_missing(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="community benchmark root not found"):
            validate_submission.main(["--root", str(tmp_path / "missing")])

    def test_main_fails_on_existing_but_empty_root(self, tmp_path: Path) -> None:
        empty = tmp_path / "community"
        empty.mkdir()
        with pytest.raises(SystemExit, match="no community benchmark bundles"):
            validate_submission.main(["--root", str(empty)])

    def test_main_succeeds_on_missing_root_with_allow_empty(self, tmp_path: Path) -> None:
        assert validate_submission.main(["--root", str(tmp_path / "missing"), "--allow-empty"]) == 0

    def test_invalid_metadata_json_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            (bundle / "metadata.json").write_text("{broken}", encoding="utf-8")
            with pytest.raises(ValueError, match="invalid JSON"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_missing_required_field_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            del meta["model"]
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="missing fields"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_bad_run_date_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            meta["run_date"] = "07-09-2026"
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="run_date"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_zero_repetitions_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            meta["repetitions_per_case"] = 0
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="repetitions_per_case"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_non_dict_baseline_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            meta["baseline"] = "baseline"
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="must be an object"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_missing_condition_field_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            del meta["skill"]["tool_availability"]
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="missing fields"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_empty_instruction_config_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            meta["skill"]["instruction_config"] = "   "
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="instruction_config"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_sampling_must_be_object(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            meta["skill"]["sampling"] = "greedy"
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="sampling"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_invalid_context_limit_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            meta = json.loads((bundle / "metadata.json").read_text(encoding="utf-8"))
            meta["skill"]["context_limit"] = 0
            (bundle / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
            with pytest.raises(ValueError, match="context_limit"):
                validate_submission.validate_bundle(bundle)

    def test_metadata_must_be_an_object(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            (bundle / "metadata.json").write_text(json.dumps([1, 2]), encoding="utf-8")
            with pytest.raises(ValueError, match="must contain a JSON object"):
                validate_submission.validate_bundle(bundle)

    def test_duplicate_case_id_in_result_rows_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            row = json.loads((bundle / "baseline.jsonl").read_text(encoding="utf-8"))
            (bundle / "baseline.jsonl").write_text(
                json.dumps(row) + "\n" + json.dumps(row) + "\n", encoding="utf-8"
            )
            with pytest.raises(ValueError, match="duplicate baseline case_id"):
                validate_submission.validate_bundle(bundle)

    def test_duplicate_case_id_in_bundle_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            case = json.loads((bundle / "cases.jsonl").read_text(encoding="utf-8"))
            (bundle / "cases.jsonl").write_text(
                json.dumps(case) + "\n" + json.dumps(case) + "\n", encoding="utf-8"
            )
            with pytest.raises(ValueError, match="duplicate case id"):
                validate_submission.validate_bundle(bundle)

    def test_result_referencing_unknown_case_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            cases = json.loads((bundle / "cases.jsonl").read_text(encoding="utf-8"))
            extra = dict(cases)
            extra["id"] = "ghost"
            (bundle / "cases.jsonl").write_text(
                json.dumps(cases) + "\n" + json.dumps(extra) + "\n", encoding="utf-8"
            )
            with pytest.raises(ValueError, match="exactly one row"):
                validate_submission.validate_bundle(bundle)

    def test_empty_bundle_readme_fails(self, tmp_path: Path) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bundle = _make_bundle(Path(tmp))
            (bundle / "README.md").write_text("   \n", encoding="utf-8")
            with pytest.raises(ValueError, match="README"):
                validate_submission.validate_bundle(bundle)