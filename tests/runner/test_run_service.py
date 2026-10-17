"""The Studio's RunService (``studio/adapters/run_service.py``) over a temporary
``runs/`` that ``$MARLEM_RUNS`` points at, and over fake targets: it lists the
experiments newest first, hands the calls to the target it is given and returns the
runner's records as they are. No training, no cluster, no browser.

Run with ``python -m pytest tests/runner -q`` in the ``marlem`` conda env.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from core.runner import targets
from core.runner.registry import RunState
from core.runner.spec import REPO, Experiment
from studio.adapters.run_service import RunService


def make_run(exp_dir, name, **status):
    run_dir = exp_dir / name
    run_dir.mkdir(parents=True)
    (run_dir / "status.json").write_text(json.dumps(status), encoding="utf-8")
    return run_dir


@pytest.fixture()
def runs_root(tmp_path, monkeypatch):
    monkeypatch.setenv("MARLEM_RUNS", str(tmp_path))
    return tmp_path


class FakeTarget:
    """What the service calls on a target; every call is recorded in ``calls``."""

    def __init__(self, name, entries=(), copied=None):
        self.name = name
        self.entries = list(entries)
        self.calls: list[tuple] = []
        self.closed = False
        self.copied = copied  # files the last sync copied; None for a LocalTarget

    def overview(self):
        self.calls.append(("overview",))
        return list(self.entries)

    def check(self, spec_path=None):
        self.calls.append(("check", spec_path))
        return {"target": self.name, "ok": True}

    def start(self, spec_path, profile="full"):
        self.calls.append(("start", spec_path, profile))
        return "x--test" if profile == "test" else "x"

    def stop(self, experiment, run=None):
        self.calls.append(("stop", experiment, run))
        return {"cancelled": ["7"], "stopped": ["a"]}

    def sync(self, experiment):
        self.calls.append(("sync", experiment))
        return Path("mirror") / experiment

    def close(self):
        self.closed = True


@pytest.fixture()
def fakes(monkeypatch):
    """``targets.get`` hands out one fake per name; ``made`` records each call."""
    found = {
        "local": FakeTarget("local"),
        "taltech": FakeTarget("taltech", copied=3),
    }
    made: list[tuple] = []

    def get(name="local", root=None, path=None):
        made.append((name, root))
        return found[name]

    monkeypatch.setattr(targets, "get", get)
    found["made"] = made
    return found


# --------------------------------------------------------------------------------------
# This PC's runs
# --------------------------------------------------------------------------------------
def test_overview_of_this_pc_has_the_runs_newest_first(runs_root):
    make_run(runs_root / "old", "a", state="completed", budget=100, index=0)
    make_run(runs_root / "new", "b", state="queued", budget=100, index=1)
    make_run(runs_root / "new", "a", state="stopped", budget=100, index=0)
    os.utime(runs_root / "old", (1_000_000, 1_000_000))  # older than `new`
    (runs_root / "new" / "experiment.json").write_text('{"description": "hi"}')

    found = RunService().overview("local")
    assert [e["name"] for e in found] == ["new", "old"]
    assert found[0]["spec"] == {"description": "hi"} and found[1]["spec"] is None
    assert found[0]["summary"]["counts"] == {"queued": 1, "stopped": 1}
    runs = found[0]["runs"]
    assert all(isinstance(r, RunState) for r in runs)
    assert [(r.name, r.state) for r in runs] == [("a", "stopped"), ("b", "queued")]
    folder, copied = RunService().sync("local", "new")
    assert (folder, copied) == (runs_root / "new", 0)  # the files are here already


def test_stop_marks_queued_runs_stopped(runs_root):
    exp = runs_root / "x"
    make_run(exp, "a", state="queued", budget=100, index=0)
    make_run(exp, "b", state="queued", budget=100, index=1)

    service = RunService()

    def states():
        (entry,) = service.overview("local")
        return [r.state for r in entry["runs"]]

    assert service.stop("local", "x", "a") == {"killed": [], "stopped": ["a"]}
    assert states() == ["stopped", "queued"]
    assert service.stop("local", "x")["stopped"] == ["b"]
    assert set(states()) == {"stopped"}
    with pytest.raises(FileNotFoundError):
        service.stop("local", "missing")


def test_this_pc_is_always_ready():
    report = RunService().check("local", "experiments/smoke.json")
    assert report["ok"] and report["problems"] == []


# --------------------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------------------
def test_target_names_and_labels_come_from_targets_toml(tmp_path, monkeypatch):
    service = RunService()
    assert service.target_names() == [("local", "This PC"), ("taltech", "TalTech")]
    elsewhere = tmp_path / "targets.toml"
    elsewhere.write_text(
        '[x]\nkind = "slurm"\nlabel = "The X"\n[y]\nkind = "slurm"\n', encoding="utf-8"
    )
    monkeypatch.setattr(targets, "TARGETS_FILE", elsewhere)
    assert service.target_names() == [("local", "local"), ("x", "The X"), ("y", "y")]


def test_a_target_is_made_once_and_closed_with_the_service(fakes, tmp_path):
    service = RunService(root=tmp_path)
    assert service.target("local") is fakes["local"]
    assert service.target("local") is fakes["local"]
    assert service.target("taltech") is fakes["taltech"]
    # This PC's folder is `root`; a cluster keeps its own copy of the results.
    assert fakes["made"] == [("local", tmp_path), ("taltech", None)]
    service.close()
    assert fakes["local"].closed and fakes["taltech"].closed
    service.target("local")
    assert len(fakes["made"]) == 3  # made again after closing


def test_making_a_real_cluster_target_connects_to_nothing():
    service = RunService()
    cluster = service.target("taltech")
    assert isinstance(cluster, targets.Target) and cluster.name == "taltech"
    assert getattr(getattr(cluster, "remote", None), "_thread", None) is None
    service.close()
    with pytest.raises(targets.TargetError, match="unknown target 'nope'"):
        service.target("nope")


def test_overview_is_the_targets_newest_first(fakes):
    old = {"name": "old", "modified": 1.0, "runs": [], "spec": None}
    new = {"name": "new", "modified": 9.0, "runs": [], "spec": {"description": "d"}}
    fakes["taltech"].entries = [old, new]
    assert RunService().overview("taltech") == [new, old]
    assert fakes["taltech"].calls == [("overview",)]
    assert fakes["local"].calls == []


def test_check_start_stop_and_sync_go_to_the_target_asked(fakes):
    service = RunService()
    assert service.check("taltech") == {"target": "taltech", "ok": True}
    service.check("taltech", "experiments/x.json")
    assert service.start("taltech", "experiments/x.json", "test") == "x--test"
    assert service.start("local", Path("experiments/x.json")) == "x"
    assert service.stop("taltech", "x", "a") == {"cancelled": ["7"], "stopped": ["a"]}
    assert service.stop("taltech", "x")["stopped"] == ["a"]
    assert service.sync("taltech", "x") == (Path("mirror") / "x", 3)
    assert service.sync("local", "x") == (Path("mirror") / "x", 0)  # nothing copied
    assert fakes["taltech"].calls == [
        ("check", None),
        ("check", "experiments/x.json"),
        ("start", "experiments/x.json", "test"),
        ("stop", "x", "a"),
        ("stop", "x", None),
        ("sync", "x"),
    ]
    assert fakes["local"].calls == [
        ("start", Path("experiments/x.json"), "full"),
        ("sync", "x"),
    ]


# --------------------------------------------------------------------------------------
# Experiment specs
# --------------------------------------------------------------------------------------
def test_the_experiments_folder_specs_all_load():
    found = RunService().spec_files()
    paths = sorted((REPO / "experiments").glob("*.json"))
    assert [r["path"] for r in found] == paths and paths
    for record in found:
        assert record["error"] is None, record
        experiment = Experiment.load(record["path"])
        assert record["name"] == experiment.name
        assert record["description"] == experiment.description
        assert record["runs"] == len(experiment.expand()) >= 1
        assert record["test_runs"] == len(experiment.test_version().expand()) >= 1
        assert record["budget"] == experiment.budget
        assert record["resources"] == experiment.run_resources
        assert record["test_budget"] == experiment.test_version().budget
        assert record["test_resources"]["minutes"] == 15  # the test's default


def test_the_smoke_spec_in_numbers():
    (smoke,) = [r for r in RunService().spec_files() if r["name"] == "smoke"]
    assert (smoke["runs"], smoke["test_runs"]) == (2, 1)  # two seeds; the first only
    assert smoke["budget"] == 2000
    assert smoke["test_budget"] == {"ppo": 500}  # one training iteration
    assert smoke["resources"] == {"cpus": 4, "mem_gb": 4, "minutes": 120}


def test_a_spec_that_does_not_load_says_why(tmp_path):
    good = json.loads((REPO / "experiments" / "smoke.json").read_text("utf-8"))
    (tmp_path / "a_good.json").write_text(json.dumps(good), encoding="utf-8")
    (tmp_path / "b_not_json.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "c_unknown.json").write_text(
        json.dumps(good | {"colour": "red"}), encoding="utf-8"
    )
    (tmp_path / "d_no_scenario.json").write_text(
        json.dumps(good | {"scenario": "scenarios/missing.json"}), encoding="utf-8"
    )
    (tmp_path / "notes.txt").write_text("not a spec", encoding="utf-8")

    found = RunService(specs=tmp_path).spec_files()
    assert [r["path"].name for r in found] == [
        "a_good.json",
        "b_not_json.json",
        "c_unknown.json",
        "d_no_scenario.json",
    ]
    assert found[0]["error"] is None and found[0]["name"] == "a_good"
    for record, message in zip(found[1:], ["not valid JSON", "colour", "not found"]):
        assert message in record["error"]
        assert record["runs"] is None and record["resources"] is None
        assert record["name"] == record["path"].stem
    assert RunService(specs=tmp_path / "nowhere").spec_files() == []
