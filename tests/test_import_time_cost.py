"""Regression coverage for C3: heavy libraries stay off the import path.

``scipy`` and ``sympy`` were imported at module scope on the ``import
axiomize`` chain (``axiomize.bayesian.likelihoods`` via ``scipy.special``,
``axiomize.standards_export`` via ``sympy``), so every CLI invocation --
including ``axiomize tools`` and the doctor surface -- paid their import cost.
Both are function-level now; a fresh interpreter importing the tool surface
must not load them.
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_tool_surface_import_does_not_load_heavy_libraries() -> None:
    """A fresh interpreter importing the tool surface must not load SciPy/SymPy.

    Runs in a subprocess because the pytest process itself has long since
    imported them.
    """
    code = (
        "import sys;"
        "import axiomize.tools.inventory;"
        "from axiomize.application import services;"
        "heavy = [m for m in ('scipy', 'sympy', 'matplotlib', 'networkx',"
        " 'statsmodels', 'z3', 'cvxpy', 'casadi', 'control', 'pandas') if m in sys.modules];"
        "assert not heavy, f'heavy libraries loaded at import time: {heavy}';"
        "print('clean')"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=180, cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, result.stderr
    assert "clean" in result.stdout


def test_heavy_imports_still_work_when_the_features_run() -> None:
    """The lazy imports must not have broken the features that use them."""
    from axiomize.bayesian.likelihoods import log_likelihood

    good = log_likelihood("normal", [1.0, 2.0, 3.0], [1.0, 2.0, 3.0], sigma=1.0)
    bad = log_likelihood("normal", [1.0, 2.0, 3.0], [50.0, -50.0, 90.0], sigma=1.0)
    assert math.isfinite(good) and math.isfinite(bad)
    assert bad < good
    # poisson and student_t exercise gammaln, the symbol that was module-level.
    for family, kwargs in (("poisson", {}), ("student_t", {"sigma": 1.0, "df": 4.0})):
        value = log_likelihood(family, [1.0, 2.0], [50.0, 60.0], **kwargs)
        assert math.isfinite(value)
        assert value < 0.0
