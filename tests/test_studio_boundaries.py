"""Architecture guard: layers only reach what the architecture README §2.1 allows.

See docs_thesis/thesis/architecture/README.md §2.1–§2.3.
- studio/ imports only nicegui/plotly/stdlib and src_thesis.application.
- application/ never imports MARLEM runtime, pandapower, simbench, Ray or torch.
  Real services reach infrastructure through adapters/ (the grid catalog calls
  adapters.grid) and the grid contract; building the services loads none of it.
- Only adapters/ imports pandapower and simbench.
- MARLEM's trainer (marl/train.py, inference.py) loads the market only when it is
  the chosen environment, and the RL testbench reaches MARLEM only through the
  trainer (D-16).
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "src_thesis"
HEAVY = ("pandapower", "simbench", "ray", "torch", "networkx", "src.")
MARLEM_RUNTIME = (
    "src_thesis.marketplace",
    "src_thesis.marl",
    "src_thesis.cooperation",
    "src_thesis.environment",
    "src_thesis.agents",
)
APPLICATION_ALLOWED = ("src_thesis.core.grid_contract",)
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


def test_experiment_layer_never_imports_application_or_studio() -> None:
    forbidden = ("src_thesis.application", "src_thesis.studio")
    assert _violations("experiments", forbidden) == []


def _top_level_imports(path: Path) -> list[str]:
    """Imports at module level (not inside functions)."""
    names = []
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            names += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_marl_trainer_does_not_load_the_market() -> None:
    # The market is RLTrainer's default environment, imported only when used.
    for name in ("train.py", "inference.py"):
        names = _top_level_imports(ROOT / "marl" / name)
        market = ("src_thesis.marketplace", "src_thesis.environment")
        assert [n for n in names if n.startswith(market)] == []


def test_rl_testbench_reaches_marlem_only_through_the_trainer() -> None:
    allowed = (
        "src_thesis.rl_testbench",
        "src_thesis.marl.train",
        "src_thesis.marl.base",
        "src_thesis.experiments.models",
    )
    forbidden = ("src_thesis.", "pandapower", "simbench", "networkx")
    assert _violations("rl_testbench", forbidden, allowed) == []


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


def test_building_the_services_loads_no_pandapower() -> None:
    code = (
        "import sys; from src_thesis.application.container import build_services; "
        "build_services(); "
        "print(any(m.split('.')[0] in ('pandapower', 'simbench') for m in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True
    )
    assert result.stdout.strip() == "False", result.stderr


def test_services_satisfy_every_page_call(tmp_path) -> None:
    pytest.importorskip("nicegui")
    pytest.importorskip("pandapower")
    from src_thesis.application.container import build_services

    s = build_services(home=tmp_path)
    draft = s.config.new_from_preset("case6-3x3")
    source = s.grid.list_networks()[0].source
    assert len(s.config.expand(draft)) == 33  # 27 learning runs + 6 baseline runs
    assert s.validation.validate(draft).ok
    assert s.grid.preview_powerflow(source, "2016-06-15", 18).converged
    assert s.results.matrix("case6-3x3", "p2p_share").rows == ["CTCE", "CTDE", "DTDE"]
    import src_thesis.studio.app  # noqa: F401  registers all routes without error
