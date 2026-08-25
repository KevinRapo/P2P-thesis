"""Run a small, non-learning reproducibility protocol check.

This is deliberately not a thesis experiment: it validates that the declared
split, manifest, seed-level records, and summary path work together before a
larger training study is launched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from src.agent.der import DERAgent
from src.environment.baselines import random_valid_actions
from src.environment.experiment import (EpisodeRecordStore, ScenarioSplit,
                                        run_declared_episodes)
from src.environment.lem import LocalEnergyMarket
from src.environment.train import RLTrainer
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig


SMOKE_SPLIT = ScenarioSplit(
    train_ids=("synthetic-train",),
    validation_ids=("synthetic-validation",),
    test_ids=("synthetic-test",),
    training_seeds=(101, 102, 103),
    evaluation_seeds=(201,),
    test_seeds=(301, 302, 303),
)


def build_smoke_config(scenario_id: str) -> dict[str, Any]:
    """Build a fresh one-step scenario for the declared smoke-test IDs."""
    if scenario_id not in SMOKE_SPLIT.test_ids:
        raise ValueError(f"Unsupported reproducibility-smoke scenario: {scenario_id}")
    grid = GridNetwork(GridTopology.LINE, num_nodes=2, capacity=10.0, seed=1)
    return {
        "scenario_id": scenario_id,
        "max_steps": 1,
        "seed": 301,
        "market_config": MarketConfig(min_price=0.0, max_price=10.0, max_quantity=10.0),
        "grid_network": grid,
        "dso": DSOAgent("DSO", [1.0], [2.0], grid),
        "agents": [
            DERAgent("buyer", 10.0, generation_profile=[0.0], demand_profile=[2.0]),
            DERAgent("seller", 10.0, generation_profile=[2.0], demand_profile=[0.0]),
        ],
    }


def run_smoke(output_directory: str | Path) -> dict[str, Any]:
    """Write a three-seed baseline run and return its verifiable summary."""
    output_directory = Path(output_directory)
    scenario_id = SMOKE_SPLIT.test_ids[0]
    manifest_path = RLTrainer.write_run_manifest(
        build_smoke_config(scenario_id),
        output_directory,
        {"purpose": "non-learning reproducibility smoke",
         "scenario_split": SMOKE_SPLIT.as_dict(),
         "scenario_split_sha256": SMOKE_SPLIT.fingerprint()},
    )
    records = EpisodeRecordStore(output_directory)
    completed = run_declared_episodes(
        lambda declared_scenario_id: LocalEnergyMarket(build_smoke_config(declared_scenario_id)),
        random_valid_actions,
        SMOKE_SPLIT,
        scenario_id,
        "test",
        records,
    )
    return {
        "manifest": str(manifest_path),
        "manifest_verified": RLTrainer.verify_run_manifest(manifest_path),
        "scenario_split_sha256": SMOKE_SPLIT.fingerprint(),
        "records": completed,
        "episode_return_summary": EpisodeRecordStore.summarize(records.records(), "episode_return"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        help="New directory for the manifest and JSONL records.")
    arguments = parser.parse_args()
    output = arguments.output or Path("tmp") / f"reproducibility-smoke-{uuid4().hex[:8]}"
    print(json.dumps(run_smoke(output), indent=2))


if __name__ == "__main__":
    main()
