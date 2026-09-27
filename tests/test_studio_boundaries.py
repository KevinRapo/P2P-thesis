"""Architecture guard: layers only reach what 04-services.md §1 allows.

See docs/thesis/architecture/01-paper-to-code-map.md §5 and 04-services.md §1, §7.
- studio/ imports only nicegui/plotly/stdlib and src_thesis.application.
- application/ never imports MARLEM runtime, pandapower, simbench, Ray or torch.
  Real services reach infrastructure through adapters/ (the grid catalog calls
  adapters.grid) and the grid contract; the demo services import nothing of it.
- Only adapters/ imports pandapower and simbench.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "src_thesis"
HEAVY = ("pandapower", "simbench", "ray", "torch", "networkx", "src.")
MARLEM_RUNTIME = ("src_thesis.marketplace", "src_thesis.marl", "src_thesis.cooperation")
APPLICATION_ALLOWED = ("src_thesis.marketplace.grid.contract_new",)
STUDIO_EXTRA = ("src_thesis.adapters", "src_thesis.experiments")


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def _violations(
    package: str, forbidden: tuple[str, ...], allowed: tuple[str, ...] = ()
) -> list[str]:
    out = []
    for path in (ROOT / package).rglob("*.py"):
        for name in _imports(path):
            if name.startswith(allowed):
                continue
            if name.startswith(forbidden) or name == "src":
                out.append(f"{path.relative_to(ROOT)} imports {name}")
    return out


def test_studio_imports_only_application_layer() -> None:
    forbidden = HEAVY + MARLEM_RUNTIME + STUDIO_EXTRA
    assert _violations("studio", forbidden) == []


def test_application_layer_is_free_of_marlem_runtime() -> None:
    forbidden = HEAVY + MARLEM_RUNTIME
    assert _violations("application", forbidden, APPLICATION_ALLOWED) == []


def test_only_adapters_import_pandapower_and_simbench() -> None:
    out = []
    for path in ROOT.rglob("*.py"):
        if path.relative_to(ROOT).parts[0] == "adapters":
            continue
        out += [
            f"{path.relative_to(ROOT)} imports {name}"
            for name in _imports(path)
            if name.startswith(("pandapower", "simbench"))
        ]
    assert out == []


def test_demo_services_do_not_load_pandapower() -> None:
    code = (
        "import sys; from src_thesis.application import build_services; "
        "build_services('demo'); "
        "print(any(m.split('.')[0] in ('pandapower', 'simbench') for m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True
    )
    assert result.stdout.strip() == "False", result.stderr


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
