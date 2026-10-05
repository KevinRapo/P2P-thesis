"""Every public module, class and function of the platform code has a docstring.

The API reference (docs_site/) is generated from these docstrings. The original
MARLEM packages are rewritten in R1 and are not checked here yet.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src_thesis"
CHECKED = [
    "experiments",
    "application",
    "studio",
    "adapters/grid/simbench_new.py",
    "core/grid_contract.py",
]


def _files() -> list[Path]:
    out = []
    for item in CHECKED:
        path = ROOT / item
        out += [path] if path.is_file() else sorted(path.rglob("*.py"))
    return out


def _missing(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT).as_posix()
    out = [] if ast.get_docstring(tree) or path.name == "__init__.py" else [rel]

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if child.name.startswith("_"):
                    continue
                if not ast.get_docstring(child):
                    out.append(f"{rel}:{child.lineno} {prefix}{child.name}")
                if isinstance(child, ast.ClassDef):
                    walk(child, f"{prefix}{child.name}.")

    walk(tree, "")
    return out


def test_public_platform_code_is_documented() -> None:
    missing = [m for path in _files() for m in _missing(path)]
    assert missing == [], "Add a docstring to:\n" + "\n".join(missing)
