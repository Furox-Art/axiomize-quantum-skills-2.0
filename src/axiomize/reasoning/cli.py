"""CLI for quantum-inspired branch scoring and Model IR selection."""

from __future__ import annotations

import argparse
import json
import sys

from axiomize.reasoning.branch_controller import (
    Branch,
    BranchMetrics,
    BranchState,
    collapse_decision,
    rank_branches,
    recommended_width,
    uncertainty_from_branches,
)
from axiomize.workflow.reasoning_adapter import ModelCandidate, select_model


def _cmd_score(args: argparse.Namespace) -> int:
    metrics = BranchMetrics(
        evidence=args.evidence,
        verification=args.verification,
        independence=args.independence,
        information_gain=args.information_gain,
        contradiction=args.contradiction,
        unresolved_assumptions=args.unresolved_assumptions,
        normalized_cost=args.normalized_cost,
        shared_assumption_ratio=args.shared_assumption_ratio,
        semantic_similarity_to_leader=args.semantic_similarity,
    )
    branch = Branch(branch_id=args.id, metrics=metrics, state=BranchState.ACTIVE)
    can_collapse, reason, leader = collapse_decision([branch])
    print(json.dumps({"branch": branch.branch_id, "can_collapse": can_collapse, "reason": reason}, indent=2))
    return 0


def _cmd_select(args: argparse.Namespace) -> int:
    payload = json.loads(args.candidates.read_text(encoding="utf-8"))
    candidates = [ModelCandidate(**item) for item in payload["candidates"]]
    can_select, reason, leader_id, ranking = select_model(candidates)
    print(json.dumps({"can_select": can_select, "reason": reason, "leader": leader_id, "ranking": ranking}, indent=2))
    return 0


def _cmd_width(args: argparse.Namespace) -> int:
    branches = [
        Branch(branch_id=f"b{i}", metrics=BranchMetrics(*( [v] * 9 )), state=BranchState.ACTIVE)
        for i, v in enumerate(args.scores)
    ]
    uncertainty = uncertainty_from_branches(branches)
    low, high = recommended_width(uncertainty)
    print(json.dumps({"uncertainty": uncertainty, "recommended_width": [low, high]}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="axiomize-reason", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    score = sub.add_parser("score", help="score one branch and check collapse")
    score.add_argument("--id", default="branch-1")
    for field in (
        "evidence", "verification", "independence", "information_gain",
        "contradiction", "unresolved_assumptions", "normalized_cost",
        "shared_assumption_ratio",
    ):
        score.add_argument(f"--{field.replace('_', '-')}", type=float, default=0.5)
    score.add_argument("--semantic-similarity", type=float, default=0.0)
    score.set_defaults(func=_cmd_score)

    select = sub.add_parser("select", help="rank model candidates from a JSON file")
    select.add_argument("--candidates", type=__import__("pathlib").Path, required=True)
    select.set_defaults(func=_cmd_select)

    width = sub.add_parser("width", help="estimate uncertainty width from scores")
    width.add_argument("scores", nargs="+", type=float)
    width.set_defaults(func=_cmd_width)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
