"""The RL layer's default settings, without importing Ray or torch.

``core/rl/config.py`` builds every run from these; the runner reads them to write an
experiment out in full (``core.runner.spec.written_out``), so the Studio can show
every setting with its value without loading Ray.

- ``SETTINGS``: the hyperparameters per algorithm (V2: PPO only), passed to
  ``AlgorithmConfig.training``; an experiment's ``training`` overrides them. Any
  other key of RLlib's ``training()`` may be given too and then has RLlib's default
  until it is. The record of a run (``run.json``) holds every PPO setting with the
  value it ran with, given or default (``core/rl/train.py``).
- ``NETWORK``: the network settings that apply to the fully connected modules every
  paradigm uses, with RLlib's default values (a test compares them) except
  ``vf_share_layers``. ``config.MODEL`` is RLlib's ``DefaultModelConfig`` with these
  on top; an experiment's ``model`` overrides them.
"""

from __future__ import annotations

from typing import Any

# The original's starting hyperparameters ([P2] Table 8), less the defective ones;
# ``config.py`` says which and why. The learning rate, batch, minibatch and epochs
# chosen on the probes (RP-6b, docs/plan/decisions.md): the original's (1e-5, one
# minibatch of 4000, 5 epochs) learned none of the probes within 4 times their
# budget; these (Stable-Baselines3's PPO defaults, with a smaller batch) pass every
# probe in CTDE and DTDE.
SETTINGS: dict[str, dict[str, Any]] = {
    "ppo": {
        "lr": 3e-4,
        "gamma": 0.99,
        "grad_clip": 0.5,
        "train_batch_size_per_learner": 500,
        "minibatch_size": 64,
        "num_epochs": 10,
        # PPO only
        "lambda_": 0.95,
        "entropy_coeff": 0.01,
        "clip_param": 0.2,
        # The KL between the collecting and the updated policy is computed and
        # logged (mean_kl_loss), with weight 0 in the loss: a step-size gauge.
        "use_kl_loss": True,
        "kl_coeff": 0.0,
        "vf_clip_param": 1e6,
    },
}

# RLlib's default network for every paradigm, actor and critic separate (L-04).
NETWORK: dict[str, Any] = {
    "fcnet_hiddens": [256, 256],
    "fcnet_activation": "tanh",
    "head_fcnet_hiddens": [],
    "head_fcnet_activation": "relu",
    "free_log_std": False,
    "log_std_clip_param": 20.0,
    "vf_share_layers": False,
    # Our own (core/rl/modules.py, RP-3h): each continuous action part's mean
    # through tanh, and one learned log std per part for every state (MAPPO's).
    # Chosen on the probes (docs/rl/probes.md): RLlib's state-dependent log std
    # collapsed before the side it depends on was decided (probe 9: 0 of 9).
    "bound_mean": True,
    "log_std_bounds": None,
    "free_log_std_parts": True,
}
