"""Train one run, record it, and load its policy again.

A run is one algorithm, one paradigm, one seed and one budget of environment
steps. Everything around it is written to the run's folder:

    run.json         what was run: settings, environment, seed, versions, git
                     commit, status, final scores (fixes I-64's missing record)
    metrics.csv      one row per training iteration: environment steps, team
                     return, the learner's losses, entropy, KL, ...
    evaluation.csv   the policy and the baselines on held-out seeds, at fixed
                     environment-step counts (fixes I-64's missing baselines)
    checkpoint/      the algorithm at the end of the budget

What it fixes:

- I-50: the budget is counted in environment steps, the same for every
  algorithm and paradigm; iterations are only how often metrics are written.
- R-02: training stops with an error as soon as a loss or metric is NaN or
  infinite, instead of zeroing the gradients and continuing.
- I-62: no evaluation workers, no doubled CPU count, no population-based
  training; the algorithm is stopped and Ray shut down even when a run fails.
- I-61: ``load_policy`` acts with the trained module exactly as training does
  (``core/fixed/policy.py``).
"""

from __future__ import annotations

import importlib
import json
import math
import platform
import subprocess
import sys
import time
import traceback
from contextlib import contextmanager
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

from RL.core.fixed.config import SETTINGS, Algorithm, build_config
from RL.core.fixed.policy import Policy, baselines, evaluate, evaluation_seeds

REPO = Path(__file__).resolve().parents[2]

# Learner metrics written to metrics.csv, per module, when the algorithm has them.
LEARNER_METRICS = [
    "total_loss",
    "policy_loss",
    "vf_loss",
    "vf_explained_var",
    "entropy",
    "mean_kl_loss",
    "qf_loss",
    "alpha_value",
    "num_module_steps_trained",
]


@dataclass
class Run:
    """One training run.

    Attributes:
        algorithm: ``"ppo"``, ``"appo"`` or ``"sac"``.
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
    # Runs copied from the separate RL worktree used core.* module names.
    if module.startswith(("core.envs.", "core.fixed.", "core.rl.")):
        module = "RL." + module
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
    return keys | {
        "train_batch_size_per_learner",
        "num_steps_sampled_before_learning_starts",
    }


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


# --------------------------------------------------------------------------------------
# Training
# --------------------------------------------------------------------------------------
def _nonfinite(results: dict, prefix: str = "") -> list[str]:
    """Names of the NaN or infinite losses, entropies and temperatures in the
    learner's (nested) results. Other metrics are left out: RLlib reports e.g.
    throughputs as NaN in the first iteration."""
    bad = []
    for key, value in results.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            bad += _nonfinite(value, f"{name}/")
        elif (
            ("loss" in str(key) or key in ("entropy", "alpha_value"))
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
    for module_id, metrics in result.get(LEARNER_RESULTS, {}).items():
        if not isinstance(metrics, dict) or module_id == "__all_modules__":
            continue
        for name in LEARNER_METRICS:
            if name in metrics:
                row[f"{module_id}/{name}"] = metrics[name]
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

    started_ray = not ray.is_initialized()
    if started_ray:
        ray.init(
            num_cpus=run.num_env_runners + 1,
            num_gpus=run.num_gpus,
            include_dashboard=False,
        )
    algo, start = None, time.time()
    rows, evaluations = [], []
    seeds = evaluation_seeds(run.eval_episodes)
    env = run.env_class(run.env_config)

    def evaluate_now(env_steps: int, extra: Optional[dict] = None) -> None:
        policies = {"trained": Policy(learner_modules(algo), run.paradigm, env)}
        frame = evaluate(run.env_class, run.env_config, policies | (extra or {}), seeds)
        frame.insert(0, "env_steps", env_steps)
        evaluations.append(frame)
        pd.concat(evaluations).to_csv(out / "evaluation.csv", index=False)

    try:
        algo = config.build_algo()
        # Step 0: the untrained policy and the baselines, on the same seeds.
        evaluate_now(0, baselines(run.env_class, run.env_config, run.seed))
        env_steps, iteration = 0, 0
        next_eval = run.eval_every or run.budget
        while env_steps < run.budget:
            result = algo.train()
            iteration += 1
            row = _iteration_row(iteration, result)
            env_steps = row["env_steps"]
            rows.append(row)
            pd.DataFrame(rows).to_csv(out / "metrics.csv", index=False)
            bad = _nonfinite(result.get(LEARNER_RESULTS, {}))
            if bad:
                raise FloatingPointError(
                    f"Non-finite learner metrics at iteration {iteration} "
                    f"({env_steps} env steps): {', '.join(bad[:10])}"
                )
            if env_steps >= next_eval and env_steps < run.budget:
                evaluate_now(env_steps)
                next_eval += run.eval_every
        evaluate_now(env_steps)
        algo.save_to_path(str((out / "checkpoint").resolve()))
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
@contextmanager
def _checkpoint_imports():
    """Resolve pre-migration pickle names only while reading a checkpoint.

    The market's core package is never replaced. Restore any existing entries
    after loading, so legacy names cannot leak into subsequent market imports.
    """
    names = (
        "envs",
        "envs.probes",
        "envs.spread",
        "envs.toy",
        "envs.shapes",
        "fixed",
        "fixed.config",
        "fixed.grouping",
        "fixed.ctde_modules",
    )
    aliases = {
        "core." + name: importlib.import_module("RL.core." + name) for name in names
    }
    previous = {name: sys.modules.get(name) for name in aliases}
    try:
        sys.modules.update(aliases)
        yield
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


def load_policy(run_dir: str | Path) -> tuple[Policy, dict[str, Any]]:
    """The trained policy of a finished run, and its record.

    The policy acts in the run's multi-agent environment as in training; no
    algorithm or Ray is needed.
    """
    run_dir = Path(run_dir)
    record = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    env_class = _load_class(record["env_class"])
    with _checkpoint_imports():
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
