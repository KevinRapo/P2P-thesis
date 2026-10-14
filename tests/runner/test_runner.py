"""The runner (``core/runner/``): experiment files, expansion, and the registry.

Fast checks without training: specs are expanded and validated, and the registry
reads hand-written status files in a temporary ``runs/``.

Run with ``python -m pytest tests/runner -q`` in the ``marlem`` conda env.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import psutil
import pytest

from core.runner import registry
from core.runner.spec import ALGORITHMS, PARADIGMS, REPO, Experiment, SpecError

SCENARIO = "scenarios/validate_market.json"


def spec(**changes) -> dict:
    base = {
        "scenario": SCENARIO,
        "train_days": {"from": "2016-06-01", "to": "2016-06-03"},
        "test_days": ["2016-07-01", "2016-07-02"],
        "algorithms": ["ppo", "sac"],
        "paradigms": ["dtde", "ctde"],
        "seeds": [0, 1],
        "budget": {"ppo": 2000, "sac": 500},
        "eval_points": 4,
    }
    return base | changes


# --------------------------------------------------------------------------------------
# Experiment files
# --------------------------------------------------------------------------------------
def test_names_in_the_order_of_the_grid():
    runs = Experiment.from_dict(spec(), "x").expand(Path("out"))
    assert len(runs) == 2 * 2 * 2
    assert runs[0].name == "ppo_dtde_s0"
    assert [r.name for r in runs[:4]] == [
        "ppo_dtde_s0",
        "ppo_dtde_s1",
        "ppo_ctde_s0",
        "ppo_ctde_s1",
    ]
    assert [r.index for r in runs] == list(range(8))
    assert runs[0].out_dir == Path("out") / "ppo_dtde_s0"


def test_default_name_is_the_file_stem(tmp_path):
    path = tmp_path / "my_experiment.json"
    path.write_text(json.dumps(spec()), encoding="utf-8")
    assert Experiment.load(path).name == "my_experiment"


def test_budget_and_eval_every_per_algorithm():
    runs = {r.algorithm: r for r in Experiment.from_dict(spec(), "x").expand()}
    assert (runs["ppo"].budget, runs["ppo"].eval_every) == (2000, 500)
    assert (runs["sac"].budget, runs["sac"].eval_every) == (500, 125)
    data = spec(eval_points=None, eval_every={"ppo": 700, "sac": 0})
    runs = {r.algorithm: r for r in Experiment.from_dict(data, "x").expand()}
    assert (runs["ppo"].eval_every, runs["sac"].eval_every) == (700, 0)


def test_variants_merge_over_the_algorithm_settings():
    data = spec(
        algorithms=["sac"],
        paradigms=["dtde"],
        seeds=[3],
        variants={"a1": {"initial_alpha": 1.0}, "a0.1": {"actor_lr": 0.1}},
        training={"sac": {"actor_lr": 0.0003, "initial_alpha": 0.5}},
    )
    runs = Experiment.from_dict(data, "x").expand()
    assert [r.name for r in runs] == ["sac_dtde_s3_a1", "sac_dtde_s3_a0.1"]
    assert runs[0].training == {"actor_lr": 0.0003, "initial_alpha": 1.0}
    assert runs[1].training == {"actor_lr": 0.1, "initial_alpha": 0.5}


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


def test_heldout_seeds_default_to_one_per_test_day():
    experiment = Experiment.from_dict(spec(), "x")
    assert experiment.heldout_seed_list() == [2000, 2001]
    assert Experiment.from_dict(spec(heldout_seeds=3), "x").heldout_seed_list() == [
        2000,
        2001,
        2002,
    ]
    assert Experiment.from_dict(spec(heldout_seeds=[5]), "x").heldout_seed_list() == [5]


def test_out_dir_defaults_to_the_runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MARLEM_RUNS", str(tmp_path))
    assert Experiment.from_dict(spec(), "exp").expand()[0].out_dir == (
        tmp_path / "exp" / "ppo_dtde_s0"
    )


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"algorithms": ["ppo", "dqn"]}, "unknown algorithms"),
        ({"paradigms": ["ctxe"]}, "unknown paradigms"),
        ({"scenario": "scenarios/nope.json"}, "scenario file not found"),
        ({"scenario": None}, "needs a 'scenario'"),
        ({"budget": {"ppo": 10}}, "no entry for algorithm 'sac'"),
        ({"eval_every": 10}, "not both"),
        ({"seeds": []}, "seeds"),
        ({"seeds": [0, 0]}, "seeds"),
        ({"test_days": {"from": "2016-07-05", "to": "2016-07-01"}}, "before"),
        ({"train_days": ["2016-13-01"]}, "bad date"),
        ({"training": {"dqn": {}}}, "'training' maps"),
        ({"trainning": {}}, "unknown field"),
        ({"variants": {"a b": {}}}, "plain word"),
        ({"max_parallel": 0}, "max_parallel"),
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
    for path in sorted((REPO / "experiments").glob("*.json")):
        assert Experiment.load(path).expand(), path


def test_axis_names_match_the_trainer():
    from core.rl.config import Algorithm, Paradigm

    assert ALGORITHMS == tuple(a.value for a in Algorithm)
    assert PARADIGMS == tuple(p.value for p in Paradigm)


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
