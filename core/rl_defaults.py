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

# The original's starting hyperparameters ([P2] Table 8), less the defective ones
# (``config.py`` says which and why).
SETTINGS: dict[str, dict[str, Any]] = {
    "ppo": {
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
}
