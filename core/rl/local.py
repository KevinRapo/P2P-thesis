"""Train an ``RLTrainer``'s configuration in this process, without Ray Tune.

Not part of the original code. ``RLTrainer.train`` runs Ray Tune with
population-based training, separate sampling, evaluation and learner workers;
each worker loads torch, which needs several GB of memory and minutes to start.
To check that an algorithm and a training paradigm learn at all, this runs the
same algorithm configuration (same RL modules, grouping, hyperparameters) with
sampling and learning in the current process and no evaluation workers.
"""

from __future__ import annotations

import time

import pandas as pd
import ray
from ray.rllib.algorithms.algorithm import Algorithm
from ray.rllib.utils.metrics import ENV_RUNNER_RESULTS, EPISODE_RETURN_MEAN

from core.rl.train import RLTrainer


def build_local(trainer: RLTrainer, embeddings_dim: int = 128, **training) -> Algorithm:
    """The trainer's algorithm, built to run in this process: sampling and
    learning here, no evaluation. Call ``train()`` on it, ``stop()`` when done.

    Args:
        trainer: Defines the environment, algorithm and training paradigm.
        embeddings_dim: Width of the RL modules' hidden layers, as in ``train``.
        **training: Overrides of the algorithm's training settings, passed to
            ``AlgorithmConfig.training``: e.g. ``lr=3e-4`` (the original starts
            PPO at 1e-5 and lets population-based training change it), or
            ``train_batch_size_per_learner=2000`` (environment steps per
            iteration; fewer is faster and noisier).
    """
    config, _ = trainer._setup_config(embeddings_dim)
    config = (
        config.env_runners(num_env_runners=0)
        .learners(num_learners=0, num_gpus_per_learner=0)
        .evaluation(
            evaluation_interval=None,
            evaluation_num_env_runners=0,
            evaluation_parallel_to_training=False,
            evaluation_duration=1,
        )
    )
    if training:
        config = config.training(**training)
    if not ray.is_initialized():
        ray.init(num_cpus=1, include_dashboard=False, log_to_driver=False)
    return config.build_algo()


# What the learner reports per module, as Jones's guide suggests watching it:
# entropy falls and levels out, KL stays small, the value function explains more
# and more of the returns (explained variance towards 1).
LEARNER_METRICS = {
    "entropy": "entropy",
    "mean_kl_loss": "kl",
    "policy_loss": "policy_loss",
    "vf_loss": "vf_loss",
    "vf_explained_var": "vf_explained_var",
}


def train(algo: Algorithm, iters: int) -> pd.DataFrame:
    """Train a built algorithm ``iters`` more iterations.

    Returns:
        One row per iteration: ``return_mean`` (mean episode return over all
        agents, the metric Tune optimises), ``seconds``, and the learner metrics
        of ``LEARNER_METRICS``, averaged over the modules (one per agent in
        DTDE).
    """
    rows = []
    for _ in range(iters):
        start = time.time()
        result = algo.train()
        row = {
            "return_mean": result[ENV_RUNNER_RESULTS].get(EPISODE_RETURN_MEAN),
            "seconds": time.time() - start,
        }
        modules = [
            stats
            for module_id, stats in result.get("learners", {}).items()
            if module_id != "__all_modules__" and isinstance(stats, dict)
        ]
        for key, name in LEARNER_METRICS.items():
            found = [float(m[key]) for m in modules if key in m]
            row[name] = sum(found) / len(found) if found else None
        rows.append(row)
    out = pd.DataFrame(rows)
    out.index = pd.RangeIndex(1, len(out) + 1, name="iteration")
    return out


def train_local(
    trainer: RLTrainer, iters: int, embeddings_dim: int = 128, **training
) -> pd.DataFrame:
    """Build the trainer's algorithm in this process, train it ``iters``
    iterations and stop it. Arguments as in ``build_local``; returns as
    ``train``."""
    algo = build_local(trainer, embeddings_dim, **training)
    try:
        return train(algo, iters)
    finally:
        algo.stop()
