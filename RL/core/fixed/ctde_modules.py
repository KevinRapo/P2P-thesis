"""CTDE modules: RLlib's own modules, with the actor split into one network per agent.

CTDE is CTCE with a restricted actor (``docs/rl/training.md`` on the clean
branch): the group's policy is the product of the agents' policies, and agent
i's part may only look at agent i's observation,

    pi(a_1, ..., a_N | s) = prod_i pi_i(a_i | o_i).

So these modules are RLlib's default PPO, APPO and SAC modules for the grouped
agent (``core/fixed/grouping.py``), with one change: the actor's encoder and
head are replaced by N separate ones, each built by RLlib's own catalog for that
agent's observation and action space (the same network an agent gets in DTDE).
The critic is left as RLlib builds it, on the joint observation (and, for SAC,
the joint action). Everything an algorithm does (losses, ``rsample``, target
networks, log-std clipping, tanh squashing) stays RLlib's.

Fixes I-48: the networks the loss trains are the networks that act. Fixes R-01,
R-03, R-04 and R-05 as a consequence: the networks, the action distribution and
SAC's actor update are RLlib's, the same as in CTCE and DTDE.

model_config keys (besides RLlib's): ``agent_obs_dims`` and ``agent_act_dims``,
each agent's observation and action size in the environment's agent order.
"""

from __future__ import annotations

import numpy as np
import torch
from gymnasium import spaces
from ray.rllib.algorithms.appo.torch.default_appo_torch_rl_module import (
    DefaultAPPOTorchRLModule,
)
from ray.rllib.algorithms.ppo.torch.default_ppo_torch_rl_module import (
    DefaultPPOTorchRLModule,
)
from ray.rllib.algorithms.sac.torch.default_sac_torch_rl_module import (
    DefaultSACTorchRLModule,
)
from ray.rllib.core.columns import Columns
from ray.rllib.core.models.base import ENCODER_OUT

from RL.core.fixed.grouping import split_space


# --------------------------------------------------------------------------------------
# The per-agent actor: encoder and head
# --------------------------------------------------------------------------------------
class AgentEncoders(torch.nn.Module):
    """One encoder per agent; agent i's reads only its slice of the observation.

    Takes and returns what an RLlib encoder does (``{OBS: ...}`` in,
    ``{ENCODER_OUT: ...}`` out); the output is the agents' latents side by side.
    """

    def __init__(self, encoders: list[torch.nn.Module], obs_dims: list[int]) -> None:
        super().__init__()
        self.encoders = torch.nn.ModuleList(encoders)
        self.edges = [int(e) for e in np.cumsum([0, *obs_dims])]

    def forward(self, inputs: dict, **kwargs) -> dict:
        obs = inputs[Columns.OBS]
        latents = [
            encoder({Columns.OBS: obs[..., a:b]})[ENCODER_OUT]
            for encoder, a, b in zip(self.encoders, self.edges[:-1], self.edges[1:])
        ]
        return {ENCODER_OUT: torch.cat(latents, dim=-1)}


class AgentHeads(torch.nn.Module):
    """One policy head per agent, on that agent's latent only.

    Each head outputs ``[mean_i, log_std_i]``; they are rearranged into the layout
    RLlib's Gaussian distributions read for the joint action, ``[means of all
    agents, log-stds of all agents]``, in the environment's agent order.
    """

    def __init__(
        self,
        heads: list[torch.nn.Module],
        latent_dims: list[int],
        act_dims: list[int],
    ) -> None:
        super().__init__()
        self.heads = torch.nn.ModuleList(heads)
        self.edges = [int(e) for e in np.cumsum([0, *latent_dims])]
        self.act_dims = list(act_dims)

    def forward(self, latent: torch.Tensor, **kwargs) -> torch.Tensor:
        means, log_stds = [], []
        for head, a, b, dim in zip(
            self.heads, self.edges[:-1], self.edges[1:], self.act_dims
        ):
            out = head(latent[..., a:b])
            means.append(out[..., :dim])
            log_stds.append(out[..., dim:])
        return torch.cat(means + log_stds, dim=-1)


def agent_actors(module) -> tuple[AgentEncoders, AgentHeads]:
    """Build each agent's actor with the module's own catalog class and settings.

    Agent i's spaces are its slices of the group's joint spaces, so its network is
    the one RLlib builds for that agent alone (as in DTDE).
    """
    obs_dims = list(module.model_config["agent_obs_dims"])
    act_dims = list(module.model_config["agent_act_dims"])
    obs_spaces = split_space(module.observation_space, obs_dims)
    act_spaces = split_space(module.action_space, act_dims)
    encoders, heads, latent_dims = [], [], []
    for obs_space, act_space in zip(obs_spaces, act_spaces):
        catalog = type(module.catalog)(obs_space, act_space, dict(module.model_config))
        if hasattr(catalog, "actor_critic_encoder_config"):  # PPO, APPO
            config = catalog.actor_critic_encoder_config.base_encoder_config
            encoders.append(config.build(framework="torch"))
        else:  # SAC
            encoders.append(catalog.build_encoder(framework="torch"))
        heads.append(catalog.build_pi_head(framework="torch"))
        latent_dims.append(int(catalog.latent_dims[0]))
    return AgentEncoders(encoders, obs_dims), AgentHeads(heads, latent_dims, act_dims)


def _check_spaces(module) -> None:
    for name, space in (
        ("observation", module.observation_space),
        ("action", module.action_space),
    ):
        if not isinstance(space, spaces.Box) or len(space.shape) != 1:
            raise ValueError(f"CTDE needs a flat Box {name} space, got {space}.")


# --------------------------------------------------------------------------------------
# The three CTDE modules
# --------------------------------------------------------------------------------------
class CTDEPPOModule(DefaultPPOTorchRLModule):
    """RLlib's PPO module with a per-agent actor and the central critic."""

    def setup(self):
        super().setup()
        _check_spaces(self)
        self.encoder.actor_encoder, self.pi = agent_actors(self)


class CTDEAPPOModule(DefaultAPPOTorchRLModule):
    """RLlib's APPO module with a per-agent actor and the central critic.

    The target policy is copied from this actor by the learner after ``setup``,
    so it is split per agent too.
    """

    def setup(self):
        super().setup()
        _check_spaces(self)
        self.encoder.actor_encoder, self.pi = agent_actors(self)


class CTDESACModule(DefaultSACTorchRLModule):
    """RLlib's SAC module with a per-agent actor and the central twin Q-critics.

    The Q-networks see the joint observation and the joint action; SAC's actor
    loss reaches each agent's network through its own part of the reparameterised
    joint action.
    """

    def setup(self):
        super().setup()
        _check_spaces(self)
        self.pi_encoder, self.pi = agent_actors(self)


CTDE_MODULES = {"ppo": CTDEPPOModule, "appo": CTDEAPPOModule, "sac": CTDESACModule}
