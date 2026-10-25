"""The probe check: train PPO on every probe in every paradigm and compare the
trained networks with the exact answers.

One procedure for the command line (``probe_ppo.py``, next to this file), the
notebook (``notebooks/rl/probe_paradigms.ipynb``) and the cluster (the same
notebook in the Jupyter job, ``docs/hpc/notebooks.md``). The probes themselves
are in ``core/rl/envs/probes.py``.

A run is judged by reading its networks in the probe's check states, not by its
return (which mixes in exploration noise):

- values: per agent in DTDE and CTDE, the group's sum in CTCE, within
  ``TOLERANCE`` · max(1, |expected|), or ``TOLERANCE`` · |expected| for a check
  marked ``relative``;
- actions: a continuous part's mean within ``TOLERANCE``; a categorical part must
  be the expected category exactly; a part expected as ``None`` is not judged; a
  ``Follows`` part must be within ``TOLERANCE`` of the target of the category the
  policy chose for the other part (``compare``).

A probe marked ``measured`` (8b, the stag hunt) has no pass or fail: its result is
a number, the share of pairs that coordinate (``measure``).

Probes are named by strings ("1" to "10", with "8a" and "8b"). Runs go to
``runs/probes_<preset>/`` and are reused: a finished run is scored, not trained
again. ``escalate`` trains the failing combinations again with a larger budget, to
separate "slow" from "broken".

On a SLURM job (the cluster), the runs share one Ray instance and use one worker
per physical core, capped by the user's thread limit (``parallel_setup``).
"""

from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from core.rl.ctce import GROUP
from core.rl.envs.probes import (
    ActionProbe,
    Check,
    ConditionalPartProbe,
    ConstantProbe,
    DiscountProbe,
    Follows,
    GatedActionProbe,
    LongEpisodeProbe,
    MixedActionProbe,
    MutualChoiceProbe,
    ObsActionProbe,
    ObservationProbe,
)
from core.rl.train import Run, load_policy, train

PARADIGMS = ["ctce", "ctde", "dtde"]
TOLERANCE = 0.15
ROOT = Path(__file__).resolve().parents[3]  # core/rl/scripts -> root


# --------------------------------------------------------------------------------------
# The probes and the presets
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Probe:
    """One probe as the check trains it.

    Attributes:
        name: Short name.
        env_class: The probe environment.
        gamma: The discount it is trained and checked with.
        env_config: Its ``env_config`` (agents, scrambled names, probe settings).
        budget: Environment steps with the ``"fast"`` preset.
        measured: No pass or fail: the result is ``measure``'s number.
    """

    name: str
    env_class: type
    gamma: float
    env_config: dict
    budget: int
    measured: bool = False


_THREE = {"n_agents": 3, "scramble_ids": False}
_SCRAMBLED = {"n_agents": 3, "scramble_ids": True}
_PAIRS = {"n_agents": 4, "scramble_ids": True}

PROBES: dict[str, Probe] = {
    "1": Probe("Constant", ConstantProbe, 0.99, _THREE, 3_000),
    "2": Probe("Observation", ObservationProbe, 0.99, _THREE, 3_000),
    "3": Probe("Discount", DiscountProbe, 0.5, _THREE, 3_000),
    "4": Probe("Action", ActionProbe, 0.99, _SCRAMBLED, 8_000),
    "5": Probe("Obs -> action", ObsActionProbe, 0.99, _SCRAMBLED, 15_000),
    "6": Probe("Mixed action", MixedActionProbe, 0.99, _SCRAMBLED, 10_000),
    "7": Probe("Gated action", GatedActionProbe, 0.99, _SCRAMBLED, 15_000),
    "8a": Probe(
        "Mutual choice, coordination",
        MutualChoiceProbe,
        0.99,
        _PAIRS | {"dso_reward": 0.1},
        20_000,
    ),
    "8b": Probe(
        "Mutual choice, stag hunt",
        MutualChoiceProbe,
        0.99,
        _PAIRS | {"dso_reward": 0.5},
        20_000,
        measured=True,
    ),
    "9": Probe("Conditional part", ConditionalPartProbe, 0.99, _SCRAMBLED, 15_000),
    "10": Probe("Long episode", LongEpisodeProbe, 0.95, _THREE, 24_000),
}

