"""The algorithm configuration of one combination of algorithm and paradigm.

Only RLlib's algorithms and modules are used; what changes between paradigms is
the environment the algorithm sees and, for CTDE, what the actor reads:

| Paradigm | Environment | Modules | Objective |
|---|---|---|---|
| DTDE | the multi-agent environment | one per agent, RLlib's default | own reward |
| CTDE | ``CentralStateEnv``: o_i plus the global state | one per agent, actor on o_i, critic on everything (``ctde_modules.py``) | own reward |
| CTCE | ``GroupedEnv``: one agent, joint ``Box`` spaces | one, RLlib's default | summed reward (social planner) |

DTDE and CTDE optimise the same individual objective and differ only in what the
critic sees, so a difference between them is the central critic's.

Every paradigm uses the same network settings (RLlib's defaults: 2 x 256 tanh,
separate actor and critic), which fixes L-04.

The hyperparameters start from the original's (``SETTINGS`` in ``defaults.py``,
[P2] Table 8), with the defects removed:

- PPO: ``use_kl_loss=False``, so the KL term is not computed at all (fixes L-07;
  the original set ``kl_coeff=0`` and kept it). ``vf_clip_param`` raised from
  RLlib's 10: RLlib caps the squared value error there, so an error above about
  3.2 would give the critic no gradient at all. Rewards should still be scaled by
  the environment to returns of order 1-10.
- APPO: no ``lambda_``; RLlib's V-trace has no lambda (fixes L-13).
- SAC: ``target_entropy="auto"`` (the negative action size of each module: the
  agent's in DTDE and CTDE, the group's in CTCE, as the original intended), a
  uniform replay buffer of 1000 steps for every paradigm. Episodes are sampled
  in fragments (RLlib's default), not ``complete_episodes`` as in the original:
  in that mode RLlib 2.51 resets the environment with the run's seed at every
  sample call, so with a seed every SAC training step would replay the same
  episode.
- No population-based training and no Ray Tune (fixes L-10 and part of L-11):
  one run has fixed hyperparameters and one seed; tuning and seeds are loops
  around ``core/rl/train.py``.
- Iterations are not tied to wall-clock time (``min_time_s_per_iteration=0``),
  and the budget is counted in environment steps by the trainer (fixes L-14).
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Optional

import numpy as np
from ray.rllib.algorithms.algorithm_config import AlgorithmConfig
from ray.rllib.algorithms.appo import APPOConfig
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.algorithms.sac import SACConfig
from ray.rllib.core.rl_module.default_model_config import DefaultModelConfig
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModuleSpec
from ray.rllib.core.rl_module.rl_module import RLModuleSpec

from core.rl.grouping import GROUP, CentralStateEnv, GroupedEnv
from core.rl.ctde_modules import CTDE_MODULES
from core.rl.defaults import NETWORK, SETTINGS


class Algorithm(str, Enum):
    PPO = "ppo"
    APPO = "appo"
    SAC = "sac"


class Paradigm(str, Enum):
    CTCE = "ctce"
    CTDE = "ctde"
    DTDE = "dtde"


CONFIGS = {
    Algorithm.PPO: PPOConfig,
    Algorithm.APPO: APPOConfig,
    Algorithm.SAC: SACConfig,
}

# The settings themselves are in ``defaults.py`` (no Ray there, so the runner and the
# Studio can read them).
MODEL = dataclasses.asdict(DefaultModelConfig()) | NETWORK


def env_spec(
    paradigm: Paradigm, env_class: type, env_config: dict
) -> tuple[type, dict, list[str]]:
    """The environment the algorithm trains on, its config, and its agent ids."""
    if paradigm == Paradigm.DTDE:
        env = env_class(env_config)
        return env_class, env_config, list(env.agents_id)
    wrapped = {"env_class": env_class, "env_config": env_config}
    if paradigm == Paradigm.CTDE:
        return CentralStateEnv, wrapped, list(env_class(env_config).agents_id)
    return GroupedEnv, wrapped, [GROUP]


def build_config(
    algorithm: Algorithm | str,
    paradigm: Paradigm | str,
    env_class: type,
    env_config: Optional[dict] = None,
    *,
    seed: int = 0,
    training: Optional[dict[str, Any]] = None,
    num_env_runners: int = 0,
    num_gpus: int = 0,
    model: Optional[dict[str, Any]] = None,
) -> AlgorithmConfig:
    """The RLlib configuration of one run.

    Args:
        algorithm: PPO, APPO or SAC.
        paradigm: CTCE, CTDE or DTDE.
        env_class: A multi-agent environment built as ``env_class(env_config)``,
            with ``agents_id`` and one ``Box`` per agent.
        env_config: Its config.
        seed: Seed of RLlib (network initialisation, sampling, environment seeds).
        training: Overrides of ``SETTINGS``, passed to ``AlgorithmConfig.training``
            (e.g. ``lr=3e-4``, ``train_batch_size_per_learner=1000``).
        num_env_runners: Sampling processes besides the driver (0: sample in the
            driver). Learning always runs in the driver; nothing else starts
            processes (fixes the doubled CPU count of L-11).
        num_gpus: GPUs for the learner (0 or 1).
        model: Overrides of the network settings ``MODEL`` (the same for every
            paradigm).
    """
    algorithm, paradigm = Algorithm(algorithm), Paradigm(paradigm)
    env_config = dict(env_config or {})
    env, config_for_env, module_ids = env_spec(paradigm, env_class, env_config)
    model_config = MODEL | (model or {})

    config = (
        CONFIGS[algorithm]()
        .framework("torch")
        .environment(env=env, env_config=config_for_env)
        .env_runners(num_env_runners=num_env_runners, sample_timeout_s=None)
        .learners(num_learners=0, num_gpus_per_learner=num_gpus)
        .training(**(SETTINGS[algorithm] | (training or {})))
        .reporting(min_time_s_per_iteration=0)
        .debugging(seed=seed)
        .multi_agent(
            # In agent order: modules are built, and draw their initial weights, in
            # this order (a set would change it with every process).
            policies=list(module_ids),
            policy_mapping_fn=lambda agent_id, episode, **kwargs: agent_id,
        )
    )
    # The algorithm adds its own keys (e.g. SAC's twin_q) to config.model_config.
    config = config.rl_module(model_config=model_config)

    if paradigm == Paradigm.CTDE:
        central = CentralStateEnv(config_for_env)
        specs = {
            mid: RLModuleSpec(
                module_class=CTDE_MODULES[algorithm.value],
                model_config=config.model_config
                | {"own_obs_dim": central.own_dims[mid]},
            )
            for mid in module_ids
        }
    else:
        specs = {mid: RLModuleSpec() for mid in module_ids}
    return config.rl_module(rl_module_spec=MultiRLModuleSpec(rl_module_specs=specs))


def build_algo(config: AlgorithmConfig):
    """``config.build_algo()``, with every random generator following the seed.

    RLlib's ``debugging(seed=...)`` seeds Python, NumPy and torch, the networks and
    the environments, but RLlib 2.51 gives the episode replay buffer its own
    generator from OS entropy (``np.random.default_rng(seed=None)``), so SAC drew
    different replay batches in every run of the same seed. The buffer's generator
    is seeded here from the run's seed.
    """
    algo = config.build_algo()
    buffer = getattr(algo, "local_replay_buffer", None)
    if buffer is not None and hasattr(buffer, "rng"):
        buffer.rng = np.random.default_rng(config.seed)
    return algo
