"""Deterministic edge-branch contracts for the quantum reasoning controller."""

from __future__ import annotations

import pytest

import axiomize.reasoning.branch_controller as bc
from axiomize.workflow.reasoning_adapter import ModelCandidate, select_model


def _metrics(**overrides):
    values = {
        "evidence": 0.9,
        "verification": 0.9,
        "independence": 1.0,
        "information_gain": 0.7,
        "contradiction": 0.0,
        "unresolved_assumptions": 0.0,
        "normalized_cost": 0.0,
        "shared_assumption_ratio": 0.0,
        "semantic_similarity_to_leader": 0.0,
    }
    values.update(overrides)
    return bc.BranchMetrics(**values)


class TestClassification:
    def test_weak_active_branch_becomes_dormant(self) -> None:
        branch = bc.Branch(
            "weak",
            _metrics(
                evidence=0.05,
                verification=0.05,
                independence=0.1,
                information_gain=0.0,
                contradiction=0.1,
                unresolved_assumptions=0.6,
                normalized_cost=0.9,
            ),
        )
        assert bc.classify_branch(branch).state == bc.BranchState.DORMANT

    def test_strong_active_branch_stays_active(self) -> None:
        branch = bc.Branch("strong", _metrics())
        assert bc.classify_branch(branch).state == bc.BranchState.ACTIVE

    def test_revive_refuses_active_branches(self) -> None:
        branch = bc.Branch("active", _metrics())
        assert bc.should_revive(branch) is False

    def test_revive_refuses_dormant_without_previous_metrics(self) -> None:
        branch = bc.Branch("dormant", _metrics(), state=bc.BranchState.DORMANT)
        assert bc.should_revive(branch) is False

    def test_revive_on_verification_jump(self) -> None:
        previous = _metrics(verification=0.10)
        current = _metrics(verification=0.40)
        branch = bc.Branch(
            "revive-verification",
            current,
            state=bc.BranchState.DORMANT,
            previous_metrics=previous,
        )
        assert bc.should_revive(branch) is True

    def test_revive_on_contradiction_drop(self) -> None:
        previous = _metrics(contradiction=0.70)
        current = _metrics(contradiction=0.30)
        branch = bc.Branch(
            "revive-contradiction",
            current,
            state=bc.BranchState.DORMANT,
            previous_metrics=previous,
        )
        assert bc.should_revive(branch) is True

    def test_update_state_falls_back_to_classification(self) -> None:
        previous = _metrics(verification=0.30)
        current = _metrics(verification=0.35)
        branch = bc.Branch(
            "dormant-still-strong-now",
            current,
            state=bc.BranchState.DORMANT,
            previous_metrics=previous,
        )
        updated = bc.update_branch_state(branch)
        assert updated.state == bc.BranchState.ACTIVE


class TestEntropyAndWidth:
    def test_entropy_of_empty_collection_is_zero(self) -> None:
        assert bc.normalized_entropy([]) == 0.0

    def test_entropy_of_single_value_is_zero(self) -> None:
        assert bc.normalized_entropy([0.5]) == 0.0

    def test_entropy_of_all_zero_values_is_zero(self) -> None:
        assert bc.normalized_entropy([0.0, 0.0]) == 0.0

    def test_entropy_rejects_negative_values(self) -> None:
        with pytest.raises(ValueError):
            bc.normalized_entropy([-0.1, 0.5])

    def test_entropy_of_uniform_distribution_is_one(self) -> None:
        assert bc.normalized_entropy([1.0, 1.0, 1.0, 1.0]) == 1.0

    def test_uncertainty_from_branches_ignores_rejected(self) -> None:
        rejected = bc.Branch("bad", _metrics(), state=bc.BranchState.REJECTED)
        assert bc.uncertainty_from_branches([rejected]) == 0.0

    def test_uncertainty_of_uniform_survivors_is_one(self) -> None:
        branches = [bc.Branch(f"b{i}", _metrics()) for i in range(4)]
        assert bc.uncertainty_from_branches(branches) == 1.0

    def test_width_rejects_out_of_range_uncertainty(self) -> None:
        with pytest.raises(ValueError):
            bc.recommended_width(-0.1)
        with pytest.raises(ValueError):
            bc.recommended_width(1.1)

    def test_diversity_ratio_of_empty_collection_is_one(self) -> None:
        assert bc.diversity_ratio([]) == 1.0

    def test_diversity_ratio_rejects_invalid_threshold(self) -> None:
        with pytest.raises(ValueError):
            bc.diversity_ratio([0.2], duplicate_threshold=1.5)

    def test_diversity_ratio_rejects_out_of_range_similarities(self) -> None:
        with pytest.raises(ValueError):
            bc.diversity_ratio([0.2, 1.2])

    def test_diversity_ratio_penalizes_near_duplicates(self) -> None:
        assert bc.diversity_ratio([0.9, 0.2]) == 0.5


