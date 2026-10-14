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
separate actor and critic), which fixes R-03.

The hyperparameters start from the original's (``SETTINGS``, [P2] Table 8), with
the defects removed:

- PPO: ``use_kl_loss=False``, so the KL term is not computed at all (fixes R-02;
  the original set ``kl_coeff=0`` and kept it). ``vf_clip_param`` raised from
  RLlib's 10: RLlib caps the squared value error there, so an error above about
  3.2 would give the critic no gradient at all. Rewards should still be scaled by
  the environment to returns of order 1-10.
- APPO: no ``lambda_``; RLlib's V-trace has no lambda (fixes R-06).
- SAC: ``target_entropy="auto"`` (the negative action size of each module: the
  agent's in DTDE and CTDE, the group's in CTCE, as the original intended), a
  uniform replay buffer of 1000 steps for every paradigm. Episodes are sampled
  in fragments (RLlib's default), not ``complete_episodes`` as in the original:
  in that mode RLlib 2.51 resets the environment with the run's seed at every
  sample call, so with a seed every SAC training step would replay the same
  episode.
- No population-based training and no Ray Tune (fixes I-49 and part of I-62):
  one run has fixed hyperparameters and one seed; tuning and seeds are loops
  around ``core/fixed/train.py``.
- Iterations are not tied to wall-clock time (``min_time_s_per_iteration=0``),
  and the budget is counted in environment steps by the trainer (fixes I-50).
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any, Optional

from ray.rllib.algorithms.algorithm_config import AlgorithmConfig
from ray.rllib.algorithms.appo import APPOConfig
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.algorithms.sac import SACConfig
from ray.rllib.core.rl_module.default_model_config import DefaultModelConfig
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModuleSpec
from ray.rllib.core.rl_module.rl_module import RLModuleSpec

from RL.core.fixed.grouping import GROUP, CentralStateEnv, GroupedEnv
from RL.core.fixed.ctde_modules import CTDE_MODULES


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

# The original's starting hyperparameters ([P2] Table 8), less the defective ones.
SETTINGS: dict[Algorithm, dict[str, Any]] = {
    Algorithm.PPO: {
        "lr": 1e-5,
        "gamma": 0.99,
        "lambda_": 0.95,
        "num_epochs": 30,
        "minibatch_size": 128,
        "entropy_coeff": 0.01,
        "clip_param": 0.2,
        "grad_clip": 0.5,
        "use_kl_loss": False,
        "vf_clip_param": 1e6,
    },
    Algorithm.APPO: {
        "lr": 1e-5,
        "gamma": 0.99,
        "entropy_coeff": 0.01,
        "grad_clip": 0.5,
        "use_kl_loss": False,
    },
    Algorithm.SAC: {
        "actor_lr": 1e-5,
        "critic_lr": 1e-5,
        "gamma": 0.99,
        "twin_q": True,
        "grad_clip": 0.5,
        "target_entropy": "auto",
        "replay_buffer_config": {
            "type": "MultiAgentEpisodeReplayBuffer",
            "capacity": 1000,
        },
    },
}

# RLlib's default network for every paradigm, actor and critic separate.
MODEL = dataclasses.asdict(DefaultModelConfig()) | {"vf_share_layers": False}


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
            processes (fixes the doubled CPU count of I-62).
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
            policies=set(module_ids),
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
