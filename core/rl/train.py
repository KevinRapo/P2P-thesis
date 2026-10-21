"""Train one run, record it, and load its policy again.

A run is PPO in one paradigm, one seed and one budget of environment steps. Everything around it is written to the run's folder:

    run.json         what was run: settings, environment, seed, versions, git
                     commit, status, final scores (fixes L-16's missing record)
    metrics.csv      one row per progress report: environment steps, team
                     return, learner metrics per module and their mean, min and
                     max over the modules (``modules/<metric>_mean`` ...), timing
                     (idle polls omitted)
    evaluation.csv   the policy and the baselines on held-out seeds, at fixed
                     environment-step counts (fixes L-16's missing baselines)
    evaluation_agents.csv, evaluation_episodes.csv
                     the same evaluations kept per episode and agent, and per
                     episode (``core/rl/policy.py``, ``evaluation``)
    checkpoint/      the algorithm at the end of the budget

What it fixes:

- L-14: the budget is counted in environment steps, the same for every
  algorithm and paradigm; iterations are only how often metrics are written.
- L-07: training stops with an error as soon as a loss or metric is NaN or
  infinite, instead of zeroing the gradients and continuing.
- L-11: no evaluation workers, no doubled CPU count, no population-based
  training; the algorithm is stopped and Ray shut down even when a run fails.
- L-15: ``load_policy`` acts with the trained module exactly as training does
  (``core/rl/policy.py``).

Each run starts its own Ray instance, unless ``RAY_ADDRESS`` names one that is
already running: then the run joins it, so many runs in parallel share one Ray
instance (its threads and processes are paid once, not once per run).
"""

from __future__ import annotations

import importlib
import json
import math
import os
import platform
import subprocess
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import gymnasium
import numpy as np
import pandas as pd
import ray
import torch
from ray.rllib.core import (
    COMPONENT_LEARNER,
    COMPONENT_LEARNER_GROUP,
    COMPONENT_RL_MODULE,
)
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModule
from ray.rllib.utils.metrics import (
    ENV_RUNNER_RESULTS,
    EPISODE_RETURN_MEAN,
    LEARNER_RESULTS,
    NUM_ENV_STEPS_SAMPLED_LIFETIME,
)

from core.rl.config import SETTINGS, Algorithm, build_algo, build_config
from core.rl.policy import Policy, baselines, evaluation, evaluation_seeds

REPO = Path(__file__).resolve().parents[2]

# Learner metrics written to metrics.csv, per module, when the algorithm has them.
LEARNER_METRICS = [
    "total_loss",
    "policy_loss",
    "vf_loss",
    "vf_explained_var",
    "entropy",
    "mean_kl_loss",
    "num_module_steps_trained",
]


@dataclass
class Run:
    """One training run.

    Attributes:
        algorithm: ``"ppo"`` (the only one in V2).
        paradigm: ``"ctce"``, ``"ctde"`` or ``"dtde"``.
        env_class: The multi-agent environment class.
        env_config: Its config.
        budget: Environment steps to train for.
        seed: The run's seed.
        eval_every: Evaluate every this many environment steps (and at 0 and at
            the end). 0: only at the end.
        eval_episodes: Evaluation episodes, on seeds training does not use.
        training: Overrides of the algorithm's settings (``config.SETTINGS``).
        model: Overrides of the network settings (``config.MODEL``).
        num_env_runners: Sampling processes besides the driver.
        num_gpus: GPUs for the learner (0 or 1).
        out_dir: The run's folder (default: ``runs/<algorithm>_<paradigm>_seed<seed>
            _<time>`` in the repository).
    """

    algorithm: str
    paradigm: str
    env_class: type
    env_config: dict = field(default_factory=dict)
    budget: int = 100_000
    seed: int = 0
    eval_every: int = 0
    eval_episodes: int = 10
    training: dict = field(default_factory=dict)
    model: dict = field(default_factory=dict)
    num_env_runners: int = 0
    num_gpus: int = 0
    out_dir: Optional[Path] = None


