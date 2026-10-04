"""The experiment layer without MARLEM: files, runs, store, worker and pool.

04-application-layer.md §5. Worker runs use the ``noop`` runner, so nothing here
needs the environment, pandapower or Ray.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src_thesis.experiments.models import expand, files, resolve
from src_thesis.experiments.models.manifest import build_manifest
from src_thesis.experiments.models.records import (
    ExperimentFile,
    ExperimentMeta,
    RunCell,
    RunState,
)
from src_thesis.experiments.store.recorder import EpisodeRecorder, StepRecord
from src_thesis.experiments.store.filesystem import (
    ExperimentStore,
    IllegalTransitionError,
)
from src_thesis.experiments.worker import pool
from src_thesis.experiments.worker import process as worker

REPO = Path(__file__).resolve().parents[1]


def case6(**sections) -> ExperimentFile:
    base = {
        "meta": ExperimentMeta(id="case6-3x3", name="Case 6"),
        "time": {"days": {"mode": "fixed", "date": "2016-06-15"}},
        "learning": {
            "paradigms": ["ctce", "ctde", "dtde"],
            "algorithms": ["ppo", "appo", "sac"],
            "seeds": [1, 2, 3],
        },
    }
    base.update(sections)
    return ExperimentFile(**base)


def new_run(store: ExperimentStore, cell: RunCell, file: ExperimentFile) -> str:
    resolved = resolve.resolve_run(file, cell)
    run_id = expand.run_id(file.meta.id, cell, files.canonical_hash(file))
    store.create_run(file, resolved, build_manifest(file, resolved, cell, run_id))
    return run_id


NOOP = RunCell(kind="noop", algorithm="noop", paradigm="-", seed=0)


# --------------------------------------------------------------------------- files
def test_hash_ignores_formatting_and_key_order(tmp_path: Path) -> None:
    file = case6()
    path = files.save(file, tmp_path / "a.marlem.json")
    reordered = json.dumps(json.loads(path.read_text()), sort_keys=True)
    assert files.canonical_hash(files.parse(reordered)) == files.canonical_hash(file)
    assert files.load(path) == file


def test_unknown_schema_version_is_rejected() -> None:
    with pytest.raises(ValueError):
        files.parse(
            json.dumps({"schema_version": "0.1", "meta": {"id": "x", "name": "x"}})
        )


# --------------------------------------------------------------------------- expand
def test_3x3_matrix_with_seeds_and_baselines() -> None:
    assert len(expand.expand(case6())) == 27
    with_baselines = case6(baselines=["no_order", "random"])
    cells = expand.expand(with_baselines)
    assert len(cells) == 27 + 2 * 3
    assert {c.kind for c in cells} == {"train", "baseline"}


def test_sweep_multiplies_the_matrix() -> None:
    mechanisms = ["average", "buyer", "seller", "bid_ask_spread", "nash_bargaining"]
    file = case6(sweep={"parameters": {"market.mechanism": mechanisms}})
    cells = expand.expand(file)
    assert len(cells) == 27 * 5
    assert cells[0].sweep_point == {"market.mechanism": "average"}


def test_run_id_format() -> None:
    cell = RunCell(sweep_label="avg", algorithm="ppo", paradigm="ctde", seed=2)
    assert expand.run_id("case6-3x3", cell, "abcdef123456") == (
        "case6-3x3__avg__ppo-ctde__s2__abcdef12"
    )


# --------------------------------------------------------------------------- resolve
def test_resolve_fills_defaults_but_keeps_given_values() -> None:
    resolved = resolve.resolve(case6(market={"mechanism": "buyer"}))
    assert resolved.market["mechanism"] == "buyer"
    assert resolved.market["ledger"] == {"enabled": True, "difficulty": 2}
    assert resolved.grid["limits"]["v_min_pu"] is None  # network limits (D-15)


def test_resolve_run_fixes_the_cell() -> None:
    cell = expand.expand(case6())[5]
    learning = resolve.resolve_run(case6(), cell).learning
    assert learning["paradigms"] == [cell.paradigm]
    assert learning["algorithms"] == [cell.algorithm]
    assert learning["seeds"] == [cell.seed]


def test_day_sampler_holds_out_disjoint_seeded_days() -> None:
    days = {
        "mode": "sampler",
        "start": "2016-05-01",
        "end": "2016-08-31",
        "filter": {"day_type": "workday"},
        "eval_holdout": 0.2,
        "seed": 42,
    }
    a = resolve.resolve_days({"days": days})
    b = resolve.resolve_days({"days": days})
    assert a == b and not set(a.train) & set(a.eval)
    assert len(a.eval) == -(-(len(a.train) + len(a.eval)) * 2 // 10)  # ceil 20 %
    assert len(a.train) + len(a.eval) == 88  # workdays May-Aug 2016


# --------------------------------------------------------------------------- store
def test_store_run_lifecycle(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    run_id = new_run(store, NOOP, case6())
    assert store.read_status(run_id).state == RunState.READY
    with pytest.raises(IllegalTransitionError):
        store.set_state(run_id, RunState.COMPLETED)
    store.set_state(run_id, RunState.QUEUED)
    store.request_cancel(run_id)
    assert store.cancel_requested(run_id)
    assert [s.run_id for s in store.list_runs(state=RunState.QUEUED)] == [run_id]
    assert store.rebuild_index()["runs"][run_id]["state"] == "QUEUED"


def test_recorder_writes_evaluation_episodes_only(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    run_id = new_run(store, NOOP, case6())
    rec = EpisodeRecorder(store, run_id, "evaluation")
    for episode, evaluation in ((0, False), (1, True)):
        rec.start_episode(episode, "2016-06-15", evaluation)
        rec.record(StepRecord(episode=episode, step=0, day="2016-06-15"))
        rec.end_episode({"served_demand_share": 0.9})
    steps = list(store.read_jsonl(run_id, "raw/steps.jsonl"))
    assert [s["episode"] for s in steps] == [1]
    assert len(list(store.read_jsonl(run_id, "metrics/evaluation.jsonl"))) == 1


# --------------------------------------------------------------------------- worker
def test_worker_completes_a_noop_run(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    run_id = new_run(store, NOOP, case6())
    assert worker.run_one(store.run_dir(run_id)) == RunState.COMPLETED
    status = store.read_status(run_id)
    assert status.progress == 1.0 and status.finished is not None
    assert "finished: COMPLETED" in store.log_tail(run_id)[-1]


def test_worker_fails_when_resolved_file_was_edited(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    run_id = new_run(store, NOOP, case6())
    path = store.run_dir(run_id) / "resolved.json"
    path.write_text(path.read_text().replace("2016-06-15", "2016-06-16"))
    assert worker.run_one(store.run_dir(run_id)) == RunState.FAILED


def test_worker_honours_cancel_and_reports_errors(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    cancelled = new_run(store, NOOP, case6())
    store.request_cancel(cancelled)
    assert worker.run_one(store.run_dir(cancelled)) == RunState.CANCELLED
    unbuilt = new_run(
        store,
        RunCell(kind="baseline", algorithm="random", paradigm="-", seed=1),
        case6(),
    )
    assert worker.run_one(store.run_dir(unbuilt)) == RunState.FAILED
    assert "NotImplementedError" in store.read_status(unbuilt).message


def test_pool_runs_workers_as_processes(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    run_ids = [
        new_run(store, NOOP.model_copy(update={"seed": s}), case6()) for s in (1, 2)
    ]
    workers = pool.WorkerPool(store, max_parallel=1)
    workers.enqueue(run_ids)
    workers.wait_all(timeout_s=60)
    assert [store.read_status(r).state for r in run_ids] == [RunState.COMPLETED] * 2


def test_reconcile_marks_dead_workers_failed(tmp_path: Path) -> None:
    store = ExperimentStore(tmp_path)
    run_id = new_run(store, NOOP, case6())
    store.set_state(run_id, RunState.QUEUED)
    store.set_state(run_id, RunState.RUNNING, pid=2**22 + 7)  # no such process
    assert pool.reconcile(store) == [run_id]
    assert store.read_status(run_id).state == RunState.FAILED


# --------------------------------------------------------------------------- boundaries
def test_experiment_layer_imports_nothing_heavy() -> None:
    code = (
        "import sys, src_thesis.experiments.worker.process as w, src_thesis.experiments.worker.pool as p; "
        "heavy = {'ray', 'torch', 'pandapower', 'simbench', 'nicegui'}; "
        "print(sorted(heavy & {m.split('.')[0] for m in sys.modules}))"
    )
    done = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True
    )
    assert done.stdout.strip() == "[]", done.stderr
