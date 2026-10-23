"""Time PPO in one paradigm at one problem size.

Not a training run: no evaluation, no checkpoint. It builds the configuration
``build_config`` would train with, then measures, in this order:

    build     building the algorithm (networks, optimisers, the sampler)
    warm-up   iterations until the learner has reported its first update
              (one batch) and at least ``warmup_iterations``; not counted below
    timed     iterations until ``timed_env_steps`` environment steps (or
              ``max_seconds``): seconds per 1000 environment steps, gradient
              steps, samples trained
    sampling  the same sampler alone, ``sample_env_steps`` steps with the
              current policy and no learning: what acting costs; the rest of
              the timed phase is learning

Every setting that decides the cost is written out in the record (batch,
minibatch, epochs), with RLlib's defaults filled in, so a
result says exactly what was measured.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import psutil
import ray
from gymnasium import spaces
import torch
from ray.rllib.utils.metrics import (
    ENV_RUNNER_RESULTS,
    EPISODE_RETURN_MEAN,
    LEARNER_RESULTS,
    NUM_ENV_STEPS_SAMPLED_LIFETIME,
    NUM_MODULE_STEPS_TRAINED_LIFETIME,
)

from core.rl.config import Algorithm, Paradigm, build_algo, build_config
from core.rl.train import _git, learner_modules


@dataclass
class Bench:
    """One benchmark.

    Attributes:
        algorithm: ``"ppo"`` (the only one in V2).
        paradigm: ``"ctce"``, ``"ctde"`` or ``"dtde"``.
        env_class: The multi-agent environment class.
        env_config: Its config.
        training: Overrides of the algorithm's settings (``config.SETTINGS``).
        model: Overrides of the network settings (``config.MODEL``).
        num_gpus: 1 to learn on the GPU (sampling stays on the CPU).
        warmup_iterations: Iterations before timing, at least.
        timed_env_steps: Environment steps to time, at least one iteration.
        max_seconds: Stop timing after the iteration that passes this.
        sample_env_steps: Environment steps of the sampling-only measurement.
        seed: Seed of RLlib.
        out: File the record is written to (``None``: not written).
    """

    algorithm: str
    paradigm: str
    env_class: type
    env_config: dict = field(default_factory=dict)
    training: dict = field(default_factory=dict)
    model: dict = field(default_factory=dict)
    num_gpus: int = 0
    warmup_iterations: int = 1
    timed_env_steps: int = 4000
    max_seconds: float = 300.0
    sample_env_steps: int = 1000
    seed: int = 0
    out: Optional[Path] = None


# --------------------------------------------------------------------------------------
# What was measured: the settings that decide the cost
# --------------------------------------------------------------------------------------
def settings(config, algorithm: Algorithm) -> dict[str, Any]:
    """The settings that decide the cost of an iteration, defaults filled in."""
    out = {
        "train_batch_size_per_learner": config.train_batch_size_per_learner,
        "rollout_fragment_length": config.get_rollout_fragment_length(),
        "fcnet_hiddens": config.model_config.get("fcnet_hiddens"),
    }
    return out | {
        "minibatch_size": config.minibatch_size,
        "num_epochs": config.num_epochs,
        "lr": config.lr,
    }


def gradient_batch(config, algorithm: Algorithm) -> int:
    """Samples per gradient step: PPO's minibatch (the whole batch when unset)."""
    return config.minibatch_size or config.train_batch_size_per_learner


def _shapes(algo) -> dict[str, Any]:
    """Input and output size of each module the learner trains, and parameters."""
    modules = learner_modules(algo)
    first = next(iter(modules.keys()))
    module = modules[first]

    return {
        "n_modules": len(modules.keys()),
        "module_obs_dim": int(module.observation_space.shape[0]),
        "module_act_dim": int(spaces.flatdim(module.action_space)),
        "parameters": sum(
            p.numel() for mid in modules.keys() for p in modules[mid].parameters()
        ),
    }


# --------------------------------------------------------------------------------------
# Measuring
# --------------------------------------------------------------------------------------
def _counters(result: dict) -> tuple[int, int, float]:
    """Environment steps sampled, samples trained (all modules) and the mean
    team return, so far."""
    env = result.get(ENV_RUNNER_RESULTS, {})
    trained = sum(
        m.get(NUM_MODULE_STEPS_TRAINED_LIFETIME, 0)
        for mid, m in result.get(LEARNER_RESULTS, {}).items()
        if isinstance(m, dict) and mid != "__all_modules__"
    )

    return (
        int(env.get(NUM_ENV_STEPS_SAMPLED_LIFETIME, 0)),
        int(trained),
        float(env.get(EPISODE_RETURN_MEAN, math.nan)),
    )


