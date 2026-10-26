"""RLlib's PPO learner, with the clip fraction logged.

``PPOLearner`` is RLlib's ``PPOTorchLearner`` unchanged: the loss and the update are
RLlib's own. It only logs, per module and update, ``clip_fraction``: the share of
samples whose probability ratio π_new / π_old lies outside [1 − ε, 1 + ε] (ε =
``clip_param``), the samples where PPO's clipped objective can stop the policy
gradient. CleanRL and Stable-Baselines log the same number, averaged over the
update; here, as RLlib's KL (``window=1``), the value reported for an iteration is
its last minibatch's, at the end of the update, where it is largest.

It matters most for CTCE, where one ratio covers every agent's action, so it is the
product of all the agents' ratios and leaves the range sooner than any single
agent's (L-02).
"""

from __future__ import annotations

from typing import Any

import torch
from ray.rllib.algorithms.ppo.torch.ppo_torch_learner import PPOTorchLearner
from ray.rllib.core.columns import Columns

CLIP_FRACTION = "clip_fraction"


class PPOLearner(PPOTorchLearner):
    """RLlib's PPO learner; also logs ``clip_fraction`` per module."""

    def compute_loss_for_module(
        self, *, module_id: str, config: Any, batch: dict, fwd_out: dict
    ) -> torch.Tensor:
        loss = super().compute_loss_for_module(
            module_id=module_id, config=config, batch=batch, fwd_out=fwd_out
        )

        with torch.no_grad():
            module = self.module[module_id].unwrapped()
            dist = module.get_train_action_dist_cls().from_logits(
                fwd_out[Columns.ACTION_DIST_INPUTS]
            )
            log_ratio = dist.logp(batch[Columns.ACTIONS]) - batch[Columns.ACTION_LOGP]
            clipped = (torch.exp(log_ratio) - 1.0).abs() > config.clip_param

            if Columns.LOSS_MASK in batch:
                clipped = clipped[batch[Columns.LOSS_MASK]]

            fraction = clipped.float().mean()

        self.metrics.log_value((module_id, CLIP_FRACTION), fraction, window=1)

        return loss
