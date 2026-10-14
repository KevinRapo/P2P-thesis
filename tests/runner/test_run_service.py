"""The Studio's RunService (``studio/adapters/run_service.py``) over a temporary
``runs/`` that ``$MARLEM_RUNS`` points at: it lists the experiments newest first and
returns the registry's records as they are. No training, no browser.

Run with ``python -m pytest tests/runner -q`` in the ``marlem`` conda env.
"""

from __future__ import annotations

import json
import os

import pytest

from core.runner.registry import RunState
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


def test_lists_experiments_newest_first_with_their_runs(runs_root):
    old = runs_root / "old"
    new = runs_root / "new"
    make_run(old, "a", state="completed", budget=100, index=0)
    make_run(new, "b", state="queued", budget=100, index=1)
    make_run(new, "a", state="stopped", budget=100, index=0)
    os.utime(old, (1_000_000, 1_000_000))  # older than `new`
    (new / "experiment.json").write_text('{"description": "hi"}', encoding="utf-8")

    service = RunService()
    assert service.experiments() == ["new", "old"]
    runs = service.runs("new")
    assert all(isinstance(r, RunState) for r in runs)
    assert [(r.name, r.state) for r in runs] == [("a", "stopped"), ("b", "queued")]
    assert service.spec("new") == {"description": "hi"}
    assert service.spec("old") is None
    assert service.worker_alive("new") is False


def test_stop_marks_queued_runs_stopped(runs_root):
    exp = runs_root / "x"
    make_run(exp, "a", state="queued", budget=100, index=0)
    make_run(exp, "b", state="queued", budget=100, index=1)

    service = RunService()
    assert service.stop("x", "a") == {"killed": [], "stopped": ["a"]}
    assert [r.state for r in service.runs("x")] == ["stopped", "queued"]
    assert service.stop("x")["stopped"] == ["b"]
    assert {r.state for r in service.runs("x")} == {"stopped"}
    with pytest.raises(FileNotFoundError):
        service.stop("missing")