# "fast": a 2 x 64 network and short budgets, for day-to-day checks. "thorough":
# RLlib's default 2 x 256 network, a smaller learning rate and twice the budget.
PRESETS = {
    "fast": {
        "model": {"fcnet_hiddens": [64, 64]},
        "training": {
            "lr": 1e-3,
            "train_batch_size_per_learner": 500,
            "minibatch_size": 64,
            "num_epochs": 10,
        },
        "budget_scale": 1.0,
    },
    "thorough": {
        "model": {},
        "training": {"lr": 3e-4, "train_batch_size_per_learner": 1000},
        "budget_scale": 2.0,
    },
}

# Variants of the learner, on top of a preset: ``"fast:A"`` is the fast preset
# with variant A. The continuous action parts kept in bounds (A, RP-3h, the
# module's options in core/rl/modules.py), the gradient clip raised to MAPPO's
# (B, RP-3d), both, or one log σ per part for every state as in MAPPO (S).
VARIANTS = {
    "A": {"model": {"bound_mean": True, "log_std_bounds": [-3.0, 0.0]}},
    "B": {"training": {"grad_clip": 10.0}},
    "AB": {
        "model": {"bound_mean": True, "log_std_bounds": [-3.0, 0.0]},
        "training": {"grad_clip": 10.0},
    },
    "S": {"model": {"free_log_std_parts": True}},
}


def settings_of(preset: str) -> dict:
    """A preset's settings, with its variant's on top: ``"fast"`` or
    ``"fast:A"`` (``PRESETS``, ``VARIANTS``)."""
    name, _, variant = preset.partition(":")
    base = PRESETS[name]
    extra = VARIANTS[variant] if variant else {}

    return {
        "model": base["model"] | extra.get("model", {}),
        "training": base["training"] | extra.get("training", {}),
        "budget_scale": base["budget_scale"],
    }


# --------------------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------------------
def runs_dir(preset: str) -> Path:
    """Where the runs of a preset (and variant) are kept: ``runs/probes_fast``,
    ``runs/probes_fast_A``."""
    return ROOT / "runs" / f"probes_{preset.replace(':', '_')}"


def make_run(
    paradigm: str, probe: str, preset: str = "fast", seed: int = 0, scale: float = 1.0
) -> Run:
    """One run: PPO in ``paradigm`` on ``probe``, ``scale`` times the preset's
    budget."""
    p, settings = PROBES[probe], settings_of(preset)
    suffix = "" if scale == 1.0 else f"_x{scale:g}"

    return Run(
        "ppo",
        paradigm,
        p.env_class,
        dict(p.env_config),
        budget=int(p.budget * settings["budget_scale"] * scale),
        seed=seed,
        eval_episodes=5,
        training=settings["training"] | {"gamma": p.gamma},
        model=settings["model"],
        out_dir=runs_dir(preset) / f"ppo_{paradigm}_p{probe}_s{seed}{suffix}",
    )


def status(run: Run) -> str:
    """The run's status; a run whose process died (left "running") counts as not
    run, so it is trained again."""
    path = Path(run.out_dir) / "run.json"

    if not path.exists():
        return "not run"

    found = json.loads(path.read_text(encoding="utf-8"))["status"]

    return "not run" if found == "running" else found


