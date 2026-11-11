"""The layer rule of ``AGENTS.md``: ``core/market`` (and ``core/grid``, ``core/config``)
import nothing from ``core/env``, ``core/rl`` or ``core/runner``. The references and
the indicators (``ceiling.py``, ``indicators.py``) are market scoring, so they live
in ``core/market`` and the runner reads them, never the other way round."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

CORE = Path(__file__).resolve().parents[2] / "core"
ABOVE = ("core.env", "core.rl", "core.runner")


def imports_of(path: Path) -> set[str]:
    found = set()

    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            found |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
            found |= {f"{node.module}.{a.name}" for a in node.names}

    return found


@pytest.mark.parametrize("package", ["market", "grid", "config"])
def test_nothing_below_the_runner_imports_it_or_the_env_or_rl(package):
    for path in sorted((CORE / package).rglob("*.py")):
        bad = {
            name
            for name in imports_of(path)
            if any(name == a or name.startswith(a + ".") for a in ABOVE)
        }
        assert not bad, f"{path.relative_to(CORE.parent)} imports {sorted(bad)}"


def test_the_references_and_indicators_are_in_the_market():
    assert (CORE / "market" / "ceiling.py").is_file()
    assert (CORE / "market" / "indicators.py").is_file()
    assert not (CORE / "runner" / "ceiling.py").exists()
    assert not (CORE / "runner" / "indicators.py").exists()
