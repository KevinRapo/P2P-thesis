"""The SLURM backend (``core/runner/slurm.py``) without a cluster: ``sacct`` output is
parsed from text, and submitit and the SLURM commands are replaced by fakes that
record what they are asked, over a temporary ``runs/``. No training.

Run with ``python -m pytest tests/runner -q`` in the ``marlem`` conda env.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from core.runner import launch, registry, slurm
from core.runner.spec import Experiment, SpecError

SCENARIO = "scenarios/validate_market.json"
ARRAY = "1042700"


def spec_file(tmp_path: Path, name: str = "exp", **changes) -> Path:
    data = {
        "scenario": SCENARIO,
        "train_days": ["2016-06-01", "2016-06-02"],
        "test_days": ["2016-07-01"],
        "algorithms": ["ppo"],
        "paradigms": ["dtde", "ctde"],
        "seeds": [0, 1],
        "budget": 2000,
        "training": {"ppo": {"train_batch_size_per_learner": 500}},
        "resources": {"cpus": 2, "mem_gb": 3, "minutes": 90},
        "max_parallel": 2,
    } | changes
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


PARTITIONS = [
    {"name": "short", "max_minutes": 240},
    {"name": "common", "max_minutes": 11520},
]


# --------------------------------------------------------------------------------------
# sacct output
# --------------------------------------------------------------------------------------
def test_parse_one_line_per_task():
    text = (
        f"{ARRAY}_0|COMPLETED|node1\n"
        f"{ARRAY}_1|RUNNING|node2\n"
        f"{ARRAY}_2|FAILED|node1\n"
    )
    assert slurm.parse_sacct(text) == {
        f"{ARRAY}_0": {"state": "COMPLETED", "node": "node1"},
        f"{ARRAY}_1": {"state": "RUNNING", "node": "node2"},
        f"{ARRAY}_2": {"state": "FAILED", "node": "node1"},
    }


def test_parse_first_word_of_the_state_and_missing_nodes():
    text = (
        f"{ARRAY}_0|CANCELLED by 1234|None assigned\n"
        f"{ARRAY}_1|CANCELLED+|\n"
        f"{ARRAY}_2|PENDING|None assigned\n"
    )
    found = slurm.parse_sacct(text)
    assert found[f"{ARRAY}_0"] == {"state": "CANCELLED", "node": None}
    assert found[f"{ARRAY}_1"] == {"state": "CANCELLED", "node": None}
    assert found[f"{ARRAY}_2"] == {"state": "PENDING", "node": None}


@pytest.mark.parametrize(
    "job_id, tasks",
    [
        (f"{ARRAY}_[4-9%3]", [4, 5, 6, 7, 8, 9]),
        (f"{ARRAY}_[4-9]", [4, 5, 6, 7, 8, 9]),
        (f"{ARRAY}_[1,3-5]", [1, 3, 4, 5]),
        (f"{ARRAY}_[1,3-5%2]", [1, 3, 4, 5]),
        (f"{ARRAY}_[7]", [7]),
        (f"{ARRAY}_[0-10:5]", [0, 5, 10]),
        (f"{ARRAY}_[2,8-9:1,12]", [2, 8, 9, 12]),
    ],
)
def test_parse_expands_pending_ranges(job_id, tasks):
    found = slurm.parse_sacct(f"{job_id}|PENDING|None assigned\n")
    assert sorted(found, key=lambda t: int(t.split("_")[1])) == [
        f"{ARRAY}_{i}" for i in tasks
    ]
    assert {info["state"] for info in found.values()} == {"PENDING"}
    assert {info["node"] for info in found.values()} == {None}


def test_parse_mixed_running_and_pending_and_noise():
    text = (
        "\n"
        f"{ARRAY}_0|RUNNING|node1\n"
        f"{ARRAY}_[1-2%2]|PENDING|None assigned\n"
        f"{ARRAY}_0.batch|COMPLETED|node1\n"  # a step
        "garbage\n"
        f"{ARRAY}_3|\n"  # too short
    )
    assert slurm.parse_sacct(text) == {
        f"{ARRAY}_0": {"state": "RUNNING", "node": "node1"},
        f"{ARRAY}_1": {"state": "PENDING", "node": None},
        f"{ARRAY}_2": {"state": "PENDING", "node": None},
    }
    assert slurm.parse_sacct("") == {}


def test_parse_a_plain_job():
    # submitit submits an array of one run as a plain job (no _index)
    assert slurm.parse_sacct(f"{ARRAY}|FAILED|green20\n") == {
        ARRAY: {"state": "FAILED", "node": "green20"}
    }


def test_states_asks_sacct_once_for_the_array(tmp_path, monkeypatch):
    write(tmp_path / "slurm.json", {"array_id": ARRAY})
    calls = []

    def fake_run(command, **options):
        calls.append(command)
        return subprocess.CompletedProcess(
            command, 0, stdout=f"{ARRAY}_0|RUNNING|n1\n{ARRAY}_[1-2]|PENDING|\n"
        )

    monkeypatch.setattr(slurm.subprocess, "run", fake_run)
    found = slurm.states(tmp_path)
    assert sorted(found) == [f"{ARRAY}_0", f"{ARRAY}_1", f"{ARRAY}_2"]
    assert len(calls) == 1
    assert calls[0][:3] == ["sacct", "-j", ARRAY]
    assert {"-n", "-P", "-X"} <= set(calls[0])
    assert calls[0][-1] == "JobID,State,NodeList"


def test_states_is_empty_without_slurm_json_or_sacct(tmp_path, monkeypatch):
    def broken(command, **options):
        raise AssertionError("sacct must not be called")

    monkeypatch.setattr(slurm.subprocess, "run", broken)
    assert slurm.states(tmp_path) == {}  # never submitted: no call at all
    write(tmp_path / "slurm.json", {"array_id": ARRAY})

    def missing(command, **options):
        raise FileNotFoundError("sacct")

    monkeypatch.setattr(slurm.subprocess, "run", missing)
    assert slurm.states(tmp_path) == {}

    def failing(command, **options):
        return subprocess.CompletedProcess(command, 1, stdout="x_0|RUNNING|n\n")

    monkeypatch.setattr(slurm.subprocess, "run", failing)
    assert slurm.states(tmp_path) == {}

    def slow(command, **options):
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr(slurm.subprocess, "run", slow)
    assert slurm.states(tmp_path) == {}


# --------------------------------------------------------------------------------------
# start
# --------------------------------------------------------------------------------------
class FakeJob:
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id


class FakeExecutor:
    """Stands in for ``submitit.AutoExecutor``: records, submits nothing."""

    created: list = []
    next_array = ARRAY

    def __init__(self, folder, cluster=None) -> None:
        self.folder = Path(folder)
        self.cluster = cluster
        self.parameters: dict = {}
        self.mapped: list = []
        FakeExecutor.created.append(self)

    def update_parameters(self, **parameters) -> None:
        self.parameters |= parameters

    def map_array(self, fn, *iterable):
        arguments = list(zip(*iterable))
        self.mapped.append((fn, arguments))
        return [FakeJob(f"{self.next_array}_{i}") for i in range(len(arguments))]


@pytest.fixture()
def cluster(tmp_path, monkeypatch):
    """A fake cluster: ``sbatch`` exists, submitit is a recorder, sacct knows
    nothing until a test fills ``answer``."""
    FakeExecutor.created = []
    answer: dict = {}
    monkeypatch.setattr(slurm.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(slurm.submitit, "AutoExecutor", FakeExecutor)
    monkeypatch.setattr(slurm, "states", lambda exp_dir: dict(answer))
    root = tmp_path / "runs"
    root.mkdir()
    return root, answer


def test_start_submits_one_array_task_per_run(tmp_path, cluster):
    root, _ = cluster
    path = spec_file(tmp_path)
    exp_dir = slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    assert exp_dir == root / "exp"

    (executor,) = FakeExecutor.created
    assert executor.folder == exp_dir / "slurm"
    assert executor.cluster == "slurm"  # never submitit's local fallback
    parameters = executor.parameters
    assert parameters["name"] == "marlem-exp"
    assert parameters["timeout_min"] == 90
    assert parameters["cpus_per_task"] == 2
    assert parameters["mem_gb"] == 3
    assert parameters["slurm_partition"] == "short"
    assert parameters["slurm_account"] == "acc"
    assert parameters["slurm_array_parallelism"] == 2
    setup = parameters["slurm_setup"]
    assert setup[0].startswith("export PYTHONPATH=")
    assert "export PYTHONUNBUFFERED=1" in setup
    assert "export PYTHONHASHSEED=0" in setup  # the same seed, the same run

    ((fn, arguments),) = executor.mapped
    assert fn is launch.job  # the same job as a local worker runs
    names = ["ppo_dtde_s0", "ppo_dtde_s1", "ppo_ctde_s0", "ppo_ctde_s1"]
    assert arguments == [(str(exp_dir / name),) for name in names]

    record = registry.read_json(exp_dir / "slurm.json")
    assert record["array_id"] == ARRAY
    assert record["partition"] == "short" and record["account"] == "acc"
    assert record["resources"] == {"cpus": 2, "mem_gb": 3, "minutes": 90}
    assert record["tasks"] == {name: f"{ARRAY}_{i}" for i, name in enumerate(names)}
    assert record["submitted"]
    for i, name in enumerate(names):
        status = registry.read_json(exp_dir / name / "status.json")
        assert (status["state"], status["slurm_job"]) == ("queued", f"{ARRAY}_{i}")
    assert Experiment.load(exp_dir / "experiment.json") == Experiment.load(path)
    assert {s.state for s in registry.runs("exp", root)} == {"queued"}


def test_start_the_test_profile_is_small_and_short(tmp_path, cluster):
    root, _ = cluster
    path = spec_file(tmp_path, resources={"minutes": 600})
    exp_dir = slurm.start(
        path, account="acc", partitions=PARTITIONS, root=root, profile="test"
    )
    assert exp_dir.name == "exp--test"
    (executor,) = FakeExecutor.created
    assert executor.parameters["timeout_min"] == 15
    assert executor.parameters["slurm_partition"] == "short"
    ((_, arguments),) = executor.mapped
    assert len(arguments) == 2  # one seed: dtde and ctde
    version = Experiment.load(exp_dir / "experiment.json")
    assert (version.seeds, version.budget) == ([0], {"ppo": 500})


def test_start_picks_the_first_partition_that_allows_the_minutes(tmp_path, cluster):
    root, _ = cluster
    path = spec_file(tmp_path, resources={"minutes": 600})
    slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    assert FakeExecutor.created[0].parameters["slurm_partition"] == "common"
    assert registry.read_json(root / "exp" / "slurm.json")["partition"] == "common"


def test_choose_partition():
    assert slurm.choose_partition(PARTITIONS, 240) == PARTITIONS[0]
    assert slurm.choose_partition(PARTITIONS, 241) == PARTITIONS[1]
    with pytest.raises(SpecError, match="no partition allows 20000 minutes"):
        slurm.choose_partition(PARTITIONS, 20000)
    with pytest.raises(SpecError, match="no partition"):
        slurm.choose_partition([], 10)


def test_start_with_no_fitting_partition_changes_nothing(tmp_path, cluster):
    root, _ = cluster
    path = spec_file(tmp_path, resources={"minutes": 20000})
    with pytest.raises(SpecError, match="no partition allows"):
        slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    assert list(root.iterdir()) == [] and FakeExecutor.created == []


def test_start_needs_sbatch(tmp_path, cluster, monkeypatch):
    root, _ = cluster
    monkeypatch.setattr(slurm.shutil, "which", lambda name: None)
    with pytest.raises(RuntimeError, match="sbatch not found"):
        slurm.start(spec_file(tmp_path), account="a", partitions=PARTITIONS, root=root)
    assert list(root.iterdir()) == []


def test_start_refuses_while_tasks_are_queued_or_running(tmp_path, cluster):
    root, answer = cluster
    path = spec_file(tmp_path)
    slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    answer |= {f"{ARRAY}_0": {"state": "RUNNING", "node": "n1"}}
    answer |= {f"{ARRAY}_1": {"state": "COMPLETED", "node": "n1"}}
    answer |= {f"{ARRAY}_2": {"state": "PENDING", "node": None}}
    with pytest.raises(RuntimeError, match=r"still has 2 task\(s\)"):
        slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    assert len(FakeExecutor.created) == 1  # nothing was submitted again


def test_start_refuses_when_sacct_cannot_say(tmp_path, cluster):
    root, _ = cluster  # slurm.json exists, the fake sacct answers nothing
    path = spec_file(tmp_path)
    slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    with pytest.raises(RuntimeError, match="cannot tell"):
        slurm.start(path, account="acc", partitions=PARTITIONS, root=root)


def test_start_again_submits_only_the_runs_that_are_not_completed(tmp_path, cluster):
    root, answer = cluster
    path = spec_file(tmp_path)
    exp_dir = slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    names = ["ppo_dtde_s0", "ppo_dtde_s1", "ppo_ctde_s0", "ppo_ctde_s1"]
    launch.write_status(exp_dir / names[0], state="completed")
    launch.write_status(exp_dir / names[1], state="running")  # the task timed out
    launch.write_status(exp_dir / names[2], state="failed")
    launch.write_status(exp_dir / names[3], state="running")  # cancelled before start
    answer |= {
        f"{ARRAY}_0": {"state": "COMPLETED", "node": "n1"},
        f"{ARRAY}_1": {"state": "TIMEOUT", "node": "n1"},
        f"{ARRAY}_2": {"state": "FAILED", "node": "n2"},
        f"{ARRAY}_3": {"state": "CANCELLED", "node": None},
    }
    FakeExecutor.next_array = "2000"
    try:
        slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    finally:
        FakeExecutor.next_array = ARRAY

    second = FakeExecutor.created[1]
    ((_, arguments),) = second.mapped
    assert arguments == [(str(exp_dir / name),) for name in names[1:]]
    record = registry.read_json(exp_dir / "slurm.json")
    assert record["array_id"] == "2000"
    assert record["tasks"] == {name: f"2000_{i}" for i, name in enumerate(names[1:])}
    done = registry.read_json(exp_dir / names[0] / "status.json")
    assert (done["state"], done["slurm_job"]) == ("completed", f"{ARRAY}_0")
    again = registry.read_json(exp_dir / names[1] / "status.json")
    assert (again["state"], again["slurm_job"]) == ("queued", "2000_0")


def test_start_with_everything_completed_submits_nothing(tmp_path, cluster):
    root, answer = cluster
    path = spec_file(tmp_path)
    exp_dir = slurm.start(path, account="acc", partitions=PARTITIONS, root=root)
    for i, run_dir in enumerate(sorted(p for p in exp_dir.iterdir() if p.is_dir())):
        if run_dir.name != "slurm":
            launch.write_status(run_dir, state="completed")
            answer[f"{ARRAY}_{i}"] = {"state": "COMPLETED", "node": "n1"}
    before = registry.read_json(exp_dir / "slurm.json")
    assert slurm.start(path, account="a", partitions=PARTITIONS, root=root) == exp_dir
    assert len(FakeExecutor.created) == 1
    assert registry.read_json(exp_dir / "slurm.json") == before


# --------------------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------------------
@pytest.fixture()
def scancel(monkeypatch):
    """Records the scancel calls; ``result["code"]`` is its exit status and
    ``result["stderr"]`` what it prints then."""
    result = {"calls": [], "code": 0, "stderr": ""}

    def fake_run(command, **options):
        result["calls"].append(command)
        return subprocess.CompletedProcess(
            command, result["code"], stdout="", stderr=result["stderr"]
        )

    monkeypatch.setattr(slurm.subprocess, "run", fake_run)
    return result


def submitted(tmp_path) -> Path:
    exp = tmp_path / "exp"
    write(exp / "slurm.json", {"array_id": ARRAY})
    write(exp / "a" / "status.json", {"state": "queued", "slurm_job": f"{ARRAY}_0"})
    write(exp / "b" / "status.json", {"state": "running", "slurm_job": f"{ARRAY}_1"})
    write(exp / "c" / "status.json", {"state": "completed", "slurm_job": f"{ARRAY}_2"})
    return exp


def test_stop_cancels_the_array_and_marks_the_runs(tmp_path, scancel):
    exp = submitted(tmp_path)
    result = slurm.stop("exp", root=tmp_path)
    assert scancel["calls"] == [["scancel", ARRAY]]
    assert result["cancelled"] == [ARRAY]
    assert sorted(result["stopped"]) == ["a", "b"]  # c is completed: left alone
    states = {s.name: s.state for s in registry.runs("exp", tmp_path)}
    assert states == {"a": "stopped", "b": "stopped", "c": "completed"}
    assert (exp / "slurm.json").exists()


def test_stop_one_run_cancels_only_its_task(tmp_path, scancel):
    submitted(tmp_path)
    result = slurm.stop("exp", "b", tmp_path)
    assert scancel["calls"] == [["scancel", f"{ARRAY}_1"]]
    assert result == {"cancelled": [f"{ARRAY}_1"], "stopped": ["b"]}
    states = {s.name: s.state for s in registry.runs("exp", tmp_path)}
    assert states == {"a": "queued", "b": "stopped", "c": "completed"}


def test_a_failed_scancel_raises_with_its_message_and_marks_nothing(tmp_path, scancel):
    submitted(tmp_path)
    scancel["code"] = 1
    scancel["stderr"] = "scancel: error: Invalid job id specified"
    with pytest.raises(RuntimeError, match=r"scancel 1042700 failed.*Invalid job id"):
        slurm.stop("exp", root=tmp_path)
    assert {s.name: s.state for s in registry.runs("exp", tmp_path)} == {
        "a": "queued",
        "b": "running",
        "c": "completed",
    }
    with pytest.raises(RuntimeError, match="nothing was marked stopped"):
        slurm.stop("exp", "b", tmp_path)
    assert registry.read_json(tmp_path / "exp" / "b" / "status.json")["state"] == (
        "running"
    )


def test_stop_without_slurm_job_calls_no_scancel(tmp_path, scancel):
    write(tmp_path / "exp" / "a" / "status.json", {"state": "queued"})
    assert slurm.stop("exp", root=tmp_path) == {"cancelled": [], "stopped": ["a"]}
    assert scancel["calls"] == []


def test_stop_unknown_experiment_or_run(tmp_path, scancel):
    submitted(tmp_path)
    with pytest.raises(FileNotFoundError, match="no experiment 'nope'"):
        slurm.stop("nope", root=tmp_path)
    with pytest.raises(FileNotFoundError, match="no run 'zzz'"):
        slurm.stop("exp", "zzz", tmp_path)
    assert scancel["calls"] == []


def test_stop_without_scancel_is_an_error_and_marks_nothing(tmp_path, monkeypatch):
    submitted(tmp_path)

    def missing(command, **options):
        raise FileNotFoundError("scancel")

    monkeypatch.setattr(slurm.subprocess, "run", missing)
    with pytest.raises(FileNotFoundError, match="scancel"):
        slurm.stop("exp", root=tmp_path)
    assert {s.state for s in registry.runs("exp", tmp_path)} == {
        "queued",
        "running",
        "completed",
    }
