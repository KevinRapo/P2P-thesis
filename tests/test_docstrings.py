"""Every public module, class and function of the new code has a docstring, and
every package says in its ``__init__.py`` what it is for (the map in
src_thesis/README.md is built from those lines).

The API reference (docs_site/) is generated from these docstrings. The original
MARLEM modules are rewritten in R1 and are not checked here yet.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src_thesis"
CHECKED = [
    "platform/kernel",
    "platform/services",
    "platform/studio",
    "marlem/core/interfaces.py",
    "marlem/grid/simbench.py",
    "marlem/grid/placement.py",
    "marlem/grid/contract.py",
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


def test_every_package_says_what_it_is_for() -> None:
    silent = [
        init.parent.relative_to(ROOT).as_posix()
        for init in sorted(ROOT.rglob("__init__.py"))
        if "__pycache__" not in init.parts
        and not ast.get_docstring(ast.parse(init.read_text(encoding="utf-8")))
    ]
    assert silent == [], "Give these packages a one-line docstring:\n" + "\n".join(
        silent
    )
