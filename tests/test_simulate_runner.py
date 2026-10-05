"""A simulate run through the worker: a replayable run folder, no Ray."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src_thesis.platform.kernel.models import expand, files, resolve
from src_thesis.platform.kernel.models.manifest import build_manifest
from src_thesis.platform.kernel.models.records import (
    ExperimentFile,
    RunCell,
    RunState,
)
from src_thesis.platform.kernel.store.filesystem import ExperimentStore
from src_thesis.platform.kernel.worker import process as worker

PRESET = (
    Path(__file__).resolve().parents[1]
    / "src_thesis/platform/kernel/presets/case6-3x3.marlem.json"
)
REPO = Path(__file__).resolve().parents[1]


def new_run(store: ExperimentStore, cell: RunCell) -> str:
    file = ExperimentFile.model_validate(json.loads(PRESET.read_text("utf-8")))
    resolved = resolve.resolve_run(file, cell)
    run_id = expand.run_id(file.meta.id, cell, files.canonical_hash(file))
    store.create_run(file, resolved, build_manifest(file, resolved, cell, run_id))
    return run_id


def cell(controller: str = "net_position", **extra) -> RunCell:
    return RunCell(kind="simulate", algorithm=controller, paradigm="-", seed=1, **extra)


@pytest.fixture(scope="module")
def finished(tmp_path_factory):
    store = ExperimentStore(tmp_path_factory.mktemp("store"))
    run_id = new_run(store, cell(day="2016-06-15"))
    return store, run_id, worker.run_one(store.run_dir(run_id))


def test_a_simulate_run_completes_and_is_replayable(finished) -> None:
    store, run_id, state = finished
    assert state == RunState.COMPLETED, store.log_tail(run_id)
    steps = list(store.read_jsonl(run_id, "raw/steps.jsonl"))
    assert [s["step"] for s in steps] == list(range(24))
    assert {s["day"] for s in steps} == {"2016-06-15"}
    assert steps[12]["assessment"]["converged"] and steps[12]["kpis"]["fit"] > 0
    topology = json.loads((store.run_dir(run_id) / "grid_topology.json").read_text())
    assert topology["topology"]["buses"] and topology["participants"]
    assert "grid_topology" in store.read_artifacts(run_id).files


def test_checks_and_summary_are_written_per_day(finished) -> None:
    store, run_id, _ = finished
    (checks,) = store.read_jsonl(run_id, "metrics/checks.jsonl")
    assert {c["id"] for c in checks["checks"]} >= {"trade_integrity", "soc_limits"}
    (summary,) = store.read_jsonl(run_id, "metrics/summary.jsonl")
    assert summary["steps_played"] == 24 and summary["failed_invariants"] == 0
    assert store.read_status(run_id).progress == 1.0


def test_two_days_and_a_cancel(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    run_id = new_run(store, cell("no_order", days=2, day="2016-06-15"))
    assert worker.run_one(store.run_dir(run_id)) == RunState.COMPLETED
    days = [s["day"] for s in store.read_jsonl(run_id, "raw/steps.jsonl")]
    assert days == ["2016-06-15"] * 24 + ["2016-06-16"] * 24
    cancelled = new_run(store, cell("random", day="2016-06-15"))
    store.request_cancel(cancelled)
    assert worker.run_one(store.run_dir(cancelled)) == RunState.CANCELLED


def test_a_run_is_the_same_twice(tmp_path: Path) -> None:
    a, b = ExperimentStore(tmp_path / "a"), ExperimentStore(tmp_path / "b")
    ra, rb = new_run(a, cell(day="2016-06-15")), new_run(b, cell(day="2016-06-15"))
    worker.run_one(a.run_dir(ra))
    worker.run_one(b.run_dir(rb))
    assert (a.run_dir(ra) / "raw/steps.jsonl").read_bytes() == (
        b.run_dir(rb) / "raw/steps.jsonl"
    ).read_bytes()


def test_a_simulate_run_never_starts_ray(tmp_path: Path) -> None:
    # The market's base class imports ray.rllib, so ray is loaded; it must never
    # be started (no ray.init, no worker processes).
    store = ExperimentStore(tmp_path)
    run_id = new_run(store, cell("no_order", day="2016-06-15"))
    code = (
        "import sys; from src_thesis.platform.kernel.worker import process; "
        f"process.run_one(r'{store.run_dir(run_id)}'); "
        "ray = sys.modules.get('ray'); print(ray is not None and ray.is_initialized())"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True
    )
    assert out.stdout.strip().splitlines()[-1] == "False", out.stderr[-500:]