# --------------------------------------------------------------------------------------
# The run record
# --------------------------------------------------------------------------------------
def _class_path(cls: type) -> str:
    return f"{cls.__module__}:{cls.__qualname__}"


def _load_class(path: str) -> type:
    module, _, name = path.partition(":")
    obj: Any = importlib.import_module(module)
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


def _git() -> dict[str, Any]:
    """The repository's commit, and whether it had uncommitted changes."""
    try:
        commit = subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return {"commit": commit, "uncommitted_changes": bool(dirty)}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "uncommitted_changes": None}


def _record(run: Run, config) -> dict[str, Any]:
    algo_settings = {
        k: v for k, v in config.to_dict().items() if k in _settings_keys(run)
    }
    return {
        "algorithm": run.algorithm,
        "paradigm": run.paradigm,
        "env_class": _class_path(run.env_class),
        "env_config": run.env_config,
        "budget_env_steps": run.budget,
        "seed": run.seed,
        "eval_every": run.eval_every,
        "eval_seeds": evaluation_seeds(run.eval_episodes),
        "settings": algo_settings,
        "model": run.model,
        "num_env_runners": run.num_env_runners,
        "num_gpus": run.num_gpus,
        # None: Python's set order changed with the process, so the same seed does
        # not reproduce a multi-agent run (the runner fixes it, core/runner/launch.py)
        "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
        "versions": {
            "python": platform.python_version(),
            "ray": ray.__version__,
            "torch": torch.__version__,
            "numpy": np.__version__,
            "gymnasium": gymnasium.__version__,
        },
        "git": _git(),
        "started": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
    }


def _settings_keys(run: Run) -> set[str]:
    keys = set(SETTINGS[Algorithm(run.algorithm)]) | set(run.training)
    return keys | {"train_batch_size_per_learner"}


def _replace(path: Path, write) -> None:
    """Write the file at ``path`` in one step: ``write(tmp)`` writes it beside
    ``path``, which it then replaces, so a reader (the runner's status, read while
    the run trains) never sees half of it."""
    tmp = path.with_name(path.name + ".tmp")
    write(tmp)
    for attempt in range(20):  # Windows refuses while a reader has the file open
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def _append(path: Path, frame: pd.DataFrame) -> None:
    """Add ``frame``'s rows (in the file's columns) to the end of a CSV in one write,
    so a reader sees whole rows."""
    text = frame.to_csv(index=False, header=False)
    with open(path, "a", encoding="utf-8", newline="") as handle:
        handle.write(text)


def _append_csv(path: Path, frame: pd.DataFrame, written: dict) -> None:
    """Add ``frame``'s rows to the CSV at ``path``: the first time (no entry in
    ``written``) the file is replaced and its columns kept; later rows are written in
    those columns, so an evaluation point costs its own rows, not the history."""
    columns = written.get(path.name)
    if columns is None:
        written[path.name] = list(frame.columns)
        _replace(path, lambda tmp: frame.to_csv(tmp, index=False))
    else:
        _append(path, frame.reindex(columns=columns))


def _append_metrics(path: Path, rows: list[dict], columns: list[str]) -> None:
    """Add the last of ``rows`` to ``metrics.csv``. Its columns are those of every
    row so far (``columns``, kept by the caller): a row that brings new ones (the
    learner metrics, once learning starts) replaces the file once with all rows in
    the wider columns; every other row is appended, so a report costs one row, not
    the history."""
    new = [key for key in rows[-1] if key not in columns]
    if new:
        columns.extend(new)
        _replace(
            path,
            lambda tmp: pd.DataFrame(rows, columns=columns).to_csv(tmp, index=False),
        )
    else:
        _append(path, pd.DataFrame(rows[-1:], columns=columns))


def _write_json(path: Path, data: dict) -> None:
    text = json.dumps(data, indent=2, default=str)
    _replace(path, lambda tmp: tmp.write_text(text, encoding="utf-8"))


