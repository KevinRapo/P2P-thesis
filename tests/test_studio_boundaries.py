"""Architecture guard: layers only reach what the architecture README §2.1 allows.

See docs_thesis/thesis/architecture/README.md §2.1–§2.3.
- platform/studio/ imports only nicegui/plotly/stdlib and platform/services/.
- platform/services/ never imports MARLEM's runtime (market, DSO, agents,
  environment, cooperation, marl), pandapower, simbench, Ray or torch. It reaches
  the grid through marlem/grid/ (SimBench adapter, placement, contract); building
  the services loads none of it.
- Only marlem/grid/simbench.py imports pandapower and simbench.
- MARLEM's trainer (marlem/marl/train.py, inference.py) loads the market only when
  it is the chosen environment, and the RL testbench reaches MARLEM only through
  the trainer (D-16).
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
    "src_thesis.marlem.market",
    "src_thesis.marlem.dso",
    "src_thesis.marlem.marl",
    "src_thesis.marlem.cooperation",
    "src_thesis.marlem.environment",
    "src_thesis.marlem.agents",
    "src_thesis.marlem.simulation",
)
APPLICATION_ALLOWED = (
    "src_thesis.marlem.grid.contract",
    "src_thesis.marlem.simulation.spec",
    "src_thesis.marlem.simulation.policy",
    "src_thesis.marlem.simulation.checks",
    "src_thesis.marlem.simulation.catalog",
)
STUDIO_EXTRA = ("src_thesis.marlem", "src_thesis.platform.kernel")


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
    assert _violations("platform/studio", forbidden) == []


def test_application_layer_is_free_of_marlem_runtime() -> None:
    forbidden = HEAVY + MARLEM_RUNTIME
    assert _violations("platform/services", forbidden, APPLICATION_ALLOWED) == []


def test_experiment_layer_never_imports_application_or_studio() -> None:
    forbidden = ("src_thesis.platform.services", "src_thesis.platform.studio")
    assert _violations("platform/kernel", forbidden) == []


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
        names = _top_level_imports(ROOT / "marlem" / "marl" / name)
        market = ("src_thesis.marlem.market", "src_thesis.marlem.environment")
        assert [n for n in names if n.startswith(market)] == []


def test_rl_testbench_reaches_marlem_only_through_the_trainer() -> None:
    allowed = (
        "src_thesis.platform.testbench",
        "src_thesis.marlem.marl.train",
        "src_thesis.marlem.marl.base",
        "src_thesis.platform.kernel.models",
    )
    forbidden = ("src_thesis.", "pandapower", "simbench", "networkx")
    assert _violations("platform/testbench", forbidden, allowed) == []


def test_only_the_simbench_adapter_imports_pandapower_and_simbench() -> None:
    out = []
    for path in ROOT.rglob("*.py"):
        if path.relative_to(ROOT).as_posix() == "marlem/grid/simbench.py":
            continue
        out += [
            f"{path.relative_to(ROOT)} imports {name}"
            for name in _imports(path)
            if name.startswith(("pandapower", "simbench"))
        ]
    assert out == []


def test_building_the_services_loads_no_pandapower() -> None:
    code = (
        "import sys; from src_thesis.platform.services.container import build_services; "
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
    from src_thesis.platform.services.container import build_services

    s = build_services(home=tmp_path)
    draft = s.config.new_from_preset("case6-3x3")
    source = s.grid.list_networks()[0].source
    assert len(s.config.expand(draft)) == 33  # 27 learning runs + 6 baseline runs
    assert s.validation.validate(draft).ok
    assert s.grid.preview_powerflow(source, "2016-06-15", 18).converged
    assert s.results.matrix("case6-3x3", "p2p_share").rows == ["CTCE", "CTDE", "DTDE"]
    import src_thesis.platform.studio.app  # noqa: F401  registers all routes without error
