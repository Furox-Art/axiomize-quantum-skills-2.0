"""Structural tests for the skill-quality regression benchmark corpus (ideas.json)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
IDEAS = REPO / "benchmarks" / "ideas.json"


def _load_ideas() -> dict:
    return json.loads(IDEAS.read_text(encoding="utf-8"))


def test_ideas_json_is_valid_with_required_top_level_fields() -> None:
    ideas = _load_ideas()
    assert "version" in ideas
    assert "description" in ideas
    assert isinstance(ideas["cases"], list)
    assert len(ideas["cases"]) >= 10


def test_all_case_ids_are_unique() -> None:
    ids = [c["id"] for c in _load_ideas()["cases"]]
    assert len(ids) == len(set(ids)), "duplicate case ids"


def test_each_case_has_required_fields() -> None:
    required = {"id", "prompt", "must_contain", "expected_archetype",
                "min_lenses_built", "must_reject_at_least_one"}
    for case in _load_ideas()["cases"]:
        missing = required - set(case.keys())
        assert not missing, f"case {case.get('id')} missing {missing}"


def test_cases_cover_diverse_domains() -> None:
    archetypes = [c["expected_archetype"] for c in _load_ideas()["cases"]]
    text = " ".join(archetypes).lower()
    assert "physics" in text or "heat" in text or "pendulum" in text, "no physics case"
    assert "predator" in text or "epidemic" in text or "sir" in text, "no biology case"
    assert "chemistry" in text or "equilibrium" in text or "reactor" in text, "no chemistry case"
    assert "inventory" in text or "staffing" in text or "queue" in text, "no operations case"
    assert "causal" in text or "confounding" in text, "no causal case"


def test_closed_form_oracles_match_the_stated_model() -> None:
    """The five v1.2.0 cases must agree with the formulas in their prompts."""
    import math

    cases = {c["id"]: c["numeric_oracle"] for c in _load_ideas()["cases"] if "numeric_oracle" in c}
    assert cases["physics-rc-discharge"]["expected"] == pytest.approx(10.0 * math.exp(-1.0), abs=1e-4)
    assert cases["biology-doubling-culture"]["expected"] == pytest.approx(1000 * 2 ** (9 / 3))
    assert cases["chemistry-first-order-half-life"]["expected"] == pytest.approx(math.log(2) / 0.1, abs=1e-4)
    assert cases["operations-mm1-wait"]["expected"] == pytest.approx(4.0 / (5.0 * (5.0 - 4.0)))
    assert cases["causal-randomized-ate"]["expected"] == pytest.approx(12.0 - 8.0)


def test_rubric_file_exists() -> None:
    assert (REPO / "benchmarks" / "rubric.md").exists()
