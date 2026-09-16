"""Quantum-reasoning benchmark protocol: evaluator, schemas and submission validator.

This subpackage is the machine-readable part of the `skills/quantum-reasoning`
skill. Both scripts also run standalone:

    python src/axiomize/reasoning/benchmark/evaluate.py --help
    python src/axiomize/reasoning/benchmark/validate_submission.py --allow-empty
"""

__all__ = ["evaluate", "validate_submission"]