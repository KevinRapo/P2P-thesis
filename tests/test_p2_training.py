"""Focused configuration tests for the training runner (P2-05)."""

import hashlib
import json
import os
from pathlib import Path

import pytest

import src.environment.train as train_module
from src.environment.base import RLAlgorithm, TrainingMode
from src.environment.train import (CSVLoggerCallback, EpisodeRecordCallback, GroupedLEM,
                                   JsonLoggerCallback, RLTrainer)
from ray.rllib.algorithms.ppo import PPOConfig
from src.environment.lem import LocalEnergyMarket
from src.environment.baselines import full_information_greedy_actions
from src.environment.io import EnvConfigHandler
from src.agent.battery import Battery
from src.agent.der import DERAgent
from src.profile.der import DERProfileHandler
from src.profile.dso import DSOProfileHandler
from src.grid.network import GridNetwork
from src.grid.base import GridTopology
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig
from src.environment.experiment import ScenarioSplit, run_declared_training
from src.environment.experiment import EpisodeRecordStore


def _trainer(tune_samples: int) -> RLTrainer:
    trainer = object.__new__(RLTrainer)
    trainer.tune_samples = tune_samples
    trainer.checkpoint_freq = 1
    trainer.algorithm = RLAlgorithm.PPO
    trainer.training = TrainingMode.DTDE
    return trainer


def test_single_trial_uses_no_population_scheduler() -> None:
    assert _trainer(1)._get_tune_scheduler({"lr": object()}) is None


def test_windows_training_disables_unavailable_libuv_before_ray_workers_start() -> None:
    if os.name == "nt":
        assert os.environ["USE_LIBUV"] == "0"


def test_ray_workers_receive_the_repository_source_path() -> None:
    worker_pythonpath = RLTrainer._ray_runtime_env()["env_vars"]["PYTHONPATH"]

    assert str(Path(__file__).resolve().parents[1]) in worker_pythonpath.split(os.pathsep)


def test_training_uses_portable_machine_readable_tune_loggers() -> None:
    assert os.environ["TUNE_DISABLE_AUTO_CALLBACK_LOGGERS"] == "1"
    assert isinstance(CSVLoggerCallback(), CSVLoggerCallback)
    assert isinstance(JsonLoggerCallback(), JsonLoggerCallback)


def test_population_trials_use_population_scheduler() -> None:
    assert _trainer(2)._get_tune_scheduler({"lr": [0.001, 0.01]}) is not None


def test_evaluation_duration_accepts_positive_integer_and_rejects_boolean() -> None:
    trainer = object.__new__(RLTrainer)
    trainer.algorithm = RLAlgorithm.PPO
    trainer.training = TrainingMode.DTDE
    trainer.cpus = 1
    trainer.gpus = 0
    trainer.iters = 1
    trainer.tune_samples = 1
    trainer.checkpoint_freq = 1
    trainer.evaluation_interval = None
    trainer.evaluation_duration = 1
    trainer.storage_path = None
    trainer.env_config = {"max_steps": 2, "market_config": object(), "agents": [object()]}
    trainer._check_init()

    import pytest
    trainer.evaluation_duration = True
    with pytest.raises(ValueError, match="evaluation_duration"):
        trainer._check_init()


def test_held_out_evaluation_requests_complete_episodes_from_rllib() -> None:
    trainer = object.__new__(RLTrainer)
    trainer.cpus = 1
    trainer.gpus = 0
    trainer.evaluation_interval = 1
    trainer.evaluation_duration = 2
    trainer.evaluation_env_config = {"scenario_id": "validation", "seed": 12}

    configured = trainer._setup_extra_config(PPOConfig())

    assert configured.evaluation_duration_unit == "episodes"
    assert configured.evaluation_num_env_runners == 0
    assert not configured.evaluation_parallel_to_training


def test_windows_gpu_uses_a_single_local_rllib_learner() -> None:
    trainer = object.__new__(RLTrainer)
    trainer.cpus = 1
    trainer.gpus = 1
    trainer.evaluation_interval = None

    configured = trainer._setup_extra_config(PPOConfig())

    assert configured.num_gpus_per_learner == 1
    assert configured.num_learners == (0 if os.name == "nt" else 1)


def test_train_batch_size_requires_a_positive_integer_when_configured() -> None:
    trainer = object.__new__(RLTrainer)
    trainer.algorithm = RLAlgorithm.PPO
    trainer.training = TrainingMode.DTDE
    trainer.cpus = 1
    trainer.gpus = 0
    trainer.iters = 1
    trainer.tune_samples = 1
    trainer.checkpoint_freq = 1
    trainer.evaluation_interval = None
    trainer.evaluation_duration = "auto"
    trainer.storage_path = None
    trainer.env_config = {"max_steps": 2, "market_config": object(), "agents": [object()]}
    trainer.train_batch_size = 8
    trainer._check_init()

    import pytest
    trainer.train_batch_size = True
    with pytest.raises(ValueError, match="train_batch_size"):
        trainer._check_init()

    trainer.train_batch_size = 1
    with pytest.raises(ValueError, match="complete environment episode"):
        trainer._check_init()


