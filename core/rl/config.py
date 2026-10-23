"""The PPO configuration of one paradigm.

V2 uses RLlib's PPO only (APPO and SAC are not part of V2; V1 keeps them). Only
RLlib's algorithm, loss, modules and distributions are used; what changes between
paradigms is the environment PPO sees and, for CTDE, what the actor reads:

| Paradigm | Environment | Modules | Objective |
|---|---|---|---|
| DTDE | the multi-agent environment | one per agent, RLlib's default | own reward |
| CTDE | ``CTDEEnv``: o_i plus the global state | one per agent, actor on o_i, critic on everything (``ctde.py``) | own reward |
| CTCE | ``CTCEEnv``: one agent, joined observations, the agents' actions as one ``Tuple`` | one, RLlib's default | summed reward (social planner) |

DTDE and CTDE optimise the same individual objective and differ only in what the
critic sees, so a difference between them is the central critic's.

Every paradigm uses the same network settings (RLlib's defaults: 2 x 256 tanh,
separate actor and critic), which fixes L-04.

The hyperparameters start from the original's (``SETTINGS`` in
``core/rl_defaults.py``, [P2] Table 8), with the defects removed:

- ``use_kl_loss=False``, so the KL term is not computed at all (fixes L-07; the
  original set ``kl_coeff=0`` and kept it). ``vf_clip_param`` raised from RLlib's
  10: RLlib caps the squared value error there, so an error above about 3.2 would
  give the critic no gradient at all. Rewards should still be scaled by the
  environment to returns of order 1-10.
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

from ray.rllib.algorithms.algorithm_config import AlgorithmConfig
from ray.rllib.algorithms.ppo import PPOConfig
from ray.rllib.core.rl_module.default_model_config import DefaultModelConfig
from ray.rllib.core.rl_module.multi_rl_module import MultiRLModuleSpec
from ray.rllib.core.rl_module.rl_module import RLModuleSpec

from core.rl.ctce import GROUP, CTCEEnv
from core.rl.ctde import CTDEEnv, CTDEPPOModule
from core.rl_defaults import NETWORK, SETTINGS


class Algorithm(str, Enum):
    """The algorithms of V2: RLlib's PPO only (kept as a name, so runs and
    experiment files keep their ``algorithm`` field)."""

    PPO = "ppo"


class Paradigm(str, Enum):
    CTCE = "ctce"
    CTDE = "ctde"
    DTDE = "dtde"


CONFIGS = {Algorithm.PPO: PPOConfig}

# The settings themselves are in ``core/rl_defaults.py`` (no Ray there, so the runner and the
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
        return CTDEEnv, wrapped, list(env_class(env_config).agents_id)
    return CTCEEnv, wrapped, [GROUP]


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
        algorithm: ``"ppo"`` (the only one in V2).
        paradigm: CTCE, CTDE or DTDE.
        env_class: A multi-agent environment built as ``env_class(env_config)``,
            with ``agents_id``, a flat ``Box`` observation and any action space
            RLlib's catalog gives a distribution for (``Box``, ``Discrete`` and
            ``Dict`` / ``Tuple`` of them) per agent.
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
    config = config.rl_module(model_config=model_config)

    if paradigm == Paradigm.CTDE:
        central = CTDEEnv(config_for_env)
        specs = {
            mid: RLModuleSpec(
                module_class=CTDEPPOModule,
                model_config=config.model_config
                | {"own_obs_dim": central.own_dims[mid]},
            )
            for mid in module_ids
        }
    else:
        specs = {mid: RLModuleSpec() for mid in module_ids}
    return config.rl_module(rl_module_spec=MultiRLModuleSpec(rl_module_specs=specs))


def build_algo(config: AlgorithmConfig):
    """``config.build_algo()``: the one place runs are built, so anything a run
    needs besides RLlib's own build is added here. RLlib's ``debugging(seed=...)``
    seeds Python, NumPy and torch, the networks and the environments."""
    return config.build_algo()
