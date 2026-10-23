"""The runner (``core/runner/``): experiment files, expansion, and the registry.

Fast checks without training: specs are expanded and validated, and the registry
reads hand-written status files in a temporary ``runs/``.

Run with ``python -m pytest tests/runner -q`` in the ``marlem`` conda env.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import pytest

from core.runner import registry
from core.runner.spec import (
    ALGORITHMS,
    PARADIGMS,
    REPO,
    SCENARIO_FILE,
    Experiment,
    SpecError,
    resolve,
    to_text,
    written_out,
)

SCENARIO = "config/scenarios/validate_market.json"


def spec(**changes) -> dict:
    base = {
        "scenario": SCENARIO,
        "train_days": {"from": "2016-06-01", "to": "2016-06-03"},
        "test_days": ["2016-07-01", "2016-07-02"],
        "algorithms": ["ppo"],
        "paradigms": ["dtde", "ctde"],
        "seeds": [0, 1],
        "budget": {"ppo": 2000},
        "eval_points": 4,
    }
    return base | changes


# --------------------------------------------------------------------------------------
# Experiment files
# --------------------------------------------------------------------------------------
def test_names_in_the_order_of_the_grid():
    runs = Experiment.from_dict(spec(), "x").expand(Path("out"))
    assert len(runs) == 1 * 2 * 2
    assert runs[0].name == "ppo_dtde_s0"
    assert [r.name for r in runs[:4]] == [
        "ppo_dtde_s0",
        "ppo_dtde_s1",
        "ppo_ctde_s0",
        "ppo_ctde_s1",
    ]
    assert [r.index for r in runs] == list(range(4))
    assert runs[0].out_dir == Path("out") / "ppo_dtde_s0"


def test_default_name_is_the_file_stem(tmp_path):
    path = tmp_path / "my_experiment.json"
    path.write_text(json.dumps(spec()), encoding="utf-8")
    assert Experiment.load(path).name == "my_experiment"


@pytest.mark.parametrize("settings, expected", [({}, 0), ({"num_env_runners": 3}, 3)])
def test_env_runners_reach_training_in_both_profiles(settings, expected, monkeypatch):
    monkeypatch.setattr("core.runner.spec.load_env_class", lambda name: object)
    experiment = Experiment.from_dict(spec(**settings), "x")
    restored = Experiment.from_dict(experiment.to_dict())

    for profile in ("full", "test"):
        for run_spec in restored.with_profile(profile).expand():
            assert run_spec.run().num_env_runners == expected


@pytest.mark.parametrize("value", [-1, 1.5, True, "3"])
def test_env_runners_must_be_a_nonnegative_integer(value):
    with pytest.raises(SpecError, match="num_env_runners must be an integer >= 0"):
        Experiment.from_dict(spec(num_env_runners=value), "x")


def test_budget_and_eval_every_per_algorithm():
    runs = {r.algorithm: r for r in Experiment.from_dict(spec(), "x").expand()}
    assert (runs["ppo"].budget, runs["ppo"].eval_every) == (2000, 500)
    data = spec(eval_points=None, eval_every={"ppo": 700})
    runs = {r.algorithm: r for r in Experiment.from_dict(data, "x").expand()}
    assert runs["ppo"].eval_every == 700
    data = spec(eval_points=None, budget=900, eval_every=300)
    runs = Experiment.from_dict(data, "x").expand()
    assert {(r.budget, r.eval_every) for r in runs} == {(900, 300)}


def test_variants_merge_over_the_algorithm_settings():
    data = spec(
        paradigms=["dtde"],
        seeds=[3],
        variants={"e1": {"entropy_coeff": 0.1}, "lr1": {"lr": 0.1}},
        training={"ppo": {"lr": 0.0003, "entropy_coeff": 0.01}},
    )
    runs = Experiment.from_dict(data, "x").expand()
    assert [r.name for r in runs] == ["ppo_dtde_s3_e1", "ppo_dtde_s3_lr1"]
    assert runs[0].training == {"lr": 0.0003, "entropy_coeff": 0.1}
    assert runs[1].training == {"lr": 0.1, "entropy_coeff": 0.01}


def test_env_config_and_date_ranges():
    data = spec(env_config={"energy_scale": 7.0})
    experiment = Experiment.from_dict(data, "x")
    run = experiment.expand()[1]  # seed 1
    assert run.env_config == {
        "scenario": str((REPO / SCENARIO).resolve()),
        "days": ["2016-06-01", "2016-06-02", "2016-06-03"],
        "seed": 1,
        "energy_scale": 7.0,
    }
    assert experiment.test_days == ["2016-07-01", "2016-07-02"]
    assert experiment.heldout_config()["days"] == ["2016-07-01", "2016-07-02"]


def test_a_variants_env_config_reaches_its_runs_and_held_out_evaluation():
    graph = {"grid": {"method": "graph"}}
    data = spec(
        paradigms=["dtde"],
        seeds=[0],
        variants={"ac": {}, "graph": {"env_config": graph, "lr": 0.1}},
        env_config={"energy_scale": 7.0},
    )
    experiment = Experiment.from_dict(data, "x")
    ac, gr = experiment.expand()
    assert "grid" not in ac.env_config
    assert gr.env_config["grid"] == graph["grid"]
    assert gr.env_config["energy_scale"] == 7.0
    assert "env_config" not in gr.training and gr.training["lr"] == 0.1
    assert "grid" not in experiment.heldout_config(variant="ac")
    assert experiment.heldout_config(variant="graph")["grid"] == graph["grid"]


def test_a_variants_env_config_must_be_a_dict():
    data = spec(variants={"graph": {"env_config": ["grid"]}})
    with pytest.raises(SpecError, match="env_config"):
        Experiment.from_dict(data, "x")


def test_resolve_reads_the_scenario_into_the_experiment(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps(spec()), encoding="utf-8")
    scenario = json.loads((REPO / SCENARIO).read_text(encoding="utf-8"))
    experiment = resolve(path)
    assert experiment.scenario == scenario and experiment.name == "x"
    assert resolve(path, "test").scenario == scenario
    assert resolve(experiment) == experiment  # already holds it
    assert resolve(Experiment.load(path)) == experiment  # an Experiment, not a file
    assert Experiment.from_dict(json.loads(json.dumps(experiment.to_dict()))) == (
        experiment
    )


def test_an_experiment_with_its_scenario_reads_the_copy_in_its_folder(tmp_path):
    experiment = Experiment.from_dict(spec(scenario={"name": "s"}), "x")
    run = experiment.expand(tmp_path / "x")[0]
    assert run.env_config["scenario"] == str(tmp_path / "x" / SCENARIO_FILE)
    held_out = experiment.heldout_config(tmp_path / "x")
    assert held_out["scenario"] == str(tmp_path / "x" / SCENARIO_FILE)


@pytest.mark.parametrize(
    "content, message",
    [("{half", "not valid JSON"), ("[1]", "holds one JSON object")],
)
def test_resolve_refuses_a_scenario_file_that_is_no_scenario(
    tmp_path, content, message
):
    scenario = tmp_path / "s.json"
    scenario.write_text(content, encoding="utf-8")
    experiment = Experiment.from_dict(spec(scenario=str(scenario)), "x")

    with pytest.raises(SpecError, match=message):
        resolve(experiment)

    scenario.unlink()

    with pytest.raises(SpecError, match="scenario file not found"):
        resolve(experiment)

    with pytest.raises(SpecError, match="'scenario' is a file"):
        Experiment.from_dict(spec(scenario=[1]), "x")


def test_dated_adds_the_date_and_time_to_the_name():
    experiment = Experiment.from_dict(spec(), "x")
    dated = experiment.dated(datetime(2026, 10, 18, 14, 32, 5))
    assert dated.name == "x-20261018-143205"
    assert dated.test_version().name == "x-20261018-143205--test"
    assert experiment.name == "x" and dated.budget == experiment.budget


def test_the_heldout_evaluation_plays_every_test_day_once():
    experiment = Experiment.from_dict(spec(), "x")
    assert experiment.heldout_episodes() == [
        (2000, "2016-07-01"),
        (2001, "2016-07-02"),
    ]
    for gone in (spec(heldout_seeds=3), spec(test={"heldout_seeds": 1})):
        with pytest.raises(SpecError, match="'heldout_seeds' is gone"):
            Experiment.from_dict(gone, "x")


def test_traced_days_only_with_detailed_results():
    days = {"from": "2016-07-01", "to": "2016-07-05"}
    assert Experiment.from_dict(spec(test_days=days), "x").traced_days() == []
    detailed = Experiment.from_dict(
        spec(test_days=days, results_detail="detailed"), "x"
    )
    assert detailed.traced_days() == ["2016-07-01", "2016-07-02", "2016-07-03"]
    chosen = spec(
        test_days=days,
        results_detail="detailed",
        trace_days=["2016-07-04", "2016-07-02"],
    )
    assert Experiment.from_dict(chosen, "x").traced_days() == [
        "2016-07-02",  # in the order of the test days
        "2016-07-04",
    ]
    version = Experiment.from_dict(chosen, "x").test_version()
    assert version.test_days == ["2016-07-01"] and version.trace_days == 1
    assert version.traced_days() == ["2016-07-01"]  # its one day instead

    for bad, message in (
        ({"results_detail": "all"}, "results_detail"),
        ({"trace_days": 0}, "trace_days"),
        ({"trace_days": ["2016-08-01"]}, "not test days"),
    ):
        with pytest.raises(SpecError, match=message):
            Experiment.from_dict(spec(**bad), "x")


def test_out_dir_defaults_to_the_runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MARLEM_RUNS", str(tmp_path))
    assert Experiment.from_dict(spec(), "exp").expand()[0].out_dir == (
        tmp_path / "exp" / "ppo_dtde_s0"
    )


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"algorithms": ["ppo", "dqn"]}, "unknown algorithms"),
        ({"algorithms": ["sac"]}, "unknown algorithms"),
        ({"algorithms": ["appo"]}, "unknown algorithms"),
        ({"paradigms": ["ctxe"]}, "unknown paradigms"),
        ({"scenario": "config/scenarios/nope.json"}, "scenario file not found"),
        ({"scenario": None}, "needs a 'scenario'"),
        ({"budget": {"sac": 10}}, "no entry for algorithm 'ppo'"),
        ({"eval_every": 10}, "not both"),
        ({"seeds": []}, "seeds"),
        ({"seeds": [0, 0]}, "seeds"),
        ({"test_days": {"from": "2016-07-05", "to": "2016-07-01"}}, "before"),
        ({"train_days": ["2016-13-01"]}, "bad date"),
        ({"training": {"dqn": {}}}, "'training' maps"),
        ({"trainning": {}}, "unknown field"),
        ({"variants": {"a b": {}}}, "plain word"),
        ({"max_parallel": 0}, "max_parallel"),
        ({"ray_thread_caps": "yes"}, "ray_thread_caps"),
        ({"ray_thread_caps": 1}, "ray_thread_caps"),
        ({"resources": {"gpus": 1}}, "unknown 'resources' key"),
        ({"resources": {"cpus": 0}}, "'resources.cpus' must be a positive integer"),
        ({"resources": {"cpus": 1.5}}, "'resources.cpus' must be a positive integer"),
        ({"resources": {"cpus": True}}, "'resources.cpus' must be a positive integer"),
        ({"resources": {"mem_gb": 0}}, "'resources.mem_gb' must be a positive number"),
        ({"resources": {"minutes": -5}}, "'resources.minutes' must be a positive"),
        ({"resources": [4]}, "'resources' maps"),
        ({"resources": {"node": ""}}, "'resources.node' is one node's name"),
        ({"resources": {"node": "green[1-3]"}}, "'resources.node' is one node"),
        ({"resources": {"node": 1}}, "'resources.node' is one node's name"),
        ({"test": {"budgets": 1}}, "unknown 'test' key"),
        ({"test": ["seeds"]}, "'test' maps"),
        ({"test": {"train_days": 0}}, "'test.train_days' is a number of days"),
        ({"test": {"seeds": 3}}, "'test.seeds' is a list"),
        ({"test": {"seeds": [1, 1]}}, "'test' block: .*seeds"),
        (
            {"test": {"budget": {"sac": 10}}},
            "'test' block: .*no entry for algorithm 'ppo'",
        ),
        ({"test": {"resources": {"cpus": 0}}}, "'test.resources.cpus' must be"),
    ],
)
def test_validation_errors(changes, message):
    with pytest.raises(SpecError, match=message):
        Experiment.from_dict(spec(**changes), "x")


def test_missing_file_and_bad_json(tmp_path):
    with pytest.raises(SpecError, match="not found"):
        Experiment.load(tmp_path / "nope.json")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(SpecError, match="not valid JSON"):
        Experiment.load(tmp_path / "bad.json")


def test_experiments_folder_files_are_valid():
    for path in sorted((REPO / "config" / "experiments").glob("*.json")):
        assert Experiment.load(path).expand(), path


def test_axis_names_match_the_trainer():
    from core.rl.config import Algorithm, Paradigm

    assert ALGORITHMS == tuple(a.value for a in Algorithm)
    assert PARADIGMS == tuple(p.value for p in Paradigm)


def test_the_rl_defaults_are_those_the_trainer_uses():
    import dataclasses

    from ray.rllib.core.rl_module.default_model_config import DefaultModelConfig

    from core.rl.config import MODEL
    from core.rl_defaults import NETWORK

    rllib = dataclasses.asdict(DefaultModelConfig())
    assert {k: v for k, v in NETWORK.items() if k != "vf_share_layers"} == {
        k: rllib[k] for k in NETWORK if k != "vf_share_layers"
    }
    assert MODEL == rllib | {"vf_share_layers": False}


def test_written_out_shows_every_setting_and_makes_the_same_runs():
    from core.rl_defaults import NETWORK, SETTINGS

    for path in sorted((REPO / "config" / "experiments").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        full = written_out(data, path.stem)
        assert written_out(full, path.stem) == full, path  # twice: the same
        assert json.loads(to_text(full)) == full
        assert set(full) >= set(Experiment.__dataclass_fields__) - {"name"}
        before = Experiment.from_dict(data, path.stem).expand()
        after = Experiment.from_dict(full, path.stem).expand()
        assert len(before) == len(after)

        for a, b in zip(before, after):
            assert SETTINGS[a.algorithm] | a.training == b.training
            assert NETWORK | a.model == b.model
            # null in env_config: computed by the environment, as when absent
            given = [
                {k: v for k, v in run.env_config.items() if v is not None}
                for run in (a, b)
            ]
            assert given[0] == given[1]
            plain = dict(training={}, model={}, env_config={})
            assert replace(a, **plain) == replace(b, **plain)


# --------------------------------------------------------------------------------------
# Resources, writing a spec back, and the test profile
# --------------------------------------------------------------------------------------
def test_run_resources_default_and_override():
    default = {"cpus": 4, "mem_gb": 4, "minutes": 120, "node": None}
    assert Experiment.from_dict(spec(), "x").run_resources == default
    experiment = Experiment.from_dict(spec(resources={"mem_gb": 8.5}), "x")
    assert experiment.run_resources == default | {"mem_gb": 8.5}
    assert experiment.resources == {"mem_gb": 8.5}  # as written


def test_to_dict_round_trips_every_experiments_file():
    for path in sorted((REPO / "config" / "experiments").glob("*.json")):
        experiment = Experiment.load(path)
        data = json.loads(json.dumps(experiment.to_dict()))  # plain JSON
        assert Experiment.from_dict(data) == experiment, path
        assert data["name"] == experiment.name


def test_to_dict_writes_days_out_as_dates():
    experiment = Experiment.from_dict(spec(), "x")
    data = experiment.to_dict()
    assert data["train_days"] == ["2016-06-01", "2016-06-02", "2016-06-03"]
    assert data["test_days"] == ["2016-07-01", "2016-07-02"]
    data["seeds"].append(9)  # a copy: the experiment is not changed
    assert experiment.seeds == [0, 1]


def test_test_version_is_the_smallest_version():
    data = spec(
        description="Everything",
        variants={"a": {"lr": 0.1}},
        env_config={"energy_scale": 7.0},
        training={"ppo": {"train_batch_size_per_learner": 2400}},
        resources={"cpus": 8, "mem_gb": 16, "minutes": 600},
        model={"fcnet_hiddens": [8]},
    )
    experiment = Experiment.from_dict(data, "big")
    version = experiment.test_version()
    assert version.name == "big--test"
    assert version.seeds == [0]
    assert version.train_days == ["2016-06-01"]
    assert version.test_days == ["2016-07-01"]
    assert version.budget == {"ppo": 2400}  # one batch
    assert (version.eval_every, version.eval_points) == (None, None)
    assert version.eval_episodes == 1
    assert version.heldout_episodes() == [(2000, "2016-07-01")]
    assert version.run_resources == {
        "cpus": 8,
        "mem_gb": 16,
        "minutes": 15,
        "node": None,
    }
    assert version.test == {}
    assert version.description == "Test version of big: Everything"

    for key in (
        "scenario",
        "env",
        "env_config",
        "algorithms",
        "paradigms",
        "training",
        "model",
        "variants",
    ):
        assert getattr(version, key) == getattr(experiment, key), key

    # the original is untouched
    assert (experiment.name, experiment.seeds) == ("big", [0, 1])
    assert experiment.budget == {"ppo": 2000}
    runs = version.expand(Path("out"))
    assert len(runs) == 1 * 2 * 1 * 1  # algorithms x paradigms x seeds x variants
    assert {r.eval_every for r in runs} == {0}  # only the final evaluation
    assert {r.budget for r in runs if r.algorithm == "ppo"} == {2400}


def test_test_version_without_a_description_or_batch_size():
    version = Experiment.from_dict(spec(), "x").test_version()
    assert version.description == "Test version of x"
    assert version.budget == {"ppo": 100}
    assert version.run_resources["minutes"] == 15


def budgets(**changes) -> dict:
    return Experiment.from_dict(spec(**changes), "x").test_version().budget


def test_test_budget_comes_from_the_effective_settings():
    assert budgets(training={"ppo": {"lr": 1e-4}}) == {"ppo": 100}
    batch = {"ppo": {"train_batch_size_per_learner": 3000}}
    assert budgets(training=batch) == {"ppo": 3000}


def test_test_budget_is_the_largest_over_the_variants():
    variants = {
        "small": {"train_batch_size_per_learner": 200},
        "batch": {"train_batch_size_per_learner": 4000},
    }
    assert budgets(variants=variants) == {"ppo": 4000}
    only = {"v": {"train_batch_size_per_learner": 64}}
    assert budgets(variants=only) == {"ppo": 64}
    assert budgets(test={"budget": 7}) == 7  # an explicit test budget wins


def test_test_block_overrides_the_defaults():
    test = {
        "seeds": [7, 8],
        "train_days": 2,
        "test_days": 5,
        "budget": 300,
        "eval_episodes": 2,
        "resources": {"minutes": 30, "cpus": 2},
    }
    version = Experiment.from_dict(spec(test=test), "x").test_version()
    assert version.seeds == [7, 8]
    assert version.train_days == ["2016-06-01", "2016-06-02"]
    assert version.test_days == ["2016-07-01", "2016-07-02"]  # only two exist
    assert version.budget == 300
    assert version.eval_episodes == 2
    assert len(version.heldout_episodes()) == 2  # one per test day
    assert version.run_resources == {
        "cpus": 2,
        "mem_gb": 4,
        "minutes": 30,
        "node": None,
    }
    assert version.test == {}


def test_test_block_budget_per_algorithm():
    data = spec(test={"budget": {"ppo": 50}})
    version = Experiment.from_dict(data, "x").test_version()
    assert version.budget == {"ppo": 50}


def test_profiles():
    experiment = Experiment.from_dict(spec(), "x")
    assert experiment.with_profile("full") is experiment
    assert experiment.with_profile("test") == experiment.test_version()

    with pytest.raises(SpecError, match="unknown profile"):
        experiment.with_profile("tiny")


def test_experiments_folder_files_have_a_valid_test_version():
    for path in sorted((REPO / "config" / "experiments").glob("*.json")):
        experiment = Experiment.load(path)
        version = experiment.test_version()
        assert version.name == f"{experiment.name}--test", path
        assert 0 < len(version.expand()) <= len(experiment.expand()), path


# --------------------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------------------
def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def me() -> dict:
    process = psutil.Process()
    return {"pid": process.pid, "create_time": process.create_time()}


def dead_pid() -> dict:
    """A pid that existed (a process that has ended) with its old start time."""
    import subprocess
    import sys

    child = subprocess.Popen([sys.executable, "-c", "pass"])
    start = psutil.Process(child.pid).create_time()
    child.wait()

    return {"pid": child.pid, "create_time": start}


@pytest.fixture()
def root(tmp_path) -> Path:
    return tmp_path / "runs"


def test_states_from_status_files(root):
    exp = root / "exp"
    write(exp / "a_queued" / "status.json", {"state": "queued", "index": 0})
    write(exp / "b_running" / "status.json", {"state": "running", "index": 1} | me())
    write(exp / "c_lost" / "status.json", {"state": "running", "index": 2} | dead_pid())
    write(exp / "d_done" / "status.json", {"state": "completed", "index": 3})
    write(
        exp / "e_failed" / "status.json",
        {"state": "failed", "index": 4, "error": "ValueError('x')"},
    )
    write(exp / "f_stopped" / "status.json", {"state": "stopped", "index": 5})
    states = {s.name: s for s in registry.runs("exp", root)}
    assert [s.name for s in registry.runs("exp", root)][:2] == ["a_queued", "b_running"]
    assert {n[2:]: s.state for n, s in states.items()} == {
        "queued": "queued",
        "running": "running",
        "lost": "lost",
        "done": "completed",
        "failed": "failed",
        "stopped": "stopped",
    }
    assert states["e_failed"].error == "ValueError('x')"
    assert states["d_done"].progress == 1.0


def test_pid_reuse_is_lost(root):
    wrong_time = me() | {"create_time": me()["create_time"] - 1000}
    write(root / "exp" / "r" / "status.json", {"state": "running"} | wrong_time)
    assert registry.runs("exp", root)[0].state == "lost"


def test_queued_without_its_worker_is_lost(root):
    exp = root / "exp"
    write(exp / "r" / "status.json", {"state": "queued"})
    assert registry.runs("exp", root)[0].state == "queued"  # no worker.json: as is
    write(exp / "worker.json", dead_pid())
    assert registry.runs("exp", root)[0].state == "lost"
    write(exp / "worker.json", me())
    assert registry.runs("exp", root)[0].state == "queued"


def test_legacy_run_json(root):
    exp = root / "old"
    write(exp / "ok" / "run.json", {"status": "completed", "budget_env_steps": 100})
    write(exp / "bad" / "run.json", {"status": "failed", "error": "boom"})
    write(exp / "odd" / "run.json", {"status": "running"})
    states = {s.name: s for s in registry.runs("old", root)}
    assert states["ok"].state == "completed" and states["ok"].progress == 1.0
    assert states["bad"].state == "failed" and states["bad"].error == "boom"
    assert states["odd"].state == "unknown"
    assert registry.experiments(root) == ["old"]


def test_experiments_lists_folders_with_runs(root):
    write(root / "a" / "r" / "status.json", {"state": "queued"})
    write(root / "b" / "r" / "run.json", {"status": "completed"})
    (root / "empty").mkdir()
    write(root / "notes" / "readme.json", {})
    assert registry.experiments(root) == ["a", "b"]
    assert registry.experiments(root / "missing") == []


def test_progress_eta_and_scores(root):
    run = root / "exp" / "run"
    started = datetime.now() - timedelta(seconds=100)
    write(
        run / "status.json",
        {
            "state": "running",
            "budget": 1000,
            "started": started.isoformat(timespec="seconds"),
        }
        | me(),
    )
    (run / "metrics.csv").write_text(
        "iteration,env_steps,team_return_mean\n1,100,-5\n2,250,-4\n", encoding="utf-8"
    )
    (run / "evaluation.csv").write_text(
        "env_steps,policy,team_return_mean,team_return_std\n"
        "0,trained,-9.0,1\n0,zero,-3.0,0\n250,trained,-2.5,1\n",
        encoding="utf-8",
    )
    state = registry.runs("exp", root)[0]
    assert state.state == "running"
    assert state.env_steps == 250 and state.budget == 1000
    assert state.progress == pytest.approx(0.25)
    assert state.elapsed_s == pytest.approx(100, abs=3)
    assert state.eta_s == pytest.approx(300, abs=10)  # 100 s for 25 %
    assert state.last_eval == -2.5
    assert state.heldout is None
    (run / "heldout.csv").write_text(
        "policy,team_return_mean\ntrained,-1.5\nzero,-3.0\n", encoding="utf-8"
    )
    assert registry.runs("exp", root)[0].heldout == -1.5


def test_header_only_metrics_and_summary(root):
    run = root / "exp" / "run"
    write(run / "status.json", {"state": "running", "budget": 10} | me())
    (run / "metrics.csv").write_text("iteration,env_steps\n", encoding="utf-8")
    state = registry.runs("exp", root)[0]
    assert (state.env_steps, state.progress, state.eta_s) == (0, 0.0, None)
    info = registry.summary("exp", root)
    assert info["runs"] == 1 and info["counts"] == {"running": 1}


def test_registry_is_cheap(root):
    for i in range(30):
        write(root / "exp" / f"r{i}" / "status.json", {"state": "queued"})

    begin = time.perf_counter()
    registry.runs("exp", root)
    assert time.perf_counter() - begin < 1.0


def test_stop_marks_queued_and_running_runs_but_keeps_finished_ones(root):
    from core.runner import launch

    exp = root / "exp"
    write(exp / "q" / "status.json", {"state": "queued"})
    write(exp / "r" / "status.json", {"state": "running"} | dead_pid())
    write(exp / "d" / "status.json", {"state": "completed"})
    result = launch.stop("exp", "q", root=root)  # one run
    assert result == {"killed": [], "stopped": ["q"]}
    write(exp / "q" / "status.json", {"state": "queued"})
    result = launch.stop("exp", root=root)  # the whole experiment
    assert result["killed"] == []  # the recorded process is gone: nothing to kill
    assert sorted(result["stopped"]) == ["q", "r"]  # d is completed: left alone
    states = {s.name: s.state for s in registry.runs("exp", root)}
    assert states == {"q": "stopped", "r": "stopped", "d": "completed"}

    with pytest.raises(FileNotFoundError):
        launch.stop("nope", root=root)


# --------------------------------------------------------------------------------------
# Runs on a SLURM cluster
# --------------------------------------------------------------------------------------
SLURM_TERMINAL = [
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "TIMEOUT",
    "OUT_OF_MEMORY",
    "NODE_FAIL",
    "PREEMPTED",
    "BOOT_FAIL",
    "DEADLINE",
]


def slurm_map(task: str, state: str | None, node: str | None = "n1") -> dict:
    return {task: {"state": state, "node": node}} if state else {}


@pytest.mark.parametrize(
    "status, slurm_state, expected",
    [("running", state, "lost") for state in SLURM_TERMINAL]
    + [("queued", state, "lost") for state in SLURM_TERMINAL]
    + [
        ("running", "RUNNING", "running"),
        ("running", "COMPLETING", "running"),
        ("running", None, "running"),  # SLURM has not said
        ("queued", "RUNNING", "running"),  # started, the job has not written yet
        ("queued", "COMPLETING", "running"),
        ("queued", "PENDING", "queued"),
        ("queued", None, "queued"),
        ("completed", "COMPLETED", "completed"),
        ("completed", "CANCELLED", "completed"),
        ("failed", "FAILED", "failed"),
        ("stopped", "CANCELLED", "stopped"),
    ],
)
@pytest.mark.parametrize("process", [me, dead_pid], ids=["live pid", "dead pid"])
def test_slurm_runs_take_liveness_from_slurm_not_from_the_pid(
    root, status, slurm_state, expected, process
):
    run_dir = root / "exp" / "r"
    write(run_dir / "status.json", {"state": status, "slurm_job": "42_0"} | process())
    slurm = slurm_map("42_0", slurm_state) | slurm_map("42_1", "RUNNING")
    state = registry.runs("exp", root, slurm=slurm)[0]
    assert state.state == expected
    assert state.slurm_state == slurm_state
    assert registry.current_state(run_dir, slurm=slurm) == expected
    assert registry.summary("exp", root, slurm=slurm)["counts"] == {expected: 1}


def test_slurm_runs_without_the_slurm_map_keep_what_they_say(root):
    exp = root / "exp"
    write(exp / "a" / "status.json", {"state": "running", "slurm_job": "42_0"})
    write(exp / "b" / "status.json", {"state": "queued", "slurm_job": "42_1"})
    write(exp / "worker.json", dead_pid())  # no worker serves a SLURM run
    states = {s.name: s.state for s in registry.runs("exp", root)}
    assert states == {"a": "running", "b": "queued"}
    assert registry.runs("exp", root)[0].slurm_state is None


def test_runs_without_slurm_job_ignore_the_slurm_map(root):
    exp = root / "exp"
    write(exp / "a" / "status.json", {"state": "running", "index": 0} | dead_pid())
    write(exp / "b" / "status.json", {"state": "running", "index": 1} | me())
    write(exp / "c" / "status.json", {"state": "queued", "index": 2})
    slurm = {"42_0": {"state": "RUNNING", "node": "n1"}}

    for found in (registry.runs("exp", root), registry.runs("exp", root, slurm)):
        assert [(s.state, s.slurm_state) for s in found] == [
            ("lost", None),
            ("running", None),
            ("queued", None),
        ]


def test_run_state_reads_the_host(root):
    exp = root / "exp"
    write(exp / "a" / "status.json", {"state": "completed", "host": "node7"})
    write(exp / "b" / "status.json", {"state": "completed"})
    assert [s.host for s in registry.runs("exp", root)] == ["node7", None]


# --------------------------------------------------------------------------------------
# prepare and mark_stopped (launch)
# --------------------------------------------------------------------------------------
def test_prepare_writes_the_experiment_and_resets_unfinished_runs(root):
    from core.runner import launch

    experiment = Experiment.from_dict(
        spec(algorithms=["ppo"], paradigms=["dtde"], budget=2000, seeds=[0, 1, 2, 3]),
        "prep",
    )
    exp_dir = root / "prep"
    specs = launch.prepare(experiment, exp_dir)
    assert [s.name for s in specs] == [f"ppo_dtde_s{i}" for i in range(4)]
    assert Experiment.load(exp_dir / "experiment.json") == experiment
    assert {s.state for s in registry.runs("prep", root)} == {"queued"}
    assert registry.runs("prep", root)[0].budget == 2000

    for name, status in (
        ("ppo_dtde_s0", {"state": "completed"}),
        ("ppo_dtde_s1", {"state": "running"} | me()),
        ("ppo_dtde_s2", {"state": "failed"}),
        ("ppo_dtde_s3", {"state": "running", "slurm_job": "42_3"}),
    ):
        write(exp_dir / name / "status.json", status | {"index": 0, "budget": 1})

    (exp_dir / "ppo_dtde_s2" / "metrics.csv").write_text("a\n1\n", encoding="utf-8")
    slurm = {"42_3": {"state": "TIMEOUT", "node": "n1"}}
    launch.prepare(experiment, exp_dir, slurm=slurm)
    states = {s.name: s.state for s in registry.runs("prep", root)}
    assert states == {
        "ppo_dtde_s0": "completed",
        "ppo_dtde_s1": "running",
        "ppo_dtde_s2": "queued",  # failed: again from scratch
        "ppo_dtde_s3": "queued",  # lost on SLURM: again
    }
    assert not (exp_dir / "ppo_dtde_s2" / "metrics.csv").exists()
    status = registry.read_json(exp_dir / "ppo_dtde_s3" / "status.json")
    assert "slurm_job" not in status  # a fresh queue entry


def snapshot(folder: Path) -> dict[str, bytes]:
    return {
        path.relative_to(folder).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def test_prepare_refuses_a_changed_spec_and_writes_nothing(root):
    from core.runner import launch

    data = spec(algorithms=["ppo"], paradigms=["dtde"], budget=2000)
    experiment = Experiment.from_dict(data, "same")
    exp_dir = root / "same"
    launch.prepare(experiment, exp_dir)
    write(exp_dir / "ppo_dtde_s0" / "status.json", {"state": "failed", "index": 0})
    launch.prepare(experiment, exp_dir)  # the same spec resumes
    before = snapshot(exp_dir)

    for change in ({"budget": 3000}, {"seeds": [0, 1, 2]}, {"description": "x"}):
        changed = Experiment.from_dict(data | change, "same")
        with pytest.raises(SpecError, match="'same' changed.*new experiment name"):
            launch.prepare(changed, exp_dir)
        assert snapshot(exp_dir) == before  # experiment.json and statuses untouched


def test_prepare_compares_an_older_experiment_json_by_its_content(root):
    from core.runner import launch

    data = spec(algorithms=["ppo"], paradigms=["dtde"], budget=2000)
    experiment = Experiment.from_dict(data, "old")
    exp_dir = root / "old"
    write(exp_dir / "experiment.json", data)  # the spec as written, no name or defaults
    launch.prepare(experiment, exp_dir)  # the same content: accepted

    for unreadable in ('{"not": "a spec"}', "{half"):
        (exp_dir / "experiment.json").write_text(unreadable, encoding="utf-8")
        before = snapshot(exp_dir)

        with pytest.raises(SpecError, match="changed since it was started"):
            launch.prepare(experiment, exp_dir)

        assert snapshot(exp_dir) == before


def test_prepare_keeps_the_scenario_of_the_experiment_in_its_folder(root, tmp_path):
    from core.runner import launch

    scenario = tmp_path / "s.json"
    scenario.write_text('{"name": "one"}', encoding="utf-8")
    data = spec(algorithms=["ppo"], paradigms=["dtde"], scenario=str(scenario))
    exp_dir = root / "kept"
    launch.prepare(resolve(Experiment.from_dict(data, "kept")), exp_dir)
    assert registry.read_json(exp_dir / SCENARIO_FILE) == {"name": "one"}
    saved = registry.read_json(exp_dir / "experiment.json")
    assert saved["scenario"] == {"name": "one"}
    launch.prepare(resolve(Experiment.from_dict(data, "kept")), exp_dir)  # resumes
    scenario.write_text('{"name": "two"}', encoding="utf-8")

    with pytest.raises(SpecError, match="changed since it was started"):
        launch.prepare(resolve(Experiment.from_dict(data, "kept")), exp_dir)

    assert registry.read_json(exp_dir / SCENARIO_FILE) == {"name": "one"}


def test_prepare_resumes_a_folder_started_with_a_scenario_file(root, tmp_path):
    from core.runner import launch

    scenario = tmp_path / "s.json"
    scenario.write_text('{"name": "one"}', encoding="utf-8")
    data = spec(algorithms=["ppo"], paradigms=["dtde"], scenario=str(scenario))
    experiment = Experiment.from_dict(data, "older")
    exp_dir = root / "older"
    launch.prepare(experiment, exp_dir)  # as before: experiment.json names the file
    assert registry.read_json(exp_dir / "experiment.json")["scenario"] == str(scenario)
    assert not (exp_dir / SCENARIO_FILE).exists()
    launch.prepare(resolve(experiment), exp_dir)  # the same scenario: accepted
    assert registry.read_json(exp_dir / SCENARIO_FILE) == {"name": "one"}


def test_prepare_writes_the_test_version_under_its_own_name(root):
    from core.runner import launch

    version = Experiment.from_dict(spec(), "full").test_version()
    launch.prepare(version, root / version.name)
    written = registry.read_json(root / "full--test" / "experiment.json")
    assert written["name"] == "full--test" and written["seeds"] == [0]
    assert Experiment.from_dict(written) == version


def test_mark_stopped_without_kill_leaves_the_process_alone(root):
    from core.runner import launch

    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])

    try:
        process = {
            "pid": sleeper.pid,
            "create_time": psutil.Process(sleeper.pid).create_time(),
        }
        exp = root / "exp"
        write(exp / "r" / "status.json", {"state": "running"} | process)
        write(exp / "q" / "status.json", {"state": "queued"})
        write(exp / "d" / "status.json", {"state": "completed"})
        result = launch.mark_stopped(exp, kill=False)
        assert result["killed"] == [] and sorted(result["stopped"]) == ["q", "r"]
        assert sleeper.poll() is None  # still running
        write(exp / "r" / "status.json", {"state": "running"} | process)
        result = launch.mark_stopped(exp, "r")  # kill=True by default
        assert result == {"killed": ["r"], "stopped": ["r"]}
        sleeper.wait(timeout=20)
    finally:
        sleeper.kill()

    with pytest.raises(FileNotFoundError, match="no run 'x'"):
        launch.mark_stopped(exp, "x")

    with pytest.raises(FileNotFoundError, match="no experiment"):
        launch.experiment_dir("nope", root)


def test_a_row_still_being_written_is_not_read(tmp_path):
    path = tmp_path / "metrics.csv"
    path.write_text("iteration,env_steps\n1,100\n2,2", encoding="utf-8")
    assert registry._last_row(path) == {"iteration": "1", "env_steps": "100"}
    path.write_text("iteration,env_steps\n1,100\n2,200\n", encoding="utf-8")
    assert registry._last_row(path)["env_steps"] == "200"
    path.write_text("iteration,env", encoding="utf-8")  # the header, half written
    assert registry._last_row(path) is None
    evaluation = tmp_path / "evaluation.csv"
    evaluation.write_text(
        "policy,team_return_mean\ntrained,-7.5\ntrained,-6", encoding="utf-8"
    )
    assert registry._trained_return(evaluation, last=True) == -7.5
