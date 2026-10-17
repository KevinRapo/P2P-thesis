"""The targets (``core/runner/targets.py``, ``hpc/targets.toml``) and the command line
(``python -m core.runner``) over a temporary ``runs/`` that ``$MARLEM_RUNS`` points
at. Nothing is started and no cluster is needed: starting and SLURM are replaced by
recorders, and the cluster seen from the PC (``RemoteTarget``) talks to a fake
``Remote`` that records what it is asked. No training, no network.

Run with ``python -m pytest tests/runner -q`` in the ``marlem`` conda env.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core.runner import launch, slurm, targets
from core.runner.__main__ import main
from core.runner.registry import RunState
from core.runner.remote import Remote, RemoteError
from core.runner.spec import REPO

ARRAY = "1042700"
CLUSTER = {
    "kind": "slurm",
    "account": "acc",
    "partitions": [{"name": "short", "max_minutes": 240}],
}
REPORT_KEYS = ["target", "ok", "problems", "local_commit", "cluster_commit", "active"]


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture()
def root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("MARLEM_RUNS", str(tmp_path))
    return tmp_path


@pytest.fixture()
def populated(root) -> Path:
    """Two experiments: ``old`` (all completed) and ``new`` (a queued and a stopped
    run, with a description)."""
    write(root / "old" / "a" / "status.json", {"state": "completed", "index": 0})
    write(root / "new" / "experiment.json", {"name": "new", "description": "hi"})
    write(root / "new" / "b" / "status.json", {"state": "queued", "index": 1})
    write(root / "new" / "a" / "status.json", {"state": "stopped", "index": 0})
    return root


def has_sbatch(monkeypatch, found: bool) -> None:
    where = "/usr/bin/sbatch" if found else None
    monkeypatch.setattr(targets.shutil, "which", lambda name: where)


# --------------------------------------------------------------------------------------
# targets.toml
# --------------------------------------------------------------------------------------
def test_the_repository_targets_file():
    found = targets.settings()
    assert targets.names() == ["local", "taltech"]
    assert found["local"] == {"kind": "local", "label": "This PC"}
    cluster = found["taltech"]
    assert cluster["kind"] == "slurm" and cluster["label"] == "TalTech"
    assert {"host", "repo", "python", "account", "mirror"} <= set(cluster)
    assert [(p["name"], p["max_minutes"]) for p in cluster["partitions"]] == [
        ("short", 240),
        ("common", 11520),
    ]


def test_local_is_there_without_a_file(tmp_path):
    assert targets.settings(tmp_path / "missing.toml") == {"local": {"kind": "local"}}
    assert isinstance(
        targets.get("local", path=tmp_path / "missing.toml"), targets.Target
    )


def test_get_local_and_unknown_target():
    target = targets.get("local")
    assert isinstance(target, targets.LocalTarget) and target.name == "local"
    with pytest.raises(targets.TargetError, match="unknown target 'nope'"):
        targets.get("nope")


def test_get_a_slurm_target_is_direct_on_the_cluster_and_remote_elsewhere(
    monkeypatch, tmp_path
):
    has_sbatch(monkeypatch, True)
    target = targets.get("taltech")
    assert isinstance(target, targets.SlurmTarget) and target.name == "taltech"
    assert target.settings["account"] == "user_kerapo"
    has_sbatch(monkeypatch, False)
    target = targets.get("taltech")
    assert isinstance(target, targets.RemoteTarget) and target.name == "taltech"
    assert isinstance(target.remote, Remote)
    assert (target.remote.host, target.remote.repo) == ("taltech", "~/marlem-slurm")
    assert target.remote.python == "~/miniforge3/envs/marlem/bin/python"
    assert target.remote._thread is None  # getting a target connects to nothing
    assert target.mirror == REPO / "runs" / "@taltech"
    assert targets.get("taltech", root=tmp_path).mirror == tmp_path


def test_bad_targets_files(tmp_path):
    bad_kind = tmp_path / "kind.toml"
    bad_kind.write_text('[x]\nkind = "grid"\n', encoding="utf-8")
    with pytest.raises(targets.TargetError, match="'kind' must be"):
        targets.get("x", path=bad_kind)
    bad_toml = tmp_path / "bad.toml"
    bad_toml.write_text("[x\n", encoding="utf-8")
    with pytest.raises(targets.TargetError, match="not valid TOML"):
        targets.settings(bad_toml)


# --------------------------------------------------------------------------------------
# LocalTarget
# --------------------------------------------------------------------------------------
def test_local_target_is_always_ready():
    report = targets.LocalTarget().check()
    assert list(report) == REPORT_KEYS
    assert report["ok"] is True and report["problems"] == []
    assert targets.LocalTarget().check("anything.json")["ok"] is True


def test_local_target_overview_reads_the_runs_folder(populated):
    target = targets.LocalTarget()
    entries = target.overview()
    assert [e["name"] for e in entries] == ["new", "old"]
    new, old = entries
    assert new["description"] == "hi" and old["description"] == ""
    assert new["summary"]["runs"] == 2
    assert new["summary"]["counts"] == {"queued": 1, "stopped": 1}
    assert new["summary"]["worker_alive"] is False
    assert (populated / "new").stat().st_mtime == new["modified"]
    assert new["spec"] == {"name": "new", "description": "hi"} and old["spec"] is None
    assert all(isinstance(r, RunState) for r in new["runs"])
    assert [(r.name, r.state) for r in new["runs"]] == [
        ("a", "stopped"),
        ("b", "queued"),
    ]


def test_local_target_overview_of_one_experiment_and_runs(populated):
    target = targets.LocalTarget()
    (old,) = target.overview("old")
    assert old["name"] == "old" and old["summary"]["counts"] == {"completed": 1}
    assert [(r.name, r.state) for r in target.runs("new")] == [
        ("a", "stopped"),
        ("b", "queued"),
    ]
    with pytest.raises(FileNotFoundError, match="no experiment 'missing'"):
        target.overview("missing")
    with pytest.raises(FileNotFoundError, match="no experiment 'missing'"):
        target.runs("missing")


def test_local_target_takes_an_explicit_root(populated, tmp_path_factory):
    elsewhere = tmp_path_factory.mktemp("elsewhere")
    assert targets.LocalTarget(elsewhere).overview() == []
    assert targets.LocalTarget(populated).root == populated
    assert targets.get("local", root=populated).overview() != []


def test_local_target_sync_is_the_folder_itself(populated):
    target = targets.LocalTarget()
    assert target.sync("new") == populated / "new"
    assert target.sync("missing") is None
    assert target.copied is None  # nothing is ever copied


def test_local_target_stop_marks_queued_runs(populated):
    target = targets.LocalTarget()
    assert target.stop("new", "b") == {"killed": [], "stopped": ["b"]}
    assert [r.state for r in target.runs("new")] == ["stopped", "stopped"]
    with pytest.raises(FileNotFoundError):
        target.stop("missing")


def test_local_target_start_passes_the_profile(populated, monkeypatch):
    calls = []

    def fake_start(spec_path, root=None, profile="full"):
        calls.append((spec_path, root, profile))
        return Path(root) / "smoke--test"

    monkeypatch.setattr(launch, "start", fake_start)
    target = targets.LocalTarget()
    assert target.start("experiments/smoke.json", "test") == "smoke--test"
    assert calls == [("experiments/smoke.json", populated, "test")]
    target.start("experiments/smoke.json")
    assert calls[-1][2] == "full"


# --------------------------------------------------------------------------------------
# SlurmTarget
# --------------------------------------------------------------------------------------
def test_slurm_target_reads_runs_through_the_slurm_states(root, monkeypatch):
    write(root / "x" / "slurm.json", {"array_id": ARRAY})
    for i, state in enumerate(["queued", "running", "running", "completed"]):
        status = {"state": state, "index": i, "slurm_job": f"{ARRAY}_{i}"}
        write(root / "x" / f"r{i}" / "status.json", status)
    answer = {
        f"{ARRAY}_0": {"state": "PENDING", "node": None},
        f"{ARRAY}_1": {"state": "RUNNING", "node": "n1"},
        f"{ARRAY}_2": {"state": "TIMEOUT", "node": "n1"},
        f"{ARRAY}_3": {"state": "COMPLETED", "node": "n2"},
    }
    seen = []

    def fake_states(exp_dir):
        seen.append(Path(exp_dir))
        return answer

    monkeypatch.setattr(slurm, "states", fake_states)
    target = targets.SlurmTarget("taltech", CLUSTER)
    (entry,) = target.overview()
    assert seen == [root / "x"]  # one sacct for the summary and the runs together
    assert [(r.state, r.slurm_state) for r in entry["runs"]] == [
        ("queued", "PENDING"),
        ("running", "RUNNING"),
        ("lost", "TIMEOUT"),
        ("completed", "COMPLETED"),
    ]
    assert entry["summary"]["counts"] == {
        "queued": 1,
        "running": 1,
        "lost": 1,
        "completed": 1,
    }


def test_slurm_target_start_and_stop_go_through_slurm(root, monkeypatch):
    calls = []

    def fake_start(spec_path, **options):
        calls.append(("start", spec_path, options))
        return root / "smoke--test"

    def fake_stop(experiment, run=None, root=None):
        calls.append(("stop", experiment, run, root))
        return {"cancelled": [ARRAY], "stopped": ["a"]}

    has_sbatch(monkeypatch, True)
    monkeypatch.setattr(slurm, "start", fake_start)
    monkeypatch.setattr(slurm, "stop", fake_stop)
    target = targets.SlurmTarget("taltech", CLUSTER)
    assert target.start("experiments/smoke.json", "test") == "smoke--test"
    assert calls[0] == (
        "start",
        "experiments/smoke.json",
        {
            "account": "acc",
            "partitions": CLUSTER["partitions"],
            "root": root,
            "profile": "test",
        },
    )
    assert target.stop("smoke--test", "a") == {"cancelled": [ARRAY], "stopped": ["a"]}
    assert calls[1] == ("stop", "smoke--test", "a", root)
    with pytest.raises(targets.TargetError, match="no 'account'"):
        targets.SlurmTarget("t", {"kind": "slurm"}).start("x.json")


def test_slurm_target_check_is_ready_with_sbatch_and_submitit(root, monkeypatch):
    has_sbatch(monkeypatch, True)
    write(root / "busy" / "a" / "status.json", {"state": "queued"})
    write(root / "done" / "a" / "status.json", {"state": "completed"})
    report = targets.SlurmTarget("taltech", CLUSTER).check()
    assert list(report) == REPORT_KEYS
    assert report["target"] == "taltech"
    assert (report["ok"], report["problems"]) == (True, [])
    commit = report["local_commit"]
    assert commit is None or len(commit) == 40
    assert report["cluster_commit"] == commit  # this checkout is the cluster's
    assert report["active"] == ["busy"]  # the experiments not to update the code for
    json.dumps(report)


def test_slurm_target_check_lists_what_is_missing(root, monkeypatch):
    has_sbatch(monkeypatch, False)

    def no_submitit(name):
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(targets.importlib.metadata, "version", no_submitit)
    report = targets.SlurmTarget("taltech", CLUSTER).check()
    assert report["ok"] is False and report["active"] == []
    assert len(report["problems"]) == 2
    assert "sbatch" in report["problems"][0] and "submitit" in report["problems"][1]


def test_slurm_target_start_refuses_with_the_problems(root, monkeypatch):
    has_sbatch(monkeypatch, False)
    started = []
    monkeypatch.setattr(slurm, "start", lambda *a, **k: started.append(a))
    target = targets.SlurmTarget("taltech", CLUSTER)
    with pytest.raises(targets.TargetError, match="cannot start on taltech: sbatch"):
        target.start("experiments/smoke.json")
    assert started == []


# --------------------------------------------------------------------------------------
# RemoteTarget: the cluster seen from this machine, against a fake connection
# --------------------------------------------------------------------------------------
COMMIT = "0123456789abcdef0123456789abcdef01234567"
RUN_JSON = {"name": "a", "state": "running", "progress": 0.5, "env_steps": 10}
SSH_SETTINGS = {"kind": "slurm", "host": "h", "repo": "~/r", "python": "py"}
REMOTE_SETTINGS = SSH_SETTINGS | {"mirror": "runs/@h"}
CLUSTER_OK = {"target": "taltech", "ok": True, "problems": [], "active": []}


class FakeRemote:
    """What ``RemoteTarget`` calls on a ``Remote``, answered from ``answers`` (the
    runner's first argument -> a dict, or an exception to raise); every call is
    recorded in ``calls``. ``head`` and ``dirty`` may be exceptions too."""

    def __init__(self, answers=None, head=COMMIT, dirty=False):
        self.answers = {"check": CLUSTER_OK} | (answers or {})
        self.head_answer, self.dirty_answer = head, dirty
        self.calls: list[tuple] = []
        self.accepted: list = []
        self.pulled: list = []
        self.pull_result: int | Exception = 2
        self.closed = False

    def runner(self, *args, accept=(0,)):
        self.calls.append(args)
        self.accepted.append(accept)
        answer = self.answers[args[0]]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def head(self):
        if isinstance(self.head_answer, Exception):
            raise self.head_answer
        return self.head_answer

    def uncommitted(self):
        if isinstance(self.dirty_answer, Exception):
            raise self.dirty_answer
        return self.dirty_answer

    def pull(self, remote_dir, local_dir, skip=()):
        self.pulled.append((remote_dir, local_dir))
        if isinstance(self.pull_result, Exception):
            raise self.pull_result
        return self.pull_result

    def close(self):
        self.closed = True


def remote_target(tmp_path, **options) -> tuple[targets.RemoteTarget, FakeRemote]:
    fake = FakeRemote(**options)
    return (
        targets.RemoteTarget("taltech", REMOTE_SETTINGS, fake, tmp_path / "mirror"),
        fake,
    )


def git(root: Path, *args: str) -> str:
    options = [
        "-c",
        "user.name=t",
        "-c",
        "user.email=t@t",
        "-c",
        "commit.gpgsign=false",
    ]
    done = subprocess.run(
        ["git", "-C", str(root), *options, *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch) -> Path:
    """A small git repository standing in for the project: a committed spec with its
    scenario. ``targets.REPO`` points at it."""
    root = tmp_path / "repo"
    write(root / "scenarios" / "s.json", {"s": 1})
    spec = {
        "scenario": "scenarios/s.json",
        "algorithms": ["ppo"],
        "paradigms": ["dtde"],
        "seeds": [0],
        "budget": 100,
    }
    write(root / "experiments" / "x.json", spec)
    git(root, "init")
    git(root, "add", "-A")
    git(root, "commit", "-m", "start")
    monkeypatch.setattr(targets, "REPO", root)
    return root


def spec_of(root: Path) -> dict:
    """The committed spec, to write another file with the same content."""
    return json.loads((root / "experiments" / "x.json").read_text(encoding="utf-8"))


def head_of(root: Path) -> str:
    return git(root, "rev-parse", "HEAD")


def test_remote_target_needs_its_settings(tmp_path):
    with pytest.raises(targets.TargetError, match="no 'mirror'"):
        targets.RemoteTarget("t", SSH_SETTINGS, FakeRemote())
    with pytest.raises(targets.TargetError, match="no 'host'"):
        targets.RemoteTarget("t", {"mirror": "m"})
    default = targets.RemoteTarget("t", REMOTE_SETTINGS, FakeRemote())
    assert default.mirror == REPO / "runs" / "@h"


# --- check ------------------------------------------------------------------------------
def test_remote_check_is_ready_when_everything_agrees(tmp_path, repo):
    target, fake = remote_target(tmp_path, head=head_of(repo))
    fake.answers["check"] = CLUSTER_OK | {"active": ["old"]}
    report = target.check()
    assert list(report) == REPORT_KEYS
    assert (report["ok"], report["problems"]) == (True, [])
    assert report["local_commit"] == report["cluster_commit"] == head_of(repo)
    assert report["active"] == ["old"]  # the cluster's answer
    assert fake.calls == [("check", "--target", "taltech")]
    assert fake.accepted == [(0, 1)]  # a cluster that is not ready still answers
    json.dumps(report)


def test_remote_check_reports_different_commits(tmp_path, repo):
    target, _ = remote_target(tmp_path, head="f" * 40)
    report = target.check()
    assert report["ok"] is False
    (problem,) = report["problems"]
    assert "ffffffff" in problem and head_of(repo)[:8] in problem
    assert 'git shipc "message"' in problem
    assert (report["local_commit"], report["cluster_commit"]) == (
        head_of(repo),
        "f" * 40,
    )


def test_remote_check_reports_a_cluster_checkout_with_changes(tmp_path, repo):
    target, _ = remote_target(tmp_path, head=head_of(repo), dirty=True)
    report = target.check()
    assert report["ok"] is False
    (problem,) = report["problems"]
    assert "uncommitted changes" in problem and "cluster" in problem


def test_remote_check_passes_on_the_clusters_own_problems(tmp_path, repo):
    target, fake = remote_target(tmp_path, head=head_of(repo))
    fake.answers["check"] = CLUSTER_OK | {"ok": False, "problems": ["sbatch not found"]}
    report = target.check()
    assert report["ok"] is False
    assert report["problems"] == ["on the cluster: sbatch not found"]


def test_remote_check_never_raises_for_a_connection_problem(tmp_path, repo):
    down = RemoteError("runner check failed on taltech: timed out (is the VPN on?)")
    target, fake = remote_target(tmp_path, answers={"check": down})
    report = target.check()
    assert report["ok"] is False and report["problems"] == [str(down)]
    assert report["local_commit"] == head_of(repo)
    assert (report["cluster_commit"], report["active"]) == (None, None)
    fake.answers["check"] = CLUSTER_OK  # reachable, but git there fails
    fake.head_answer = RemoteError("git rev-parse failed on taltech: exit status 128")
    report = target.check()
    assert report["ok"] is False and "git rev-parse failed" in report["problems"][0]
    fake.head_answer, fake.dirty_answer = COMMIT, RemoteError("connection lost")
    assert target.check()["problems"] == ["connection lost"]


def test_remote_check_with_a_committed_spec_is_ready(tmp_path, repo):
    target, _ = remote_target(tmp_path, head=head_of(repo))
    assert target.check("experiments/x.json")["problems"] == []
    assert target.check(repo / "experiments" / "x.json")["ok"] is True  # absolute


def test_remote_check_reports_an_untracked_or_modified_spec(tmp_path, repo):
    target, _ = remote_target(tmp_path, head=head_of(repo))
    write(repo / "experiments" / "new.json", spec_of(repo))
    (problem,) = target.check("experiments/new.json")["problems"]
    assert "experiments/new.json is not tracked" in problem
    path = repo / "experiments" / "x.json"
    path.write_text(path.read_text(encoding="utf-8") + "\n\n", encoding="utf-8")
    (problem,) = target.check("experiments/x.json")["problems"]
    assert "experiments/x.json has uncommitted changes" in problem


def test_remote_check_reports_a_modified_or_untracked_scenario(tmp_path, repo):
    target, _ = remote_target(tmp_path, head=head_of(repo))
    write(repo / "scenarios" / "s.json", {"s": 2})
    (problem,) = target.check("experiments/x.json")["problems"]
    assert "scenarios/s.json has uncommitted changes" in problem
    git(repo, "rm", "--cached", "-q", "scenarios/s.json")
    (problem,) = target.check("experiments/x.json")["problems"]
    assert "scenarios/s.json is not tracked" in problem


def test_remote_check_reports_a_spec_outside_the_repository_or_invalid(tmp_path, repo):
    target, _ = remote_target(tmp_path, head=head_of(repo))
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    (problem,) = target.check(other)["problems"]
    assert "not inside the repository" in problem
    (repo / "experiments" / "bad.json").write_text('{"budget": 1}', encoding="utf-8")
    (problem,) = target.check("experiments/bad.json")["problems"]
    assert problem.startswith("experiments/bad.json: missing field")


def test_remote_check_collects_every_problem(tmp_path, repo):
    target, _ = remote_target(tmp_path, head="f" * 40, dirty=True)
    write(repo / "scenarios" / "s.json", {"s": 2})
    assert len(target.check("experiments/x.json")["problems"]) == 3


def test_allow_uncommitted_drops_the_commit_problems_only(tmp_path, repo):
    target, fake = remote_target(tmp_path, head="f" * 40, dirty=True)
    write(repo / "experiments" / "wip.json", spec_of(repo))  # untracked
    report = target.check("experiments/wip.json", allow_uncommitted=True)
    assert report["ok"] is True and report["problems"] == []
    assert report["cluster_commit"] == "f" * 40  # still reported
    fake.answers["check"] = CLUSTER_OK | {"problems": ["sbatch not found"]}
    assert target.check(allow_uncommitted=True)["ok"] is False
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    assert target.check(other, allow_uncommitted=True)["ok"] is False


# --- start ------------------------------------------------------------------------------
def test_remote_start_checks_then_sends_the_spec(tmp_path, repo):
    target, fake = remote_target(tmp_path, head=head_of(repo))
    fake.answers["start"] = {"experiment": "x--test", "folder": "/cluster/runs/x--test"}
    assert target.start("experiments/x.json", "test") == "x--test"
    assert fake.calls == [
        ("check", "--target", "taltech"),
        ("start", "experiments/x.json", "--target", "taltech", "--profile", "test"),
    ]
    assert target.start(repo / "experiments" / "x.json") == "x--test"  # absolute
    assert fake.calls[-1][-1] == "full"


def test_remote_start_refuses_with_the_problems_of_the_check(tmp_path, repo):
    target, fake = remote_target(tmp_path, head="f" * 40, dirty=True)
    with pytest.raises(targets.TargetError) as error:
        target.start("experiments/x.json")
    message = str(error.value)
    assert message.startswith("cannot start on taltech: ")
    assert "ffffffff" in message and "uncommitted changes" in message
    assert 'git shipc "message"' in message and "; " in message
    assert fake.calls == [("check", "--target", "taltech")]  # nothing was started


def test_remote_start_refuses_an_untracked_spec_and_one_outside(tmp_path, repo):
    target, fake = remote_target(tmp_path, head=head_of(repo))
    write(repo / "experiments" / "new.json", spec_of(repo))
    with pytest.raises(targets.TargetError, match="new.json is not tracked"):
        target.start("experiments/new.json")
    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    with pytest.raises(targets.TargetError, match="not inside the repository"):
        target.start(other, allow_uncommitted=True)  # not even for development
    assert not [call for call in fake.calls if call[0] == "start"]


def test_remote_start_when_the_cluster_is_unreachable(tmp_path, repo):
    down = RemoteError("runner check failed on taltech: no route (is the VPN on?)")
    target, fake = remote_target(tmp_path, answers={"check": down})
    with pytest.raises(targets.TargetError, match=r"cannot start on taltech.*VPN"):
        target.start("experiments/x.json")


def test_allow_uncommitted_starts_what_the_check_would_refuse(tmp_path, repo):
    target, fake = remote_target(tmp_path, head="f" * 40, dirty=True)
    fake.answers["start"] = {"experiment": "x"}
    write(repo / "experiments" / "wip.json", spec_of(repo))  # untracked
    assert target.start("experiments/wip.json", allow_uncommitted=True) == "x"
    assert fake.calls[-1][:2] == ("start", "experiments/wip.json")


def test_remote_errors_come_out_of_start_unchanged(tmp_path, repo):
    target, fake = remote_target(tmp_path, head=head_of(repo))
    fake.answers["start"] = RemoteError("the spec of 'x' changed: use a new name")
    with pytest.raises(RemoteError, match="the spec of 'x' changed"):
        target.start("experiments/x.json")


# --- reading ----------------------------------------------------------------------------
ENTRY = {
    "name": "x",
    "description": "d",
    "modified": 2.0,
    "spec": {"name": "x", "description": "d"},
    "summary": {
        "runs": 3,
        "counts": {"running": 1},
        "progress": 0.5,
        "worker_alive": False,
    },
    "runs": [
        RUN_JSON | {"future_field": 1},  # a key this version does not know
        RUN_JSON | {"name": "b", "state": "queued"},
        {"name": "c", "state": "completed", "slurm_state": "COMPLETED", "host": "n1"},
    ],
}


def test_remote_overview_is_one_call_with_the_runs_as_run_states(tmp_path):
    target, fake = remote_target(tmp_path)
    fake.answers["status"] = {"target": "taltech", "experiments": [ENTRY]}
    (found,) = target.overview()
    assert fake.calls == [("status", "--target", "taltech")]
    assert found["name"] == "x" and found["spec"] == ENTRY["spec"]
    assert found["summary"]["runs"] == 3 and found["modified"] == 2.0
    assert all(isinstance(r, RunState) for r in found["runs"])
    assert [(r.name, r.state) for r in found["runs"]] == [
        ("a", "running"),
        ("b", "queued"),
        ("c", "completed"),
    ]
    assert (found["runs"][0].progress, found["runs"][0].env_steps) == (0.5, 10)
    assert (found["runs"][2].slurm_state, found["runs"][2].host) == ("COMPLETED", "n1")


def test_remote_overview_of_one_experiment_and_runs(tmp_path):
    target, fake = remote_target(tmp_path)
    fake.answers["status"] = {"target": "taltech", "experiment": "x"} | ENTRY
    (found,) = target.overview("x")
    assert found["name"] == "x" and len(found["runs"]) == 3
    assert [r.name for r in target.runs("x")] == ["a", "b", "c"]
    assert fake.calls == [("status", "x", "--target", "taltech")] * 2
    fake.answers["status"] = RemoteError("no experiment 'y' in runs")
    with pytest.raises(RemoteError, match="no experiment 'y'"):
        target.runs("y")


def test_remote_stop_passes_the_names_and_returns_what_was_stopped(tmp_path):
    target, fake = remote_target(tmp_path)
    fake.answers["stop"] = {
        "cancelled": ["7"],
        "stopped": ["a"],
        "target": "taltech",
        "experiment": "x",
    }
    assert target.stop("x", "a") == {"cancelled": ["7"], "stopped": ["a"]}
    assert target.stop("x") == {"cancelled": ["7"], "stopped": ["a"]}
    assert fake.calls == [
        ("stop", "x", "a", "--target", "taltech"),
        ("stop", "x", "--target", "taltech"),
    ]


# --- sync -------------------------------------------------------------------------------
def test_remote_sync_pulls_into_the_mirror_and_local_runs_reads_it(tmp_path):
    target, fake = remote_target(tmp_path)
    assert target.copied is None
    folder = target.sync("x")
    assert folder == tmp_path / "mirror" / "x"
    assert fake.pulled == [("runs/x", tmp_path / "mirror" / "x")]
    assert target.copied == 2
    for name in ("../x", "", ".hidden", "a/b", "a\\b"):
        with pytest.raises(targets.TargetError, match="not an experiment name"):
            target.sync(name)
    write(folder / "r1" / "status.json", {"state": "completed", "index": 0})
    write(folder / "r1" / "budget.json", {})
    assert [(r.name, r.state) for r in target.local_runs("x")] == [("r1", "completed")]
    assert target.local_runs("other") == []


def test_a_failed_sync_raises_and_keeps_the_last_count(tmp_path):
    target, fake = remote_target(tmp_path)
    target.sync("x")
    fake.pull_result = RemoteError("copying runs/x failed on taltech: gone")
    with pytest.raises(RemoteError, match="copying runs/x failed"):
        target.sync("x")
    assert target.copied == 2


def test_closing_a_remote_target_closes_its_connection(tmp_path):
    target, fake = remote_target(tmp_path)
    target.close()
    assert fake.closed


# --------------------------------------------------------------------------------------
# The command line
# --------------------------------------------------------------------------------------
def run_cli(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_status_json_lists_the_experiments_with_their_runs(populated, capsys):
    code, out, err = run_cli(capsys, "status", "--json")
    assert code == 0 and err == ""
    data = json.loads(out)  # nothing else on stdout
    assert data["target"] == "local"
    new, old = data["experiments"]
    assert (new["name"], old["name"]) == ("new", "old")
    assert new["summary"]["counts"] == {"queued": 1, "stopped": 1}
    assert new["description"] == "hi" and old["spec"] is None
    assert new["spec"] == {"name": "new", "description": "hi"}
    assert [r["name"] for r in new["runs"]] == ["a", "b"]
    assert RunState(**new["runs"][1]).state == "queued"  # every field, nothing else


def test_status_json_of_one_experiment(populated, capsys):
    write(
        populated / "new" / "a" / "status.json",
        {"state": "stopped", "index": 0, "host": "pc"},
    )
    code, out, _ = run_cli(capsys, "status", "new", "--json")
    assert code == 0
    data = json.loads(out)
    assert {"target", "experiment", "spec", "summary", "runs"} <= set(data)
    assert data["experiment"] == "new" and data["spec"]["description"] == "hi"
    assert data["summary"]["runs"] == 2 and data["description"] == "hi"
    assert [r["name"] for r in data["runs"]] == ["a", "b"]
    first = data["runs"][0]
    assert (first["state"], first["host"], first["slurm_state"]) == (
        "stopped",
        "pc",
        None,
    )
    assert RunState(**first).name == "a"


def test_status_without_json_is_the_table(populated, capsys):
    code, out, _ = run_cli(capsys, "status")
    assert code == 0
    assert out.startswith("new") and "2 runs" in out and "1 queued, 1 stopped" in out
    code, out, _ = run_cli(capsys, "status", "new")
    header, *rows = out.splitlines()
    assert header.split()[:3] == ["run", "state", "progress"]
    assert [r.split()[:2] for r in rows] == [["a", "stopped"], ["b", "queued"]]
    write(populated / "empty" / "x.txt", {})
    code, out, _ = run_cli(capsys, "status", "empty")
    assert code == 0 and "no runs in 'empty'" in out


def test_status_table_shows_slurm_and_host_columns_only_when_present(root, capsys):
    write(root / "x" / "a" / "status.json", {"state": "queued", "index": 0})
    _, out, _ = run_cli(capsys, "status", "x")
    assert out.splitlines()[0].split()[:3] == ["run", "state", "progress"]
    write(root / "x" / "a" / "status.json", {"state": "completed", "host": "node7"})
    _, out, _ = run_cli(capsys, "status", "x")
    assert out.splitlines()[0].split()[:4] == ["run", "state", "host", "progress"]
    assert "slurm" not in out.splitlines()[0]


def test_status_table_with_slurm_states(root, capsys, monkeypatch):
    write(root / "x" / "slurm.json", {"array_id": ARRAY})
    write(
        root / "x" / "a" / "status.json",
        {"state": "running", "slurm_job": f"{ARRAY}_0", "host": "node7"},
    )
    answer = {f"{ARRAY}_0": {"state": "RUNNING", "node": "node7"}}
    monkeypatch.setattr(slurm, "states", lambda exp_dir: answer)
    has_sbatch(monkeypatch, True)
    code, out, _ = run_cli(capsys, "status", "x", "--target", "taltech")
    header, row = out.splitlines()
    assert header.split()[:5] == ["run", "state", "slurm", "host", "progress"]
    assert row.split()[:4] == ["a", "running", "RUNNING", "node7"]
    code, out, _ = run_cli(capsys, "status", "x", "--target", "taltech", "--json")
    (run,) = json.loads(out)["runs"]
    assert (run["state"], run["slurm_state"], run["host"]) == (
        "running",
        "RUNNING",
        "node7",
    )


def test_errors_exit_2_as_text_or_as_json(populated, capsys, monkeypatch, tmp_path):
    code, out, err = run_cli(capsys, "status", "--target", "nope")
    assert (code, out) == (2, "") and err.startswith("error: unknown target 'nope'")
    code, out, err = run_cli(capsys, "status", "--target", "nope", "--json")
    assert (code, err) == (2, "")
    assert "unknown target" in json.loads(out)["error"]  # the only thing on stdout
    code, out, err = run_cli(capsys, "status", "missing")
    assert (code, out) == (2, "") and err.startswith("error: no experiment 'missing'")
    code, out, err = run_cli(capsys, "status", "missing", "--json")
    assert (code, err) == (2, "") and list(json.loads(out)) == ["error"]
    code, out, err = run_cli(capsys, "stop", "missing")
    assert code == 2 and err.startswith("error: no experiment 'missing'")
    has_sbatch(monkeypatch, False)
    elsewhere = tmp_path / "targets.toml"
    elsewhere.write_text('[x]\nkind = "slurm"\nhost = "h"\n', encoding="utf-8")
    monkeypatch.setattr(targets, "TARGETS_FILE", elsewhere)
    code, out, err = run_cli(capsys, "check", "--target", "x", "--json")
    assert (code, err) == (2, "") and "has no 'mirror'" in json.loads(out)["error"]


def test_a_refused_start_is_an_error_on_stdout_with_json(root, capsys, monkeypatch):
    has_sbatch(monkeypatch, True)

    def not_ready(self, spec_path=None, allow_uncommitted=False):
        return targets._report(self.name, ["sbatch not found"])

    monkeypatch.setattr(targets.SlurmTarget, "check", not_ready)
    code, out, err = run_cli(capsys, "start", "x.json", "--json", "--target", "taltech")
    assert (code, err) == (2, "")
    assert json.loads(out) == {"error": "cannot start on taltech: sbatch not found"}
    code, out, err = run_cli(capsys, "start", "x.json", "--target", "taltech")
    assert (code, out) == (2, "")
    assert err.strip() == "error: cannot start on taltech: sbatch not found"


def test_stop_command(populated, capsys):
    code, out, _ = run_cli(capsys, "stop", "new", "b")
    assert code == 0 and out.strip() == "killed [], marked stopped ['b']"


def test_stop_on_slurm_says_cancelled(root, capsys, monkeypatch):
    write(root / "x" / "a" / "status.json", {"state": "queued"})
    monkeypatch.setattr(
        slurm, "stop", lambda *a: {"cancelled": ["7"], "stopped": ["a"]}
    )
    has_sbatch(monkeypatch, True)
    code, out, _ = run_cli(capsys, "stop", "x", "--target", "taltech")
    assert code == 0 and out.strip() == "cancelled ['7'], marked stopped ['a']"


def test_check_prints_the_report_and_exits_0_when_ready(capsys):
    code, out, _ = run_cli(capsys, "check")
    assert (code, out.strip()) == (0, "local: ready")
    code, out, _ = run_cli(capsys, "check", "--json")
    assert (code, json.loads(out)) == (0, targets.LocalTarget().check())


def test_check_exits_1_with_the_problems_when_not_ready(capsys, monkeypatch):
    has_sbatch(monkeypatch, True)
    report = targets._report(
        "taltech",
        ["the cluster is at commit aaaaaaaa but this machine at bbbbbbbb"],
        local_commit="b" * 40,
        cluster_commit="a" * 40,
        active=["old", "older"],
    )
    seen = []

    def fake_check(self, spec_path=None, allow_uncommitted=False):
        seen.append(spec_path)
        return report

    monkeypatch.setattr(targets.SlurmTarget, "check", fake_check)
    code, out, _ = run_cli(capsys, "check", "experiments/x.json", "--target", "taltech")
    assert code == 1 and seen == ["experiments/x.json"]
    lines = out.splitlines()
    assert lines[0] == "taltech: NOT ready"
    assert lines[1].startswith("  problem: the cluster is at commit aaaaaaaa")
    assert "commit on this machine: bbbbbbbb" in out and "on cluster: aaaaaaaa" in out
    assert "queued or running: old, older" in out
    code, out, _ = run_cli(capsys, "check", "--target", "taltech", "--json")
    assert (code, json.loads(out)) == (1, report) and seen[-1] is None


def test_start_goes_to_the_target_with_the_profile(populated, capsys, monkeypatch):
    calls = []

    def fake_start(self, spec_path, profile="full", allow_uncommitted=False):
        calls.append((self.name, spec_path, profile))
        return "smoke--test" if profile == "test" else "smoke"

    monkeypatch.setattr(targets.LocalTarget, "start", fake_start)
    code, out, _ = run_cli(
        capsys, "start", "experiments/smoke.json", "--profile", "test"
    )
    assert code == 0 and calls == [("local", "experiments/smoke.json", "test")]
    assert out.splitlines()[0] == "started smoke--test on local"
    assert (
        out.splitlines()[-1] == "watch with: python -m core.runner status smoke--test"
    )
    run_cli(capsys, "start", "experiments/smoke.json")
    assert calls[-1][2] == "full"
    with pytest.raises(SystemExit):  # argparse: not a profile
        main(["start", "experiments/smoke.json", "--profile", "tiny"])


def test_status_json_is_the_only_output_of_a_real_process(populated):
    done = subprocess.run(
        [sys.executable, "-m", "core.runner", "status", "new", "--json"],
        cwd=REPO,
        env=os.environ | {"MARLEM_RUNS": str(populated)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout)["summary"]["runs"] == 2
    done = subprocess.run(
        [sys.executable, "-m", "core.runner", "status", "nope", "--json"],
        cwd=REPO,
        env=os.environ | {"MARLEM_RUNS": str(populated)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 2 and done.stderr == ""
    assert "no experiment 'nope'" in json.loads(done.stdout)["error"]


def test_start_stop_and_sync_json_are_the_only_output(populated, capsys, monkeypatch):
    monkeypatch.setattr(targets.LocalTarget, "_start", lambda *a: "smoke--test")
    code, out, err = run_cli(capsys, "start", "x.json", "--json")
    assert (code, err) == (0, "")
    assert json.loads(out) == {
        "target": "local",
        "experiment": "smoke--test",
        "folder": str(populated / "smoke--test"),
    }
    code, out, err = run_cli(capsys, "stop", "new", "b", "--json")
    assert (code, err) == (0, "")
    assert json.loads(out) == {
        "killed": [],
        "stopped": ["b"],
        "target": "local",
        "experiment": "new",
    }
    code, out, _ = run_cli(capsys, "sync", "new", "--json")
    assert code == 0 and json.loads(out) == {
        "target": "local",
        "experiment": "new",
        "folder": str(populated / "new"),
        "copied": None,  # nothing is copied: the files are here
    }
    code, out, _ = run_cli(capsys, "sync", "new")
    assert (code, out.strip()) == (0, str(populated / "new"))
    code, out, _ = run_cli(capsys, "sync", "missing")
    assert code == 0 and "no results of 'missing'" in out
    code, out, err = run_cli(capsys, "stop", "missing", "--json")
    assert code == 2 and "no experiment" in json.loads(out)["error"] and err == ""


# --------------------------------------------------------------------------------------
# The command line with a RemoteTarget
# --------------------------------------------------------------------------------------
@pytest.fixture()
def remote_cli(tmp_path, monkeypatch):
    """``taltech`` is a RemoteTarget over a fake connection."""
    target, fake = remote_target(tmp_path, head=COMMIT)
    monkeypatch.setattr(targets, "get", lambda name="local", **kw: target)
    return target, fake


def test_cli_start_through_a_remote_target(remote_cli, tmp_path, capsys, monkeypatch):
    target, fake = remote_cli
    monkeypatch.setattr(targets.RemoteTarget, "_start", lambda self, spec, profile: "s")
    monkeypatch.setattr(
        targets.RemoteTarget, "_check_spec", staticmethod(lambda spec: ([], []))
    )
    monkeypatch.setattr(
        targets, "_git", lambda *args: COMMIT if args[0] == "rev-parse" else ""
    )
    code, out, _ = run_cli(
        capsys, "start", "experiments/smoke.json", "--target", "taltech"
    )
    assert code == 0
    assert out.splitlines()[0] == "started s on taltech"
    assert "watch with: python -m core.runner status s --target taltech" in out
    assert out.splitlines()[-1].startswith("fetch results with:")
    assert "results in" not in out  # they are on the cluster until synced
    code, out, _ = run_cli(capsys, "start", "x.json", "--target", "taltech", "--json")
    assert json.loads(out) == {
        "target": "taltech",
        "experiment": "s",
        "folder": str(tmp_path / "mirror" / "s"),
    }
    assert fake.closed  # the command closed the connection


def test_cli_sync_through_a_remote_target(remote_cli, tmp_path, capsys):
    target, fake = remote_cli
    code, out, _ = run_cli(capsys, "sync", "x", "--target", "taltech")
    assert code == 0
    assert out.splitlines() == [str(tmp_path / "mirror" / "x"), "copied 2 file(s)"]
    code, out, _ = run_cli(capsys, "sync", "x", "--target", "taltech", "--json")
    assert json.loads(out) == {
        "target": "taltech",
        "experiment": "x",
        "folder": str(tmp_path / "mirror" / "x"),
        "copied": 2,
    }
    assert fake.pulled[-1] == ("runs/x", tmp_path / "mirror" / "x")


def test_cli_check_through_a_remote_target(remote_cli, capsys, monkeypatch):
    target, fake = remote_cli
    monkeypatch.setattr(
        targets, "_git", lambda *args: COMMIT if args[0] == "rev-parse" else ""
    )
    code, out, _ = run_cli(capsys, "check", "--target", "taltech", "--json")
    assert code == 0 and json.loads(out)["ok"] is True
    fake.answers["check"] = CLUSTER_OK | {"ok": False, "problems": ["no sbatch"]}
    code, out, _ = run_cli(capsys, "check", "--target", "taltech")
    assert (
        code == 1 and "taltech: NOT ready" in out and "on the cluster: no sbatch" in out
    )
    fake.answers["check"] = RemoteError("runner check failed on taltech: no route")
    code, out, err = run_cli(capsys, "check", "--target", "taltech", "--json")
    assert (code, err) == (1, "")  # a report, not an error
    assert json.loads(out)["problems"] == ["runner check failed on taltech: no route"]


def test_cli_status_stop_and_errors_through_a_remote_target(remote_cli, capsys):
    target, fake = remote_cli
    fake.answers["stop"] = {"cancelled": ["7"], "stopped": ["a"], "target": "taltech"}
    code, out, _ = run_cli(capsys, "stop", "x", "a", "--target", "taltech")
    assert code == 0 and out.strip() == "cancelled ['7'], marked stopped ['a']"
    fake.answers["status"] = {"target": "taltech", "experiments": [ENTRY]}
    code, out, _ = run_cli(capsys, "status", "--target", "taltech")
    assert code == 0 and out.startswith("x ") and "3 runs" in out
    fake.answers["status"] = RemoteError("cannot reach taltech")
    code, out, err = run_cli(capsys, "status", "--target", "taltech")
    assert (code, out) == (2, "") and err.strip() == "error: cannot reach taltech"
    code, out, err = run_cli(capsys, "status", "--target", "taltech", "--json")
    assert (code, err) == (2, "") and json.loads(out) == {
        "error": "cannot reach taltech"
    }
