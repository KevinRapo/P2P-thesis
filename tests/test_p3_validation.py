"""Focused regression tests for defensive input validation and repository docs (P3)."""

import json
from pathlib import Path
import re

import pytest

from src.agent.der import DERAgent
from src.grid.base import GridTopology, Location
from src.grid.network import GridNetwork
from src.market.matching import MarketConfig
from src.market.dso import DSOAgent
from src.market.matching import OrderMatcher
from src.market.order import Order
from src.market.order import Trade
from src.market.validation import Validator
from src.profile.der import DERProfileHandler
from src.profile.dso import DSOProfileHandler


def test_grid_rejects_negative_capacity_before_normalizing() -> None:
    with pytest.raises(ValueError, match="capacity"):
        GridNetwork(capacity=-1.0)


def test_procedural_topology_requires_two_nodes() -> None:
    with pytest.raises(ValueError, match="at least 2"):
        GridNetwork(topology=GridTopology.LINE, num_nodes=1)


def test_default_constructed_agents_do_not_share_profiles() -> None:
    first = DERAgent("first", 1.0)
    second = DERAgent("second", 1.0)
    first.generation_profile.append(1.0)

    assert second.generation_profile == []


def test_market_config_rejects_non_enum_mechanism_cleanly() -> None:
    with pytest.raises(ValueError, match="Unknown pricing mechanism"):
        MarketConfig(price_mechanism="average")


def test_settlement_proof_of_work_is_not_created_by_default() -> None:
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2)
    matcher = OrderMatcher(2, MarketConfig(), grid, DSOAgent("DSO", [1.0], [1.0], grid))

    assert matcher.validator is None


def test_profile_handlers_accept_integer_bounds() -> None:
    DERProfileHandler(min_quantity=0, max_quantity=10)
    DSOProfileHandler(min_price=0, max_price=10)


def test_dso_rejects_orders_referencing_an_unknown_grid_node() -> None:
    grid = GridNetwork(topology=GridTopology.LINE, num_nodes=2)
    dso = DSOAgent("DSO", [0.1], [0.2], grid)
    buyer = Order("buy", "buyer", 0.2, 1.0, True, 0,
                  Location("missing", 0.0, 0.0))
    seller = Order("sell", "seller", 0.1, 1.0, False, 0,
                   Location("0", 0.0, 0.0))

    assert not dso.validate_grid_constraints(buyer, seller)


def test_optional_settlement_log_detects_changes_to_any_settlement_field() -> None:
    validator = Validator(block_size=1)
    trade = Trade("buyer", "seller", 1.0, 2.0, 0.0, distance=3.0,
                  transmission_loss=0.1, fees=0.2, buyer_order_id="buy",
                  seller_order_id="sell")
    validator.add_trade(trade)

    assert validator.verify_chain()
    validator.chain[-1].trades[0].fees = 0.3
    assert not validator.verify_chain()


def test_readme_inventory_and_notebook_paths_match_the_repository() -> None:
    root = Path(__file__).resolve().parents[1]
    readme = (root / "README.md").read_text(encoding="utf-8")
    notebook_names = [
        "case1_market_mechanisms.ipynb", "case2_agent_heterogeneity.ipynb",
        "case3_dso_intervention.ipynb", "case4_grid_constraints.ipynb",
        "case5_battery_coordination.ipynb", "case6_implicit_cooperation.ipynb",
        "case7_scalability_analysis.ipynb", "case_studies_index.ipynb",
    ]

    assert "cases/" not in readme
    assert "STAR" not in readme and "TREE" not in readme
    assert "train_batch_size=16" not in readme
    assert "train_batch_size=24" in readme
    assert all((root / "notebooks" / name).is_file() and name in readme
               for name in notebook_names[:-1])