# --------------------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------------------
def _nonfinite(results: dict, prefix: str = "") -> list[str]:
    """Names of the NaN or infinite losses and entropies in the
    learner's (nested) results. Other metrics are left out: RLlib reports e.g.
    throughputs as NaN in the first iteration."""
    bad = []
    for key, value in results.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            bad += _nonfinite(value, f"{name}/")
        elif (
            ("loss" in str(key) or key == "entropy")
            and isinstance(value, (float, int, np.floating))
            and not math.isfinite(value)
        ):
            bad.append(name)
    return bad


def _iteration_row(iteration: int, result: dict) -> dict[str, Any]:
    env = result.get(ENV_RUNNER_RESULTS, {})
    row = {
        "iteration": iteration,
        "env_steps": env.get(NUM_ENV_STEPS_SAMPLED_LIFETIME, 0),
        "team_return_mean": env.get(EPISODE_RETURN_MEAN, float("nan")),
    }
    timers = result.get("timers", {})
    learner = result.get(LEARNER_RESULTS, {}).get("__all_modules__", {})
    # RLlib timers are smoothed means in seconds, not additive stage totals.
    row.update(
        sampler_sample_s_mean=env.get("sample", float("nan")),
        sampling_s_mean=timers.get("env_runner_sampling_timer", float("nan")),
        learner_call_s_mean=timers.get("learner_update_timer", float("nan")),
        async_learner_update_s_mean=learner.get(
            "learner_thread_update_timer", float("nan")
        ),
        learner_env_steps=learner.get("num_env_steps_trained_lifetime", 0),
    )
    per_metric: dict[str, list[float]] = {}
    for module_id, metrics in result.get(LEARNER_RESULTS, {}).items():
        if not isinstance(metrics, dict) or module_id == "__all_modules__":
            continue
        for name in LEARNER_METRICS:
            if name in metrics:
                row[f"{module_id}/{name}"] = metrics[name]
                per_metric.setdefault(name, []).append(float(metrics[name]))
    for name, values in per_metric.items():  # readable at any number of modules
        row[f"modules/{name}_mean"] = float(np.mean(values))
        row[f"modules/{name}_min"] = float(np.min(values))
        row[f"modules/{name}_max"] = float(np.max(values))
    return row


def learner_modules(algo) -> MultiRLModule:
    """The learner's modules, with their critics (the samplers' copies have none)."""
    return algo.learner_group._learner.module


