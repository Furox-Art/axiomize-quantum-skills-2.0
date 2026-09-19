# Skills index — axiomize-quantum-skills-2.0

Two model-facing skills ship in this repo. Both are plain Markdown protocols;
the engine exposes deterministic reference implementations under `src/axiomize/`.

| Skill | File | Reference code | Tests |
|---|---|---|---|
| axiomize | `skills/axiomize/SKILL.md` | `src/axiomize/` (Model IR, engines, validation, export) | `tests/test_engine_*.py`, `test_adaptive_workflow.py` |
| quantum-reasoning | `skills/quantum-reasoning/SKILL.md` | `src/axiomize/reasoning/branch_controller.py` + `src/axiomize/workflow/reasoning_adapter.py` | `tests/test_reasoning_quantum.py` |

Quantum reasoning skill folder (`skills/quantum-reasoning/`):

- `SKILL.md` — model-facing protocol
- `VERSION` — protocol version (0.3.1 content, shipped inside 2.0.0)
- `docs/MEASUREMENT.md` — auditable formulas and thresholds
- `docs/COMPATIBILITY.md` — host compatibility contract
- `examples/usage.md`, `examples/host-integration.md` — task and host integration examples

Supporting material:

- `src/axiomize/reasoning/benchmark/` — evaluator, seed cases, JSON schemas, submission validator
- `skills/axiomize/tools/` — `check_skill.py`, `validate.py`, `fit.py`, `parallel_sweep.py`, `benchmark_runner.py`
- `pyproject.toml` — both skill folders are force-included in the built wheel
