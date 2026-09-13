"""Regression tests for the paper-aligned experiment protocol."""

import numpy as np

from src.environment.lem import LocalEnergyMarket
from src.environment.base import RLAlgorithm, TrainingMode
from src.environment.train import GroupedLEM, RLTrainer, extract_run_metrics
from src.market.matching import MarketConfig
from src.market.validation import Validator
from src.scenario import CASE6_PARTICIPANTS, build_case6_config, build_case6_evaluation_config


def test_case6_scenario_matches_paper_table_and_has_heterogeneous_profiles():
    config = build_case6_config(seed=42, max_steps=24)
    agents = config["agents"]
    assert [(a.id, a.capacity, a.battery.nominal_capacity, a.node_id) for a in agents] == list(CASE6_PARTICIPANTS)
    assert all(a.battery.min_soc == 0.05 and a.battery.max_soc == 0.95 for a in agents)
    assert len({tuple(a.generation_profile) for a in agents}) == 8
    assert len({tuple(a.demand_profile) for a in agents}) == 8
    assert config["market_config"].price_mechanism.value == "average"
    assert config["grid_network"].topology.value == "IEEE34"
    assert config["grid_network"].capacity == 1800.0
    assert {a.id: a.location.node_id for a in agents} == config["paper_node_mapping"]
    assert all(max(a.generation_profile) <= a.capacity + 1e-8 for a in agents)
    assert all(max(a.demand_profile) <= a.capacity + 1e-8 for a in agents)


def test_forecast_error_is_seeded_bounded_and_does_not_change_physical_profiles():
    config = build_case6_config(seed=42, max_steps=24)
    env = LocalEnergyMarket(config)
    env.reset(seed=123)
    physical = {a.id: (list(a.generation_profile), list(a.demand_profile)) for a in env._agents.values()}
    first_forecasts = {a.id: (list(a.forecast_generation_profile), list(a.forecast_demand_profile)) for a in env._agents.values()}
    for agent in env._agents.values():
        for actual, forecast in zip(agent.generation_profile, agent.forecast_generation_profile):
            if actual:
                assert abs(forecast / actual - 1.0) <= config["max_error"] + 1e-12
        for actual, forecast in zip(agent.demand_profile, agent.forecast_demand_profile):
            if actual:
                assert abs(forecast / actual - 1.0) <= config["max_error"] + 1e-12
    env.reset()
    second_forecasts = {a.id: (list(a.forecast_generation_profile), list(a.forecast_demand_profile)) for a in env._agents.values()}
    assert first_forecasts != second_forecasts
    assert physical == {a.id: (list(a.generation_profile), list(a.demand_profile)) for a in env._agents.values()}
    env.reset(seed=123)
    assert first_forecasts == {a.id: (list(a.forecast_generation_profile), list(a.forecast_demand_profile)) for a in env._agents.values()}
    assert not np.allclose(first_forecasts["hospital"][1], physical["hospital"][1])


def test_group_reward_reports_total_and_per_agent_mean():
    total, mean = GroupedLEM._aggregate_group_reward({"a": 2.0, "b": 6.0})
    assert total == 8.0
    assert mean == 4.0


def test_case6_observations_remain_inside_declared_spaces_for_full_episode():
    env = LocalEnergyMarket(build_case6_config(seed=42, max_steps=24))
    for episode_seed in (42, 43, 44):
        observations, _ = env.reset(seed=episode_seed)
        for index, agent_id in enumerate(env.agents):
            env.action_spaces[agent_id].seed(episode_seed + index)
        assert all(env.observation_spaces[agent_id].contains(observation)
                   for agent_id, observation in observations.items())
        for _ in range(24):
            actions = {agent_id: env.action_spaces[agent_id].sample()
                       for agent_id in env.agents}
            observations, _, terminated, truncated, _ = env.step(actions)
            violations = {}
            for agent_id, observation in observations.items():
                space = env.observation_spaces[agent_id]
                bad = np.flatnonzero((observation < space.low) | (observation > space.high))
                if len(bad):
                    violations[agent_id] = [
                        (int(i), float(observation[i]), float(space.low[i]), float(space.high[i]))
                        for i in bad
                    ]
            assert not violations, violations
            if terminated["__all__"] or truncated["__all__"]:
                break