def train(run: Run) -> dict[str, Any]:
    """Train one run and write its record (see the module docstring).

    Returns:
        The run record, as in ``run.json``.
    """
    out = (
        Path(run.out_dir)
        if run.out_dir
        else (
            REPO / "runs" / f"{run.algorithm}_{run.paradigm}_seed{run.seed}_"
            f"{datetime.now():%Y%m%d-%H%M%S}"
        )
    )
    out.mkdir(parents=True, exist_ok=True)
    config = build_config(
        run.algorithm,
        run.paradigm,
        run.env_class,
        run.env_config,
        seed=run.seed,
        training=run.training,
        num_env_runners=run.num_env_runners,
        num_gpus=run.num_gpus,
        model=run.model,
    )
    record = _record(run, config) | {"out_dir": str(out)}
    _write_json(out / "run.json", record)

    timings = {"evaluation_s": 0.0, "train_calls_s": 0.0}
    stage_start = time.perf_counter()
    started_ray = not ray.is_initialized()
    if started_ray and os.environ.get("RAY_ADDRESS"):
        ray.init()  # join the shared instance; Ray refuses resources when joining
    elif started_ray:
        ray.init(
            num_cpus=run.num_env_runners + 1,
            num_gpus=run.num_gpus,
            include_dashboard=False,
        )
    timings["ray_init_s"] = time.perf_counter() - stage_start
    algo, start = None, time.time()
    rows, evaluations = [], []
    metric_columns: list[str] = []  # of metrics.csv, as its rows bring them
    written: dict[str, list[str]] = {}  # the columns of each evaluation CSV
    seeds = evaluation_seeds(run.eval_episodes)
    env = run.env_class(run.env_config)

    def evaluate_now(env_steps: int, extra: Optional[dict] = None) -> None:
        evaluation_start = time.perf_counter()
        policies = {"trained": Policy(learner_modules(algo), run.paradigm, env)}
        found = evaluation(
            run.env_class, run.env_config, policies | (extra or {}), seeds
        )
        evaluations.append(found.summary)
        for frame, name in (
            (found.summary, "evaluation.csv"),
            (found.agents, "evaluation_agents.csv"),
            (found.episodes, "evaluation_episodes.csv"),
        ):
            frame.insert(0, "env_steps", env_steps)
            _append_csv(out / name, frame, written)
        timings["evaluation_s"] += time.perf_counter() - evaluation_start

    try:
        stage_start = time.perf_counter()
        algo = build_algo(config)
        timings["build_s"] = time.perf_counter() - stage_start
        # Step 0: the untrained policy and the baselines, on the same seeds.
        evaluate_now(0, baselines(run.env_class, run.env_config, run.seed))
        env_steps, iteration = 0, 0
        learner_steps = 0
        loop_start = time.perf_counter()
        next_eval = run.eval_every or run.budget
        while env_steps < run.budget:
            call_start = time.perf_counter()
            result = algo.train()
            call_s = time.perf_counter() - call_start
            timings["train_calls_s"] += call_s
            iteration += 1
            row = _iteration_row(iteration, result)
            progressed = (
                row["env_steps"] > env_steps or row["learner_env_steps"] > learner_steps
            )
            env_steps = max(env_steps, row["env_steps"])
            learner_steps = max(learner_steps, row["learner_env_steps"])
            bad = _nonfinite(result.get(LEARNER_RESULTS, {}))
            if progressed or bad:
                row.update(
                    env_steps=env_steps,
                    learner_env_steps=learner_steps,
                    train_call_s=call_s,
                    train_calls_s_total=timings["train_calls_s"],
                    elapsed_s=time.perf_counter() - loop_start,
                    sampled_steps_per_train_s=env_steps / timings["train_calls_s"],
                )
                rows.append(row)
                _append_metrics(out / "metrics.csv", rows, metric_columns)
            if bad:
                raise FloatingPointError(
                    f"Non-finite learner metrics at iteration {iteration} "
                    f"({env_steps} env steps): {', '.join(bad[:10])}"
                )
            if env_steps >= next_eval and env_steps < run.budget:
                evaluate_now(env_steps)
                next_eval += run.eval_every
        evaluate_now(env_steps)
        stage_start = time.perf_counter()
        algo.save_to_path(str((out / "checkpoint").resolve()))
        timings["checkpoint_s"] = time.perf_counter() - stage_start
        final = evaluations[-1].set_index("policy").loc["trained"].to_dict()
        record |= {
            "status": "completed",
            "env_steps": env_steps,
            "iterations": iteration,
            "final": final,
        }
    except Exception as error:
        record |= {
            "status": "failed",
            "error": repr(error),
            "traceback": traceback.format_exc(),
        }
        raise
    finally:
        record["timings"] = {k: round(v, 6) for k, v in timings.items()}
        record["duration_s"] = round(time.time() - start, 1)
        record["finished"] = datetime.now().isoformat(timespec="seconds")
        _write_json(out / "run.json", record)
        if algo is not None:
            algo.stop()
        if started_ray:
            ray.shutdown()
    return record


# --------------------------------------------------------------------------------------
# Loading a trained policy
# --------------------------------------------------------------------------------------
def load_policy(run_dir: str | Path) -> tuple[Policy, dict[str, Any]]:
    """The trained policy of a finished run, and its record.

    The policy acts in the run's multi-agent environment as in training; no
    algorithm or Ray is needed.
    """
    run_dir = Path(run_dir)
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    env_class = _load_class(record["env_class"])
    modules = MultiRLModule.from_checkpoint(
        str(
            (
                run_dir
                / "checkpoint"
                / COMPONENT_LEARNER_GROUP
                / COMPONENT_LEARNER
                / COMPONENT_RL_MODULE
            ).resolve()
        )
    )
    env = env_class(record["env_config"])
    return Policy(modules, record["paradigm"], env), record