def test_case6_has_no_machine_local_checkpoint_and_remains_valid_notebook_json() -> None:
    root = Path(__file__).resolve().parents[1]
    notebook = json.loads((root / "notebooks/case6_implicit_cooperation.ipynb").read_text(encoding="utf-8"))
    source = "".join(line for cell in notebook["cells"] for line in cell.get("source", []))

    assert "downloads/TRAIN" not in source
    assert "downloads/INFERENCE" not in source
    assert "CHECKPOINT_PATH_INFERENCE = None" in source


def test_all_notebooks_have_parseable_json_and_python_code_cells() -> None:
    root = Path(__file__).resolve().parents[1]

    for path in (root / "notebooks").glob("*.ipynb"):
        notebook = json.loads(path.read_text(encoding="utf-8"))
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                compile("".join(cell["source"]), f"{path}:{index}", "exec")


def test_case_notebooks_resolve_the_project_root_and_use_contract_price_units() -> None:
    root = Path(__file__).resolve().parents[1]

    for path in (root / "notebooks").glob("case[1-7]_*.ipynb"):
        source = "".join(line for cell in json.loads(path.read_text(encoding="utf-8"))["cells"]
                         for line in cell.get("source", []))
        assert 'project_root = Path.cwd()' in source
        assert '(project_root / "src").is_dir()' in source
        assert "/MWh" not in source


def test_case7_requires_an_explicit_opt_in_for_training_workloads() -> None:
    root = Path(__file__).resolve().parents[1]
    notebook = json.loads((root / "notebooks/case7_scalability_analysis.ipynb").read_text(encoding="utf-8"))
    source = "".join(line for cell in notebook["cells"] for line in cell.get("source", []))

    assert "RUN_TRAINING_SMOKE = False" in source
    assert "RUN_FULL_ANALYSIS = False" in source
    assert "TRAINING_MODES = [TrainingMode.CTCE, TrainingMode.DTDE]" in source


def test_case_notebooks_do_not_run_disabled_ctde_or_keep_its_failure_output() -> None:
    root = Path(__file__).resolve().parents[1]
    names = [
        "case1_market_mechanisms.ipynb",
        "case2_agent_heterogeneity.ipynb",
        "case3_dso_intervention.ipynb",
        "case4_grid_constraints.ipynb",
        "case5_battery_coordination.ipynb",
    ]

    for name in names:
        notebook = json.loads((root / "notebooks" / name).read_text(encoding="utf-8"))
        source = "".join(line for cell in notebook["cells"] for line in cell.get("source", []))
        output = "".join(
            text if isinstance(text := output_item.get("text", ""), str) else "".join(text)
            for cell in notebook["cells"]
            for output_item in cell.get("outputs", [])
        )

        assert "TRAINING_MODE = TrainingMode.CTDE" not in source
        assert "CTDE is disabled" not in output


def test_local_markdown_links_point_to_existing_artifacts() -> None:
    root = Path(__file__).resolve().parents[1]
    markdown_files = [root / "README.md", *(root / "docs").glob("*.md"),
                      root / "notebooks" / "README.md"]

    for markdown in markdown_files:
        for target in re.findall(r"\]\(([^)]+)\)", markdown.read_text(encoding="utf-8")):
            target = target.split("#", 1)[0]
            if not target or "://" in target or target.startswith("mailto:"):
                continue
            assert (markdown.parent / target).resolve().exists(), f"Broken link: {markdown}: {target}"


def test_focused_gate_has_a_conda_ci_workflow() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/validation.yml").read_text(encoding="utf-8")

    assert "conda-incubator/setup-miniconda@v3" in workflow
    assert "environment-file: environment.yml" in workflow
    assert "pytest -q" in workflow


def test_notebook_validation_outputs_are_ignored() -> None:
    root = Path(__file__).resolve().parents[1]
    ignore_rules = (root / ".gitignore").read_text(encoding="utf-8")

    assert "downloads/case5/" in ignore_rules
    assert "notebooks/tmp/" in ignore_rules
    assert "results/lem_*/" in ignore_rules
