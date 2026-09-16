"""axiomize-reason CLI contract: score / select / width subcommands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiomize.reasoning.cli import build_parser, main


def _run(capsys, *argv: str) -> dict:
    code = main(list(argv))
    assert code == 0
    return json.loads(capsys.readouterr().out)


def test_score_reports_collapse_state(capsys) -> None:
    payload = _run(
        capsys,
        "score",
        "--id",
        "leader",
        "--evidence",
        "1.0",
        "--verification",
        "1.0",
        "--independence",
        "1.0",
        "--information-gain",
        "0.9",
        "--contradiction",
        "0.0",
        "--unresolved-assumptions",
        "0.0",
        "--normalized-cost",
        "0.0",
    )
    assert payload["branch"] == "leader"
    assert payload["can_collapse"] is True
    assert payload["reason"] == "collapse criteria satisfied"


def test_score_weak_branch_cannot_collapse(capsys) -> None:
    payload = _run(capsys, "score", "--evidence", "0.2", "--verification", "0.2")
    assert payload["can_collapse"] is False


def test_score_rejects_out_of_range_metric() -> None:
    with pytest.raises(ValueError):
        main(["score", "--evidence", "1.2", "--verification", "0.5"])


def test_parser_requires_a_subcommand() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_select_ranks_candidates_from_json(capsys, tmp_path: Path) -> None:
    candidates = {
        "candidates": [
            {"candidate_id": "sir", "evidence": 1.0, "verification": 1.0, "information_gain": 0.9},
            {"candidate_id": "seir", "evidence": 0.5, "verification": 0.4},
        ]
    }
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(candidates), encoding="utf-8")
    payload = _run(capsys, "select", "--candidates", str(path))
    assert payload["can_select"] is True
    assert payload["leader"] == "sir"
    assert payload["ranking"] == ["sir", "seir"]


def test_select_blocked_by_close_competitor(capsys, tmp_path: Path) -> None:
    candidates = {
        "candidates": [
            {"candidate_id": "sir", "evidence": 1.0, "verification": 1.0, "information_gain": 0.9},
            {"candidate_id": "seir", "evidence": 0.97, "verification": 0.97, "information_gain": 0.9},
        ]
    }
    path = tmp_path / "candidates.json"
    path.write_text(json.dumps(candidates), encoding="utf-8")
    payload = _run(capsys, "select", "--candidates", str(path))
    assert payload["can_select"] is False
    assert "margin" in payload["reason"]
    assert set(payload["ranking"]) == {"sir", "seir"}


def test_width_maps_uncertainty_to_search_range(capsys) -> None:
    payload = _run(capsys, "width", "0.8", "0.8", "0.8", "0.8")
    assert 0.0 <= payload["uncertainty"] <= 1.0
    assert payload["recommended_width"] == [6, 10]


def test_width_uniform_agreement_is_zero_uncertainty(capsys) -> None:
    payload = _run(capsys, "width", "1.0")
    assert payload["uncertainty"] == 0.0
    assert payload["recommended_width"] == [2, 3]