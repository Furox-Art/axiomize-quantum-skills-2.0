"""Reasoning adapter: connect quantum-inspired branch control to Model IR selection.

The adapter translates model-family candidate scores into BranchMetrics so
competing mechanisms can be scored, ranked and collapsed with the same
deterministic rules as reasoning branches.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from axiomize.reasoning.branch_controller import (
    Branch,
    BranchMetrics,
    BranchState,
    Thresholds,
    collapse_decision,
    rank_branches,
)


@dataclass(frozen=True)
class ModelCandidate:
    """One candidate model family with explicit, externally supplied scores."""

    candidate_id: str
    evidence: float
    verification: float
    independence: float = 1.0
    information_gain: float = 0.5
    contradiction: float = 0.0
    unresolved_assumptions: float = 0.0
    normalized_cost: float = 0.0
    shared_assumption_ratio: float = 0.0
    semantic_similarity_to_leader: float = 0.0

    def to_branch(self) -> Branch:
        return Branch(
            branch_id=self.candidate_id,
            metrics=BranchMetrics(
                evidence=self.evidence,
                verification=self.verification,
                independence=self.independence,
                information_gain=self.information_gain,
                contradiction=self.contradiction,
                unresolved_assumptions=self.unresolved_assumptions,
                normalized_cost=self.normalized_cost,
                shared_assumption_ratio=self.shared_assumption_ratio,
                semantic_similarity_to_leader=self.semantic_similarity_to_leader,
            ),
            state=BranchState.ACTIVE,
        )


def select_model(
    candidates: Sequence[ModelCandidate],
    thresholds: Thresholds | None = None,
) -> tuple[bool, str, str | None, list[str]]:
    """Rank candidates and decide whether one model can be selected.

    Returns ``(can_select, reason, leader_id, ranking)`` where ranking lists
    candidate ids from strongest to weakest.
    """
    branches = [c.to_branch() for c in candidates]
    ranked = rank_branches(branches)
    ranking = [b.branch_id for b in ranked]
    if thresholds is None:
        can_select, reason, leader = collapse_decision(branches)
    else:
        can_select, reason, leader = collapse_decision(branches, thresholds)
    return (can_select, reason, leader.branch_id if leader else None, ranking)