def test_relative_storage_paths_are_normalized_for_ray(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    grid = GridNetwork(GridTopology.LINE, num_nodes=2, capacity=10.0, seed=1)
    trainer = RLTrainer(
        env_config={
            "max_steps": 1,
            "market_config": MarketConfig(min_price=0.0, max_price=10.0, max_quantity=10.0),
            "grid_network": grid,
            "dso": DSOAgent("DSO", [1.0], [2.0], grid),
            "agents": [
                DERAgent("buyer", 10.0, generation_profile=[0.0], demand_profile=[2.0]),
                DERAgent("seller", 10.0, generation_profile=[2.0], demand_profile=[0.0]),
            ],
        },
        algorithm=RLAlgorithm.PPO,
        training=TrainingMode.DTDE,
        iters=1,
        checkpoint_freq=1,
        cpus=1,
        gpus=0,
        train_batch_size=1,
        storage_path="results",
    )

    assert Path(trainer.storage_path).is_absolute()


def test_train_shuts_down_ray_when_tuner_setup_fails(tmp_path, monkeypatch) -> None:
    trainer = object.__new__(RLTrainer)
    trainer.algorithm = RLAlgorithm.PPO
    trainer.training = TrainingMode.DTDE
    trainer.iters = 1
    trainer.tune_samples = 1
    trainer.checkpoint_freq = 1
    trainer.evaluation_interval = None
    trainer.evaluation_env_config = None
    trainer.scenario_split = None
    trainer.env_config = {}
    trainer.storage_path = str(tmp_path)

    class _Config:
        algo_class = object

        def callbacks(self, **_kwargs):
            return self

        def environment(self, **_kwargs):
            return self

    class _Ray:
        initialized = False
        shutdown_calls = 0

        @classmethod
        def is_initialized(cls):
            return cls.initialized

        @classmethod
        def init(cls, **_kwargs):
            cls.initialized = True

        @classmethod
        def shutdown(cls):
            cls.initialized = False
            cls.shutdown_calls += 1

    monkeypatch.setattr(trainer, "_setup_config", lambda _embeddings: (_Config(), {}))
    monkeypatch.setattr(trainer, "_experiment_name", lambda: "setup-failure")
    monkeypatch.setattr(RLTrainer, "write_run_manifest", staticmethod(lambda *_args: tmp_path / "manifest"))
    monkeypatch.setattr(train_module, "ray", _Ray)
    monkeypatch.setattr(train_module, "Tuner", lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("setup failed")))

    with pytest.raises(RuntimeError, match="setup failed"):
        trainer.train()

    assert _Ray.shutdown_calls == 1
    assert not _Ray.initialized


def test_run_names_include_subsecond_uniqueness() -> None:
    trainer = _trainer(1)
    assert trainer._experiment_name() != trainer._experiment_name()


def test_grouped_reward_reports_total_and_agent_normalized_value() -> None:
    assert GroupedLEM._aggregate_group_reward({"a": 2.0, "b": 4.0}) == (6.0, 3.0)


