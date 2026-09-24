"""Architecture guard: the Studio and the application layer stay free of MARLEM internals.

See docs/thesis/architecture/01-paper-to-code-map.md §5 and 04-services.md §1.
- studio/ may import only nicegui/plotly/stdlib and src_thesis.application.
- application/ must not import MARLEM runtime, grid adapters, pandapower, simbench, Ray or torch
  (real services will reach them through experiments/ later; the demo services never do).
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "src_thesis"
MARLEM_AND_HEAVY = (
    "src_thesis.marketplace",
    "src_thesis.marl",
    "src_thesis.cooperation",
    "src_thesis.adapters",
    "pandapower",
    "simbench",
    "ray",
    "torch",
    "networkx",
    "src.",
)
STUDIO_EXTRA = ("src_thesis.experiments",)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def _violations(package: str, forbidden: tuple[str, ...]) -> list[str]:
    out = []
    for path in (ROOT / package).rglob("*.py"):
        for name in _imports(path):
            if name.startswith(forbidden) or name == "src":
                out.append(f"{path.relative_to(ROOT)} imports {name}")
    return out


def test_studio_imports_only_application_layer() -> None:
    assert _violations("studio", MARLEM_AND_HEAVY + STUDIO_EXTRA) == []


def test_application_layer_is_free_of_marlem_runtime() -> None:
    assert _violations("application", MARLEM_AND_HEAVY) == []


def test_demo_services_satisfy_every_page_call() -> None:
    pytest.importorskip("nicegui")
    from src_thesis.application import build_services

    s = build_services("demo")
    draft = s.config.new_from_preset("case6-3x3")
    source = s.grid.list_networks()[0].source
    assert len(s.config.expand(draft)) == 27
    assert s.validation.validate(draft).ok
    assert s.grid.preview_powerflow(source, "2016-06-15", 18).converged
    assert s.results.matrix("case6-3x3", "p2p_share").rows == ["CTCE", "CTDE", "DTDE"]
    import src_thesis.studio.pages  # noqa: F401  registers all routes without error
