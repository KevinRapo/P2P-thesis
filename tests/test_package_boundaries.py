"""MARLEM's packages depend one way, through core/ (src_thesis/README.md).

core/ imports nothing else from src_thesis; agents/, marketplace/, cooperation/
and adapters/ import only core/ and themselves; only environment/ combines them.
Every import counts, also the ones only used for type hints.
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src_thesis"

# package -> the src_thesis packages it may import besides itself
ALLOWED = {
    "core": (),
    "agents": ("core",),
    "marketplace": ("core",),
    "cooperation": ("core",),
    "adapters": ("core",),
    "environment": ("core", "agents", "marketplace", "cooperation", "adapters", "root"),
}


def _src_imports(path: Path) -> list[str]:
    """``src_thesis`` packages imported anywhere in the file (also in functions)."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        else:
            continue
        out += [n.split(".")[1] for n in names if n.startswith("src_thesis.")]
    return out


@pytest.mark.parametrize("package", list(ALLOWED))
def test_package_imports_only_what_it_may(package: str) -> None:
    allowed = {package, *ALLOWED[package]}
    wrong = [
        f"{path.relative_to(ROOT).as_posix()} imports src_thesis.{name}"
        for path in sorted((ROOT / package).rglob("*.py"))
        for name in _src_imports(path)
        if name not in allowed
    ]
    assert wrong == []


def test_core_has_no_third_party_runtime() -> None:
    # networkx is allowed: Location.distance_to is a shortest path on the grid graph.
    heavy = ("ray", "torch", "pandapower", "simbench", "gymnasium")
    wrong = [
        f"{path.name} imports {n}"
        for path in ROOT.joinpath("core").rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for n in (
            [a.name for a in node.names]
            if isinstance(node, ast.Import)
            else [node.module or ""]
        )
        if n.split(".")[0] in heavy
    ]
    assert wrong == []