def test_run_manifest_is_written_before_training(tmp_path) -> None:
    split = ScenarioSplit(("train",), ("validation",), ("test",), (1,), (2,), (3,))
    path = RLTrainer.write_run_manifest(
        {"seed": 7}, tmp_path / "run",
        {"algorithm": "ppo", "scenario_split": split.as_dict(),
         "scenario_split_sha256": split.fingerprint()},
    )

    manifest = json.loads(path.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    assert manifest["environment"]["seed"] == 7
    assert manifest["unit_contract"]["energy"] == "kWh"
    assert manifest["repository"]["environment_sha256"]
    assert manifest["repository"]["metric_contract_sha256"]
    assert manifest["metadata"]["scenario_split_sha256"] == split.fingerprint()
    manifest_fingerprint = manifest.pop("manifest_sha256")
    assert manifest_fingerprint == hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    assert RLTrainer.verify_run_manifest(path)

    tampered = json.loads(path.read_text(encoding="utf-8"))
    tampered["metadata"]["algorithm"] = "tampered"
    path.write_text(json.dumps(tampered), encoding="utf-8")
    assert not RLTrainer.verify_run_manifest(path)
    assert (tmp_path / "run" / "episode_records.jsonl").exists()


def test_environment_profiles_round_trip_without_default_rounding(tmp_path) -> None:
    config = {"agents": [DERAgent("a", 1.0, generation_profile=[0.123456789], demand_profile=[0.987654321])]}
    EnvConfigHandler.save(config, str(tmp_path), "scenario")
    restored = EnvConfigHandler.load(str(tmp_path / "scenario.json"))

    assert restored["agents"][0].generation_profile == [0.123456789]
    assert restored["agents"][0].demand_profile == [0.987654321]


def test_round_trip_retains_replay_sources_and_battery_limits(tmp_path) -> None:
    generation = tmp_path / "generation.csv"
    demand = tmp_path / "demand.csv"
    feed_in = tmp_path / "feed_in.csv"
    utility = tmp_path / "utility.csv"
    for path, column in ((generation, "solar"), (demand, "load"),
                         (feed_in, "fit"), (utility, "retail")):
        path.write_text(f"{column}\n1.0\n", encoding="utf-8")

    config = {
        "agents": [DERAgent("a", 1.0, Battery(2.0, max_charge_power=0.5,
                                                 max_discharge_power=0.4,
                                                 time_step_hours=0.25,
                                                 initial_soc=0.3),
                            generation_profile=[0.0], demand_profile=[0.0])],
        "der_profile_handler": DERProfileHandler(0.0, 2.0, str(generation), str(demand),
                                                  "solar", "load", seed=3),
        "dso_profile_handler": DSOProfileHandler(0.0, 2.0, str(feed_in), str(utility),
                                                  "fit", "retail", seed=4),
    }
    EnvConfigHandler.save(config, str(tmp_path), "replay")
    restored = EnvConfigHandler.load(str(tmp_path / "replay.json"))

    battery = restored["agents"][0].battery
    assert (battery.max_charge_power, battery.max_discharge_power,
            battery.time_step_hours, battery.initial_soc) == (0.5, 0.4, 0.25, 0.3)
    assert restored["der_profile_handler"].generation_column == "solar"
    assert restored["dso_profile_handler"].utility_price_column == "retail"


def test_dso_restoration_does_not_depend_on_json_key_order(tmp_path) -> None:
    grid = GridNetwork(num_nodes=2, capacity=3.0, seed=5)
    dso = DSOAgent(feed_in_tariff=[0.1], utility_price=[0.2], grid_network=grid,
                   max_buy_quantity=1.0, max_sell_quantity=2.0)
    EnvConfigHandler.save({"dso": dso, "grid_network": grid}, str(tmp_path), "ordered")
    restored = EnvConfigHandler.load(str(tmp_path / "ordered.json"))

    assert restored["dso"].grid_network is restored["grid_network"]
    assert (restored["dso"].max_buy_quantity, restored["dso"].max_sell_quantity) == (1.0, 2.0)


def test_complete_scenario_round_trip_reproduces_the_next_seeded_transition(tmp_path) -> None:
    grid = GridNetwork(GridTopology.LINE, num_nodes=2, capacity=10.0, seed=5)
    config = {
        "max_steps": 1, "seed": 5,
        "market_config": MarketConfig(max_price=10.0, max_quantity=10.0),
        "grid_network": grid,
        "dso": DSOAgent("DSO", [1.0], [2.0], grid),
        "agents": [DERAgent("buyer", 10.0, generation_profile=[0.0], demand_profile=[2.0]),
                   DERAgent("seller", 10.0, generation_profile=[2.0], demand_profile=[0.0])],
    }
    EnvConfigHandler.save(config, str(tmp_path), "scenario")
    restored_config = EnvConfigHandler.load(str(tmp_path / "scenario.json"))
    original = LocalEnergyMarket(config)
    restored = LocalEnergyMarket(restored_config)

    original.reset(seed=17)
    restored.reset(seed=17)
    original_step = original.step(full_information_greedy_actions(original))
    restored_step = restored.step(full_information_greedy_actions(restored))

    assert original_step[1] == restored_step[1]
    for agent_id in original.agent_order:
        original_info = original_step[4][agent_id]
        restored_info = restored_step[4][agent_id]
        for key in ("current_step", "time_of_day", "grid_balance", "market_price",
                    "market_volume", "kpis", "dso_stats"):
            assert original_info[key] == restored_info[key]


def test_held_out_evaluation_requires_a_distinct_declared_seed() -> None:
    trainer = object.__new__(RLTrainer)
    trainer.env_config = {"seed": 11, "scenario_id": "day-a"}
    trainer.evaluation_env_config = {"seed": 12, "scenario_id": "day-b"}
    trainer.scenario_split = ScenarioSplit(("day-a",), ("day-b",), ("day-c",), (11,), (12,), (13,))
    trainer._validate_evaluation_protocol()

    import pytest
    trainer.evaluation_env_config = {"seed": 11}
    with pytest.raises(ValueError, match="distinct"):
        trainer._validate_evaluation_protocol()

    trainer.evaluation_env_config = {"seed": 12, "scenario_id": "day-b"}
    trainer.env_config = {"seed": 99, "scenario_id": "day-a"}
    with pytest.raises(ValueError, match="Training seed"):
        trainer._validate_evaluation_protocol()


def test_scenario_split_rejects_profile_or_seed_overlap() -> None:
    import pytest

    with pytest.raises(ValueError, match="scenario IDs"):
        ScenarioSplit(("a",), ("a",), ("c",), (1,), (2,), (3,))
    with pytest.raises(ValueError, match="seed lists"):
        ScenarioSplit(("a",), ("b",), ("c",), (1,), (1,), (3,))
    with pytest.raises(ValueError, match="duplicates"):
        ScenarioSplit(("a", "a"), ("b",), ("c",), (1,), (2,), (3,))
    with pytest.raises(ValueError, match="duplicates"):
        ScenarioSplit(("a",), ("b",), ("c",), (1, 1), (2,), (3,))

    split = ScenarioSplit(("a",), ("b",), ("c",), (1,), (2,), (3,))
    assert split.fingerprint() == split.fingerprint()


def test_declared_training_runs_each_declared_seed_once() -> None:
    split = ScenarioSplit(("train-a",), ("validation-a",), ("test-a",),
                          (3, 5, 7), (11,), (13,))
    calls = []

    class _Trainer:
        def __init__(self, seed):
            self.seed = seed

        def train(self):
            return f"result-{self.seed}", {"seed": self.seed}

    def factory(scenario_id, seed):
        calls.append((scenario_id, seed))
        return _Trainer(seed)

    completed = run_declared_training(factory, split, "train-a")

    assert calls == [("train-a", 3), ("train-a", 5), ("train-a", 7)]
    assert [item["metrics"] for item in completed] == [{"seed": 3}, {"seed": 5}, {"seed": 7}]


def test_episode_records_are_append_only_and_report_distribution_summary(tmp_path) -> None:
    store = EpisodeRecordStore(tmp_path)
    store.create()
    store.append({"seed": 1, "episode_return": 2.0})
    store.append({"seed": 2, "episode_return": 4.0})

    assert list(store.records()) == [{"episode_return": 2.0, "seed": 1},
                                     {"episode_return": 4.0, "seed": 2}]
    assert EpisodeRecordStore.summarize(store.records(), "episode_return")["mean"] == 3.0


def test_checkpoint_selection_does_not_name_validation_without_held_out_config() -> None:
    trainer = object.__new__(RLTrainer)
    trainer.evaluation_interval = None
    assert trainer._selection_metric().endswith("episode_return_mean")
    assert "evaluation" not in trainer._selection_metric()

    trainer.evaluation_interval = 1
    assert trainer._selection_metric().startswith("evaluation/")


def test_manifest_hashes_each_configured_profile_source(tmp_path) -> None:
    source = tmp_path / "profile.csv"
    source.write_text("value\n1.0\n", encoding="utf-8")

    hashes = RLTrainer._profile_source_hashes({
        "der_profile_handler": {"generation_file_path": str(source)},
        "dso_profile_handler": None,
    })

    assert hashes[str(source)]


def test_episode_callback_logs_completed_returns_and_lengths() -> None:
    logged = []

    class _MetricsLogger:
        def log_value(self, *args, **kwargs):
            logged.append((args, kwargs))

    class _Episode:
        def get_return(self):
            return 3.5

        def env_steps(self):
            return 2

    EpisodeRecordCallback().on_episode_end(episode=_Episode(), metrics_logger=_MetricsLogger())

    assert logged[0][0] == ("raw_episode_returns", 3.5)
    assert logged[1][0] == ("raw_episode_lengths", 2)
    assert all(entry[1]["reduce"] is None for entry in logged)


def test_episode_callback_appends_driver_side_training_records(tmp_path) -> None:
    store = EpisodeRecordStore(tmp_path)
    store.create()

    class _Algorithm:
        class config:
            env_config = {"_episode_record_path": str(store.path),
                          "scenario_id": "train-a", "seed": 7}

    EpisodeRecordCallback().on_train_result(
        algorithm=_Algorithm(),
        result={"training_iteration": 2,
                "env_runners": {"raw_episode_returns": [1.5, 2.5],
                                "raw_episode_lengths": [3, 4]}},
    )

    assert list(store.records()) == [
        {"episode_return": 1.5, "phase": "train", "record_type": "training_episode",
         "scenario_id": "train-a", "seed": 7, "steps": 3, "training_iteration": 2},
        {"episode_return": 2.5, "phase": "train", "record_type": "training_episode",
         "scenario_id": "train-a", "seed": 7, "steps": 4, "training_iteration": 2},
    ]