def test_run_metrics_fallback_normalizes_dtde_and_reports_overshoot():
    report = extract_run_metrics({
        "episode_return_mean": 80.0,
        "num_env_steps_sampled_lifetime": 224,
        "num_episodes_lifetime": 9,
        "num_training_step_calls_per_iteration": 3,
    }, num_agents=8, decentralized=True, target_env_steps=192)
    assert report["comparison_reward"] == 10.0
    assert report["sampled_env_steps"] == 224
    assert report["sampled_episodes"] == 9
    assert report["learner_updates"] == 3
    assert report["env_step_overshoot"] == 32
    assert report["budget_reached"] is True


def test_run_metrics_reads_nested_env_runner_counters_and_missing_eval_is_safe():
    report = extract_run_metrics({
        "env_runners": {
            "episode_return_mean": 5.0,
            "num_env_steps_sampled_lifetime": 96,
            "num_episodes_lifetime": 4,
        }
    }, num_agents=2, decentralized=True, target_env_steps=192)
    assert report["comparison_reward"] == 2.5
    assert report["sampled_env_steps"] == 96
    assert report["comparison_eval_reward"] is None
    assert report["env_step_overshoot"] == 0
    assert report["budget_reached"] is False

    flat_eval = extract_run_metrics({
        "episode_return_mean": 4.0,
        "evaluation": {"episode_return_mean": 12.0},
    }, num_agents=2, decentralized=True)
    assert flat_eval["comparison_eval_reward"] == 6.0


def test_run_metrics_does_not_confuse_learner_steps_with_update_calls():
    report = extract_run_metrics({
        "learners": {
            "__all_modules__": {"num_env_steps_trained_lifetime": 10250}
        }
    })
    assert report["learner_updates"] is None
    assert report["learner_train_steps"] == 10250


def test_all_algorithms_use_complete_episode_batches_with_step_budget():
    config = build_case6_config(seed=42, max_steps=24)
    for algorithm in RLAlgorithm:
        trainer = RLTrainer(
            config,
            algorithm=algorithm,
            training=TrainingMode.CTCE,
            iters=2,
            env_steps=192,
            train_batch_size=192,
            cpus=1,
            gpus=0,
        )
        algorithm_config, _ = trainer._setup_config()
        values = algorithm_config.to_dict()
        assert values["batch_mode"] == "complete_episodes"
        assert trainer.env_steps == 192


def test_eval_config_is_independent_and_manifest_serializes_effective_eval():
    train = build_case6_config(seed=42, max_steps=24)
    evaluation = build_case6_evaluation_config(seed=10042, max_steps=24)
    assert train["seed"] != evaluation["seed"]
    trainer = RLTrainer(train, iters=1, evaluation_env_config=evaluation, evaluation_interval=1, cpus=1, gpus=0)
    assert trainer.evaluation_env_config["seed"] == 10042
    assert trainer.evaluation_env_config is not trainer.env_config


def test_best_result_selection_falls_back_when_evaluation_metric_is_missing():
    class Result:
        def __init__(self, checkpoint):
            self.checkpoint = checkpoint

    class ResultsWithoutEvaluation:
        def get_best_result(self, metric=None, mode=None):
            if metric and metric.startswith("evaluation/"):
                raise RuntimeError("evaluation metric was never emitted")
            return Result("train-checkpoint")

    trainer = RLTrainer(build_case6_config(), iters=1, evaluation_interval=1, cpus=1, gpus=0)
    results = ResultsWithoutEvaluation()
    train, evaluation = trainer.get_best_results(results)
    assert train.checkpoint == "train-checkpoint"
    assert evaluation is None
    assert trainer.get_best_checkpoint(results) == {
        "train": "train-checkpoint", "eval": None}


def test_validator_zero_difficulty_keeps_chain_integrity_without_pow():
    validator = Validator(difficulty=0, block_size=1)
    assert validator.difficulty == 0
    assert validator.verify_chain()
