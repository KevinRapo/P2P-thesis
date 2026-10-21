"""CTDE module: RLlib's own PPO module with a decentralised actor and a central critic.

CTDE here is MAPPO with one module per agent (no parameter sharing): each agent
keeps its own reward, its own critic and its own PPO clip, exactly as in DTDE. The
only difference from DTDE is what the networks see. Under ``CentralStateEnv``
(``grouping.py``) agent i observes ``[o_i, o_1, ..., o_N]``:

- the **actor** reads only ``o_i``, the first ``own_obs_dim`` entries, so the agent
  can act on its own observation after training (decentralised execution);
- the **critic** reads all of it, its own observation and the global state
  (centralised training): ``V_i(s)``.

The module is RLlib's default PPO module, with one change: the actor's encoder is
replaced by the encoder RLlib's catalog builds for the agent's own observation,
applied to its slice. The policy head, the action distribution (one per action
component, composite for the market's mixed action), the critic and the loss stay
RLlib's.

Fixes L-01 (the networks the loss trains are the networks that act) and the
deviations from standard multi-agent PPO of the earlier grouped CTDE: rewards,
advantages and the PPO clip are per agent.

model_config keys (besides RLlib's): ``own_obs_dim``, the size of the agent's own
observation.
"""

from __future__ import annotations

import torch
from gymnasium import spaces
from ray.rllib.algorithms.ppo.torch.default_ppo_torch_rl_module import (
    DefaultPPOTorchRLModule,
)
from ray.rllib.core.columns import Columns


class OwnObsEncoder(torch.nn.Module):
    """An RLlib encoder applied to the first ``dim`` entries of the observation.

    Takes and returns what an RLlib encoder does (``{OBS: ...}`` in,
    ``{ENCODER_OUT: ...}`` out).
    """

    def __init__(self, encoder: torch.nn.Module, dim: int) -> None:
        super().__init__()
        self.encoder = encoder
        self.dim = int(dim)

    def forward(self, inputs: dict, **kwargs) -> dict:
        return self.encoder({Columns.OBS: inputs[Columns.OBS][..., : self.dim]})


def own_encoder(module) -> OwnObsEncoder:
    """The encoder RLlib builds for the agent's own observation, on its slice."""
    dim = int(module.model_config["own_obs_dim"])
    space = module.observation_space
    if not isinstance(space, spaces.Box) or len(space.shape) != 1:
        raise ValueError(f"CTDE needs a flat Box observation space, got {space}.")
    own = spaces.Box(space.low[:dim], space.high[:dim], dtype=space.dtype)
    catalog = type(module.catalog)(own, module.action_space, dict(module.model_config))
    encoder = catalog.actor_critic_encoder_config.base_encoder_config.build(
        framework="torch"
    )
    return OwnObsEncoder(encoder, dim)


class CTDEPPOModule(DefaultPPOTorchRLModule):
    """RLlib's PPO module; the actor reads the agent's own observation only."""

    def setup(self):
        super().setup()
        self.encoder.actor_encoder = own_encoder(self)
