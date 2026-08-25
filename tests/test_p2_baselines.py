"""Smoke and semantics tests for non-learning experiment baselines (P2-06)."""

import numpy as np

from src.agent.der import DERAgent
from src.environment.baselines import (dso_fallback_actions, full_information_greedy_actions,
                                       random_valid_actions, run_baseline_episode)
from src.environment.lem import LocalEnergyMarket
from src.environment.experiment import EpisodeRecordStore, ScenarioSplit, run_declared_episodes
from src.environment.reproducibility_smoke import SMOKE_SPLIT, run_smoke
from src.environment.train import RLTrainer
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig


def _environment() -> LocalEnergyMarket:
    grid = GridNetwork(GridTopology.LINE, num_nodes=2, capacity=10.0)
    return LocalEnergyMarket({
        "max_steps": 1, "seed": 1,
        "market_config": MarketConfig(max_price=10.0, max_quantity=10.0),
        "grid_network": grid,
        "dso": DSOAgent("DSO", [1.0], [2.0], grid),
        "agents": [DERAgent("buyer", 10.0, generation_profile=[0.0], demand_profile=[2.0]),
                   DERAgent("seller", 10.0, generation_profile=[2.0], demand_profile=[0.0])],
    })


def test_baselines_emit_feasible_signed_actions_and_distinct_matching_intent() -> None:
    environment = _environment()
    random_actions = random_valid_actions(environment, seed=4)
    fallback_actions = dso_fallback_actions(environment)
    greedy_actions = full_information_greedy_actions(environment)

    assert random_actions["buyer"][1] >= 0 and random_actions["seller"][1] <= 0
    assert fallback_actions["buyer"][0] < fallback_actions["seller"][0]
    assert greedy_actions["buyer"][0] > greedy_actions["seller"][0]
    environment.step(greedy_actions)


def test_baseline_runner_emits_seed_level_raw_record() -> None:
    record = run_baseline_episode(_environment(), full_information_greedy_actions, seed=3)

    assert record["seed"] == 3
    assert record["steps"] == 1
    assert record["episode_return"] == record["total_reward"]
    assert "mean_agent_reward" in record


def test_random_baseline_uses_the_declared_episode_seed_by_default() -> None:
    first_environment = _environment()
    second_environment = _environment()
    changed_environment = _environment()
    first_environment.reset(seed=7)
    second_environment.reset(seed=7)
    changed_environment.reset(seed=8)
    first = random_valid_actions(first_environment)
    second = random_valid_actions(second_environment)
    changed_seed = random_valid_actions(changed_environment)

    assert all(np.array_equal(first[agent_id], second[agent_id])
               for agent_id in first_environment.agent_order)
    assert any(not np.array_equal(first[agent_id], changed_seed[agent_id])
               for agent_id in first_environment.agent_order)


def test_declared_test_phase_uses_only_declared_scenario_and_seeds(tmp_path) -> None:
    split = ScenarioSplit(("train",), ("validation",), ("test",), (1,), (2,), (3, 4))
    records = EpisodeRecordStore(tmp_path)
    records.create()
    requested_scenarios = []

    def environment_factory(scenario_id: str) -> LocalEnergyMarket:
        requested_scenarios.append(scenario_id)
        return _environment()

    completed = run_declared_episodes(environment_factory, full_information_greedy_actions,
                                      split, "test", "test", records)

    assert requested_scenarios == ["test", "test"]
    assert [record["seed"] for record in completed] == [3, 4]
    assert [record["phase"] for record in records.records()] == ["test", "test"]


def test_reproducibility_smoke_writes_a_verified_three_seed_raw_run(tmp_path) -> None:
    result = run_smoke(tmp_path / "smoke")

    assert result["manifest_verified"]
    assert result["scenario_split_sha256"] == SMOKE_SPLIT.fingerprint()
    assert [record["seed"] for record in result["records"]] == [301, 302, 303]
    assert result["episode_return_summary"]["count"] == 3
    assert RLTrainer.verify_run_manifest(result["manifest"])
