"""Make the editable install behave like the wheel for ``axiomize.tools``.

The wheel maps ``skills/axiomize/tools`` onto ``axiomize/tools`` via
``[tool.hatch.build.targets.wheel.force-include]`` in ``pyproject.toml``,
because that directory backs seven of the nine ``axiomize-*`` console entry
points. An editable install only puts ``src/`` on ``sys.path``, so
``import axiomize.tools.validate`` raises ``ModuleNotFoundError`` and every
skill-tool entry point is broken for a contributor running from a checkout::

    $ pip install -e . --no-deps
    $ axiomize-validate --model sir --beta 0.3 --gamma 0.1
    ModuleNotFoundError: No module named 'axiomize.tools.validate'

This conftest closes that gap for the test suite. It is a no-op when the
package is installed normally, because the tools are then already on disk
inside site-packages.

``tests/test_tools.py`` works around the same gap by appending
``skills/axiomize/tools`` to ``sys.path`` and importing the modules under their
bare names (``import validate``). That workaround is left in place: it is
existing test code owned elsewhere, and this shim does not conflict with it.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
SKILL_TOOLS = REPO_ROOT / "skills" / "axiomize" / "tools"


def _extend_axiomize_tools() -> bool:
    """Append the skill-tools directory to ``axiomize.tools.__path__``.

    Returns True when the shim was applied.
    """
    if not SKILL_TOOLS.is_dir():
        return False

    # Only relevant for a source checkout: in an installed package the tools
    # already live inside the package directory.
    if not (REPO_ROOT / "src" / "axiomize" / "__init__.py").is_file():
        return False

    try:
        import axiomize.tools as tools_pkg
    except ImportError:
        # axiomize itself is not importable; nothing to extend.
        return False

    tools_dir = str(SKILL_TOOLS)
    path_entries = getattr(tools_pkg, "__path__", None)
    if path_entries is None:
        return False
    if tools_dir in list(path_entries):
        return True

    path_entries.append(tools_dir)

    # Pre-load the tools under their package-qualified names so the declared
    # entry points (axiomize.tools.validate:main, ...) resolve. A tool that
    # fails on an absent optional dependency is skipped: its TOOL_UNAVAILABLE
    # behaviour is covered by tests/test_gap1_pymc_jax.py, not by this shim.
    for source in sorted(SKILL_TOOLS.glob("*.py")):
        if source.name == "__init__.py":
            continue
        try:
            importlib.import_module(f"axiomize.tools.{source.stem}")
        except ImportError:
            continue

    return True


_APPLIED = _extend_axiomize_tools()


def pytest_report_header(config) -> str:  # noqa: ARG001
    """State plainly in the pytest header whether the shim is active.

    Without this the shim is invisible: a checkout run and an installed-package
    run produce identical-looking output despite resolving different code for
    ``axiomize.tools.*``.
    """
    if _APPLIED:
        relative = SKILL_TOOLS.relative_to(REPO_ROOT).as_posix()
        return f"axiomize.tools: source shim active ({relative})"
    return "axiomize.tools: using installed package layout"


if __name__ == "__main__":  # pragma: no cover - manual check, see module docstring
    print("active" if _APPLIED else "inactive", file=sys.stderr)