def benchmark(bench: Bench) -> dict[str, Any]:
    """Run one benchmark (see the module docstring) and return its record."""
    algorithm, paradigm = Algorithm(bench.algorithm), Paradigm(bench.paradigm)
    env = bench.env_class(bench.env_config)
    n_agents = len(env.agents_id)
    episode_length = getattr(env, "length", None)
    config = build_config(
        algorithm,
        paradigm,
        bench.env_class,
        bench.env_config,
        seed=bench.seed,
        training=bench.training,
        num_gpus=bench.num_gpus,
        model=bench.model,
    )
    record: dict[str, Any] = {
        "algorithm": algorithm.value,
        "paradigm": paradigm.value,
        "device": "gpu" if bench.num_gpus else "cpu",
        "n_agents": n_agents,
        "agent_obs_dim": int(env.observation_spaces[env.agents_id[0]].shape[0]),
        "agent_act_dim": int(env.action_spaces[env.agents_id[0]].shape[0]),
        "episode_length": episode_length,
        "env_config": bench.env_config,
        "settings": settings(config, algorithm),
        "gradient_batch": gradient_batch(config, algorithm),
        "torch_threads": torch.get_num_threads(),
        "git": _git(),
        "started": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
    }
    _write(bench.out, record)

    started_ray = not ray.is_initialized()

    if started_ray:
        ray.init(num_cpus=1, num_gpus=bench.num_gpus, include_dashboard=False)

    algo = None

    try:
        start = time.perf_counter()
        algo = build_algo(config)
        record["build_s"] = time.perf_counter() - start
        record |= _shapes(algo)

        # Warm-up: until the learner has updated once, and warmup_iterations.
        start, iterations, trained = time.perf_counter(), 0, 0

        while iterations < bench.warmup_iterations or trained == 0:
            steps, trained, _ = _counters(algo.train())
            iterations += 1
            if time.perf_counter() - start > bench.max_seconds:
                raise TimeoutError(f"no learner update after {steps} env steps")

        record["warmup"] = {
            "iterations": iterations,
            "env_steps": steps,
            "seconds": time.perf_counter() - start,
        }

        # Timed: whole iterations, until timed_env_steps or max_seconds.
        steps0, trained0, return0 = steps, trained, None
        start, iterations = time.perf_counter(), 0

        while True:
            steps, trained, team_return = _counters(algo.train())
            iterations += 1
            return0 = team_return if return0 is None else return0
            elapsed = time.perf_counter() - start

            if steps - steps0 >= bench.timed_env_steps or elapsed > bench.max_seconds:
                break

        env_steps, samples = steps - steps0, trained - trained0
        grad_steps = samples / record["gradient_batch"] if samples else math.nan
        record["timed"] = {
            "iterations": iterations,
            "env_steps": env_steps,
            "seconds": elapsed,
            "samples_trained": samples,
            "gradient_steps": grad_steps,
        }

        # Sampling alone: the same sampler, current policy, no learning.
        start = time.perf_counter()
        algo.env_runner.sample(num_timesteps=bench.sample_env_steps, explore=True)
        sample_s = time.perf_counter() - start

        per_1k = 1000 * elapsed / env_steps
        sample_per_1k = 1000 * sample_s / bench.sample_env_steps
        reward_scale = n_agents * (episode_length or 1)
        record["results"] = {
            "s_per_1k_env_steps": per_1k,
            "sample_s_per_1k": sample_per_1k,
            "learn_s_per_1k": max(per_1k - sample_per_1k, 0.0),
            "env_steps_per_s": env_steps / elapsed,
            "gradient_steps_per_s": grad_steps / elapsed,
            "gradient_steps_per_1k_env_steps": 1000 * grad_steps / env_steps,
            "h_per_1M_env_steps": per_1k * 1000 / 3600,
            "reward_per_agent_step_start": return0 / reward_scale,
            "reward_per_agent_step_end": team_return / reward_scale,
            "rss_gb": psutil.Process(os.getpid()).memory_info().rss / 1e9,
            "gpu_peak_gb": (
                torch.cuda.max_memory_allocated() / 1e9 if bench.num_gpus else 0.0
            ),
        }
        record["status"] = "completed"
    except Exception as error:
        record |= {"status": "failed", "error": repr(error)}
    finally:
        record["finished"] = datetime.now().isoformat(timespec="seconds")
        _write(bench.out, record)

        if algo is not None:
            algo.stop()

        if started_ray:
            ray.shutdown()

    return record


def _write(path: Optional[Path], record: dict) -> None:
    if path is not None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2, default=str), encoding="utf-8")
