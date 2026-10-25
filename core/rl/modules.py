"""RLlib's PPO module with the continuous action parts kept in bounds.

RLlib's policy head outputs, per module, each action part's distribution inputs
one after the other (``action_parts``): ``n`` logits for a ``Discrete`` part, a
mean and a log σ for each dimension of a ``Box`` part. Nothing bounds a ``Box``
part's mean, and for a ``Dict`` or ``Tuple`` action RLlib does not clip its log σ
either (its clip splits the whole output in half, which only fits a single
``Box``; ``PPOCatalog.build_pi_head`` switches it off otherwise).

``PPOModule`` is RLlib's ``DefaultPPOTorchRLModule`` with its policy head wrapped
(``BoundedHead``). Every option is off by default (the head is then RLlib's own):

    bound_mean       mean = tanh(raw): the mean of a continuous part stays inside
                     (-1, 1), the action's bounds in the network's units, so it
                     cannot settle beyond them, where the clipped action makes the
                     reward flat
    log_std_bounds   [low, high]: each continuous part's log σ kept in the range,
                     smoothly (softplus at each end: nearly the raw value inside,
                     never a zero gradient at the edge)
    free_log_std     one learned log σ per continuous dimension, the same in every
                     state (MAPPO's DiagGaussian, CleanRL, Stable-Baselines),
                     instead of the head's state-dependent one; starts at 0 (σ = 1)

The categorical logits always pass unchanged. The distribution stays RLlib's
(Gaussian, categorical, composite), so log-probabilities, entropy and the KL are
computed as before. All paradigms use this module; CTDE's
(``core/rl/ctde.CTDEPPOModule``) adds its own-observation actor on top.

Decided in RP-3h (``docs/plan/decisions.md``); evidence: probe 9's collapsing log σ
and the mean beyond the bounds (``docs/rl/probes.md``).
"""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np
import torch
import tree
from gymnasium import spaces
from ray.rllib.algorithms.ppo.torch.default_ppo_torch_rl_module import (
    DefaultPPOTorchRLModule,
)
from ray.rllib.utils.spaces.space_utils import get_base_struct_from_space

# The module's settings in ``model_config`` (core/rl_defaults.NETWORK holds their
# defaults: all off).
BOUND_MEAN = "bound_mean"
LOG_STD_BOUNDS = "log_std_bounds"
FREE_LOG_STD = "free_log_std_parts"


# --------------------------------------------------------------------------------------
# The layout of a module's distribution inputs
# --------------------------------------------------------------------------------------
def action_parts(
    space: spaces.Space, agents: Optional[Sequence[str]] = None
) -> list[tuple[str, spaces.Space, int]]:
    """The leaf parts of one module's action space, in the order RLlib cuts the
    module's distribution inputs into them (``TorchMultiDistribution``: dm-tree's
    flattening of the space's structure, a ``Dict``'s keys sorted), each with its
    name and its number of inputs: ``n`` for a ``Discrete``, a mean and a log σ per
    dimension for a ``Box``. A ``Tuple`` of agents' actions (CTCE) names each part
    after its agent, ``agent.part``."""
    struct = get_base_struct_from_space(space)

    if isinstance(struct, spaces.Space):
        paths = [((), struct)]
    else:
        paths = tree.flatten_with_path(struct)

    out = []

    for path, part in paths:
        names = [str(k) for k in path]
        if agents is not None and names:
            names[0] = agents[int(names[0])]
        if isinstance(part, spaces.Discrete):
            size = int(part.n)
        else:
            size = 2 * int(np.prod(part.shape))

        out.append((".".join(names) or "action", part, size))

    return out


def continuous_slots(space: spaces.Space) -> tuple[list[int], list[int]]:
    """The positions of every continuous part's means and log σ in the module's
    distribution inputs: ``(means, log_stds)``. A ``Box`` part of ``d`` dimensions
    takes ``2d`` inputs, its means first (RLlib's ``TorchDiagGaussian``)."""
    means, log_stds, start = [], [], 0

    for _, part, size in action_parts(space):
        if not isinstance(part, spaces.Discrete):
            half = size // 2
            means += range(start, start + half)
            log_stds += range(start + half, start + size)
        start += size

    return means, log_stds


# --------------------------------------------------------------------------------------
# The policy head, bounded
# --------------------------------------------------------------------------------------
def soft_clamp(x: torch.Tensor, low: float, high: float) -> torch.Tensor:
    """``x`` kept in ``[low, high]`` smoothly: a softplus at each end, so the
    gradient never becomes 0, rescaled so the range is exactly ``[low, high]``.
    Well inside the range the value is close to ``x`` (``x = 0`` gives about
    ``-0.6`` for ``[-3, 0]``)."""
    softplus = torch.nn.functional.softplus
    width = high - low
    # The two softplus steps reach low at -inf and low + softplus(width) at +inf.
    top = float(softplus(torch.tensor(width)))
    y = low + softplus(high - softplus(high - x) - low)

    return low + (y - low) * (width / top)


class BoundedHead(torch.nn.Module):
    """RLlib's policy head, with the continuous parts' outputs transformed (see
    the module docstring); the categorical logits pass unchanged.

    Args:
        head: RLlib's policy head (a ``Model`` returning the distribution inputs).
        means: Positions of the continuous parts' means (``continuous_slots``).
        log_stds: Positions of their log σ.
        bound_mean: Pass the means through tanh.
        log_std_bounds: ``(low, high)`` for the log σ, or ``None``.
        free_log_std: Replace the log σ by one learned parameter per position.
    """

    def __init__(
        self,
        head: torch.nn.Module,
        means: list[int],
        log_stds: list[int],
        bound_mean: bool = False,
        log_std_bounds: Optional[Sequence[float]] = None,
        free_log_std: bool = False,
    ) -> None:
        super().__init__()
        self.head = head
        self.register_buffer("means", torch.tensor(means, dtype=torch.long))
        self.register_buffer("log_stds", torch.tensor(log_stds, dtype=torch.long))
        self.bound_mean = bool(bound_mean)
        self.log_std_bounds = tuple(log_std_bounds) if log_std_bounds else None
        self.free_log_std = (
            torch.nn.Parameter(torch.zeros(len(log_stds))) if free_log_std else None
        )

    def forward(self, inputs: torch.Tensor, **kwargs) -> torch.Tensor:
        out = self.head(inputs, **kwargs)

        if not len(self.means):
            return out

        out = out.clone()

        if self.bound_mean:
            out[..., self.means] = torch.tanh(out[..., self.means])

        if self.free_log_std is not None:
            out[..., self.log_stds] = self.free_log_std.expand_as(
                out[..., self.log_stds]
            )

        if self.log_std_bounds is not None:
            low, high = self.log_std_bounds
            out[..., self.log_stds] = soft_clamp(out[..., self.log_stds], low, high)

        return out


def bounded_head(module) -> Optional[BoundedHead]:
    """The module's policy head wrapped as its ``model_config`` asks, or ``None``
    when every option is off (the head stays RLlib's)."""
    config = module.model_config
    bound_mean = bool(config.get(BOUND_MEAN))
    bounds = config.get(LOG_STD_BOUNDS)
    free = bool(config.get(FREE_LOG_STD))

    if not (bound_mean or bounds or free):
        return None

    means, log_stds = continuous_slots(module.action_space)

    return BoundedHead(module.pi, means, log_stds, bound_mean, bounds, free)


class PPOModule(DefaultPPOTorchRLModule):
    """RLlib's PPO module; the policy head bounded as its ``model_config`` asks."""

    def setup(self):
        super().setup()
        head = bounded_head(self)

        if head is not None:
            self.pi = head