class TestCollapseEdges:
    def test_collapse_without_surviving_branches_is_blocked(self) -> None:
        rejected = bc.Branch("bad", _metrics(), state=bc.BranchState.REJECTED)
        can, reason, leader = bc.collapse_decision([rejected])
        assert can is False
        assert reason == "no surviving branch"
        assert leader is None

    def test_collapse_blocked_when_leader_score_is_low(self) -> None:
        weak = bc.Branch("weak", _metrics(evidence=0.2, verification=0.2))
        can, reason, leader = bc.collapse_decision([weak])
        assert can is False
        assert "below collapse threshold" in reason
        assert leader.branch_id == "weak"

    def test_collapse_blocked_when_verification_is_low(self) -> None:
        unverified = bc.Branch(
            "unverified",
            _metrics(evidence=1.0, verification=0.6, information_gain=0.9),
        )
        can, reason, _ = bc.collapse_decision([unverified])
        assert can is False
        assert "verification" in reason

    def test_collapse_blocked_by_high_information_runner_up(self) -> None:
        # With the reference thresholds this branch is unreachable (a runner-up
        # inside the unresolved margin is always inside the collapse margin), so
        # the contract is exercised with thresholds where both gates can pass.
        thresholds = bc.Thresholds(collapse_margin=0.05, unresolved_near_leader_margin=0.10)
        leader = bc.Branch(
            "leader",
            _metrics(evidence=1.0, verification=1.0, information_gain=0.9),
        )
        runner = bc.Branch(
            "runner",
            _metrics(evidence=0.85, verification=0.95, information_gain=0.9),
        )
        can, reason, selected = bc.collapse_decision([leader, runner], thresholds)
        assert can is False
        assert "unresolved" in reason
        assert selected.branch_id == "leader"

    def test_collapse_blocked_by_high_contradiction_leader(self) -> None:
        contradicted = bc.Branch(
            "contradicted",
            _metrics(evidence=1.0, verification=1.0, information_gain=0.9, contradiction=0.5),
        )
        can, reason, _ = bc.collapse_decision([contradicted])
        assert can is False
        assert "contradiction" in reason

    def test_ranking_excludes_rejected_and_sorts_desc(self) -> None:
        strong = bc.Branch("strong", _metrics(evidence=1.0, verification=1.0))
        medium = bc.Branch("medium", _metrics(evidence=0.6, verification=0.6))
        rejected = bc.Branch("bad", _metrics(), state=bc.BranchState.REJECTED)
        ranked = bc.rank_branches([medium, rejected, strong])
        assert [b.branch_id for b in ranked] == ["strong", "medium"]

    def test_effective_independence_uses_strongest_correlation_signal(self) -> None:
        shared = _metrics(independence=0.8, shared_assumption_ratio=0.5)
        similar = _metrics(independence=0.8, semantic_similarity_to_leader=0.7)
        assert bc.effective_independence(similar) < bc.effective_independence(shared)


class TestAdapterThresholds:
    def test_custom_thresholds_relax_collapse(self) -> None:
        moderate = ModelCandidate(
            candidate_id="moderate",
            evidence=0.7,
            verification=0.7,
            information_gain=0.5,
        )
        relaxed = bc.Thresholds(collapse_score=0.6, collapse_verification=0.6)
        can, _, leader, _ = select_model([moderate], thresholds=relaxed)
        assert can is True
        assert leader == "moderate"

    def test_default_thresholds_block_moderate_leader(self) -> None:
        moderate = ModelCandidate(
            candidate_id="moderate",
            evidence=0.7,
            verification=0.7,
            information_gain=0.5,
        )
        can, _, _, _ = select_model([moderate])
        assert can is False