def parallel_setup(workers: Optional[int] = None, shared_ray: Optional[bool] = None):
    """How many runs train at once, and whether they share one Ray instance.

    On a SLURM job: one worker per physical core less one (SLURM counts two
    hyper-threads per core), capped by the user's thread limit at about 80
    threads per run, and one shared Ray instance (each run's own instance costs
    about 175 threads). Elsewhere: half the CPUs, each run with its own Ray.
    ``workers`` and ``shared_ray`` override this.

    With a shared instance, the runs join it through ``RAY_ADDRESS``
    (``core/rl/train.py``) and their processes are started with ``spawn``: a
    forked copy of a process that has started Ray cannot use it.
    """
    cpus = int(os.environ.get("SLURM_CPUS_PER_TASK", 0))
    on_slurm = cpus > 0

    if workers is None:
        workers = max(1, (os.cpu_count() or 2) // 2)
        if on_slurm:
            import resource

            limit = resource.getrlimit(resource.RLIMIT_NPROC)[0]
            workers = max(1, min(cpus // 2 - 1, (limit - 1000) // 80))

    if shared_ray is None:
        shared_ray = on_slurm

    if shared_ray:
        import ray

        for name in (
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "MKL_NUM_THREADS",
            "RAY_num_server_call_thread",
            "RAY_gcs_server_rpc_server_thread_num",
            "RAY_gcs_server_rpc_client_thread_num",
            "RAY_num_grpc_internal_threads",
            "RAY_worker_num_grpc_internal_threads",
            "RAY_object_manager_rpc_threads_num",
        ):
            os.environ[name] = "1"
        if not ray.is_initialized():
            ray.init(num_cpus=1, include_dashboard=False, object_store_memory=200 << 20)
        os.environ["RAY_ADDRESS"] = ray.get_runtime_context().gcs_address

    return workers, shared_ray


def train_runs(runs: Iterable[Run], workers: int, retrain: bool = False) -> None:
    """Train the runs that have not finished, ``workers`` at a time, each in its
    own process (``spawn``). Prints one line per run."""
    runs = list(runs)

    if retrain:
        for run in runs:
            shutil.rmtree(run.out_dir, ignore_errors=True)

    pending = [run for run in runs if status(run) != "completed"]

    if not pending:
        return

    # The training processes import core.rl: the repository root on PYTHONPATH.
    paths = [str(ROOT), os.environ.get("PYTHONPATH", "")]
    os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, paths))
    os.environ.setdefault("PYTHONHASHSEED", "0")
    context = multiprocessing.get_context("spawn")
    start = time.time()

    with ProcessPoolExecutor(min(workers, len(pending)), mp_context=context) as pool:
        futures = {pool.submit(train, run): run for run in pending}
        for future in as_completed(futures):
            run = futures[future]
            try:
                note = f"trained in {future.result()['duration_s']:.0f} s"
            except Exception as error:  # report and go on with the others
                note = f"FAILED: {error!r}"[:200]
            print(f"{Path(run.out_dir).name:26s} {note}", flush=True)

    print(f"{len(pending)} runs trained in {time.time() - start:.0f} s", flush=True)


# --------------------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------------------
def compare(
    check: Check, values: Optional[dict], actions: Optional[dict], paradigm: str
) -> list[tuple]:
    """The rows of one check: ``(state, output, expected, got, tolerance)``, from the
    trained policy's ``values`` and ``actions`` in the check's state (each ``None``
    when the check has none). CTCE's one value is compared with the sum of the
    agents' values."""
    rows = []

    if check.value is not None:
        expected = (
            dict(check.value)
            if paradigm != "ctce"
            else {GROUP: sum(check.value.values())}
        )
        for mid, value in expected.items():
            size = abs(value) if check.relative else max(1.0, abs(value))
            rows.append(
                (check.name, f"value {mid}", value, values[mid], TOLERANCE * size)
            )

    if check.action is None:
        return rows

    for agent, value in check.action.items():
        if not isinstance(value, dict):
            have = float(np.asarray(actions[agent]).reshape(-1)[0])
            rows.append((check.name, f"action {agent}", value, have, TOLERANCE))
            continue

        for part, want in value.items():  # a mixed action, part by part
            have = np.asarray(actions[agent][part]).reshape(-1)[0]
            output = f"action {agent} {part}"

            if want is None:  # any value is right
                continue

            if isinstance(want, Follows):
                chosen = int(np.asarray(actions[agent][want.on]).reshape(-1)[0])
                target = want.targets[chosen]
                rows.append((check.name, output, target, float(have), TOLERANCE))
                continue

            tolerance = 0.0 if isinstance(want, int) else TOLERANCE
            rows.append((check.name, output, float(want), float(have), tolerance))

    return rows


def score(run: Run, probe: str) -> pd.DataFrame:
    """One row per checked output of a finished run: state, output, expected, got,
    tolerance, error, ok."""
    p = PROBES[probe]
    policy, _ = load_policy(run.out_dir)
    env = p.env_class(run.env_config)
    rows = []

    for check in env.checks(p.gamma):
        values = policy.values(check.obs) if check.value is not None else None
        actions = policy.act(check.obs) if check.action is not None else None
        rows += compare(check, values, actions, run.paradigm)

    frame = pd.DataFrame(
        rows, columns=["state", "output", "expected", "got", "tolerance"]
    )
    frame["error"] = (frame.got - frame.expected).abs()
    frame["ok"] = frame.error <= frame.tolerance + 1e-9

    return frame


def measure(run: Run, probe: str) -> float:
    """A measured probe's result: the share of pairs whose most likely actions
    coordinate (probe 8b, ``MutualChoiceProbe.coordinated``), in its check state."""
    p = PROBES[probe]
    policy, _ = load_policy(run.out_dir)
    env = p.env_class(run.env_config)
    state = env.checks(p.gamma)[0].obs

    return float(env.coordinated(policy.act(state)))


def verdict(frame: pd.DataFrame) -> tuple[str, float]:
    """``("PASS" or "FAIL", worst error / tolerance)``; a missed category (tolerance
    0) counts as infinitely far."""
    exact = frame.tolerance == 0
    ratio = frame.error / frame.tolerance.where(~exact, 1.0)
    ratio = ratio.where(~exact, np.where(frame.ok, 0.0, np.inf))

    return ("PASS" if frame.ok.all() else "FAIL"), float(ratio.max())


# --------------------------------------------------------------------------------------
# The check, and the longer budgets
# --------------------------------------------------------------------------------------
def check(
    probes: Iterable[str] = PROBES,
    paradigms: Iterable[str] = PARADIGMS,
    preset: str = "fast",
    seed: int = 0,
    scale: float = 1.0,
    workers: Optional[int] = None,
    retrain: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """Train every probe in every paradigm (one pool for all runs) and score them.

    Returns the summary (one row per probe and paradigm: result, worst error /
    tolerance or, for a measured probe, its measure; budget) and each run's scored
    checks by ``(probe, paradigm)``.
    """
    workers, _ = parallel_setup(workers)
    pairs = [(str(k), p) for k in probes for p in paradigms]
    runs = {pair: make_run(pair[1], pair[0], preset, seed, scale) for pair in pairs}
    train_runs(runs.values(), workers, retrain)
    rows, frames = [], {}

    for (probe, paradigm), run in runs.items():
        row = {"probe": probe, "name": PROBES[probe].name, "paradigm": paradigm}

        if status(run) != "completed":
            rows.append(row | {"result": "NOT RUN", "worst": float("nan")})
            continue

        frames[probe, paradigm] = score(run, probe)

        if PROBES[probe].measured:
            result, worst = "MEASURED", measure(run, probe)
        else:
            result, worst = verdict(frames[probe, paradigm])

        rows.append(row | {"result": result, "worst": worst, "budget": run.budget})

    return pd.DataFrame(rows), frames


def escalate(
    summary: pd.DataFrame,
    scales: Iterable[float] = (2, 4),
    preset: str = "fast",
    seed: int = 0,
    workers: Optional[int] = None,
) -> pd.DataFrame:
    """Train the combinations that did not pass again at each larger budget in
    turn, until they pass or the scales run out. One row per probe and paradigm:
    the smallest scale it passed at (``NaN``: none). Measured probes have no pass
    or fail and are left out."""
    workers, _ = parallel_setup(workers)
    judged = summary[summary.result != "MEASURED"]
    passed_at = {
        (r.probe, r.paradigm): (1.0 if r.result == "PASS" else float("nan"))
        for r in judged.itertuples()
    }

    for scale in scales:
        failing = [pair for pair, at in passed_at.items() if np.isnan(at)]

        if not failing:
            break

        # Every failing combination of this scale in one pool.
        runs = {(k, p): make_run(p, k, preset, seed, scale) for k, p in failing}
        print(f"x{scale:g}: {len(runs)} combinations", flush=True)
        train_runs(runs.values(), workers)

        for (probe, paradigm), run in runs.items():
            if status(run) == "completed":
                result, _ = verdict(score(run, probe))
                if result == "PASS":
                    passed_at[probe, paradigm] = float(scale)

    return pd.DataFrame(
        [
            {"probe": k, "name": PROBES[k].name, "paradigm": p, "passed at": at}
            for (k, p), at in passed_at.items()
        ]
    )


def table(summary: pd.DataFrame) -> pd.DataFrame:
    """The summary as probes by paradigms, in the probes' order: ``PASS 0.42``
    (result and worst error / tolerance), ``FAIL miss`` (a wrong category) or
    ``MEASURED 0.50`` (a measured probe's share)."""

    def cell_of(row) -> str:
        if row.result == "NOT RUN":
            return "NOT RUN"

        worst = "miss" if np.isinf(row.worst) else f"{row.worst:.2f}"

        return f"{row.result} {worst}"

    cell = summary.apply(cell_of, axis=1)
    order = [k for k in PROBES if k in set(summary.probe)]
    found = summary.assign(cell=cell).pivot(
        index="probe", columns="paradigm", values="cell"
    )
    found = found.reindex(
        index=order, columns=[p for p in PARADIGMS if p in set(summary.paradigm)]
    )
    found.index = pd.MultiIndex.from_tuples(
        [(k, PROBES[k].name) for k in order], names=["probe", "name"]
    )

    return found
