"""The bounded policy head (``core/rl/modules.py``): which outputs it changes, the
bounds it keeps, and that every paradigm builds and acts with it. Nothing is
trained."""

import numpy as np
import pytest
import torch
from gymnasium import spaces

from core.rl.config import build_algo, build_config
from core.rl.envs.probes import MixedActionProbe
from core.rl.modules import BoundedHead, continuous_slots, soft_clamp
from core.rl.train import learner_modules

UNIT = spaces.Box(-1.0, 1.0, (1,), np.float32)
MARKET = spaces.Dict(
    {
        "side": spaces.Discrete(2),
        "quantity": UNIT,
        "price": UNIT,
        "partner": spaces.Discrete(6),
    }
)


def test_continuous_slots_follow_rllibs_layout():
    """The market's 12 inputs in sorted order: partner 0-5, price mean 6 and log σ
    7, quantity mean 8 and log σ 9, side 10-11."""
    assert continuous_slots(MARKET) == ([6, 8], [7, 9])
    assert continuous_slots(spaces.Box(-1, 1, (3,), np.float32)) == (
        [0, 1, 2],
        [3, 4, 5],
    )
    assert continuous_slots(spaces.Discrete(4)) == ([], [])
    group = spaces.Tuple([MARKET, MARKET])  # CTCE: the second agent after the first
    assert continuous_slots(group) == ([6, 8, 18, 20], [7, 9, 19, 21])


def test_soft_clamp_stays_inside_and_keeps_a_gradient():
    x = torch.tensor([-50.0, -3.0, -1.5, 0.0, 30.0], requires_grad=True)
    y = soft_clamp(x, -3.0, 0.0)
    assert bool((y >= -3.0).all() and (y <= 0.0).all())
    y.sum().backward()
    assert bool((x.grad > 0).all())  # never 0, even far outside


class _Identity(torch.nn.Module):
    def forward(self, x, **kwargs):
        return x


def test_head_changes_only_the_continuous_parts():
    raw = torch.tensor([[5.0, -5.0, 1, 2, 3, 4, 9.0, 30.0, -9.0, -50.0, 7.0, -7.0]])
    means, log_stds = continuous_slots(MARKET)
    head = BoundedHead(_Identity(), means, log_stds, True, (-3.0, 0.0))
    out = head(raw)
    untouched = [0, 1, 2, 3, 4, 5, 10, 11]  # partner and side logits
    assert torch.equal(out[0, untouched], raw[0, untouched])
    assert bool((out[0, means].abs() < 1).all())  # tanh
    assert bool((out[0, log_stds] >= -3).all() and (out[0, log_stds] <= 0).all())


def test_free_log_std_is_one_parameter_for_every_state():
    means, log_stds = continuous_slots(MARKET)
    head = BoundedHead(_Identity(), means, log_stds, free_log_std=True)
    out = head(torch.randn(4, 12))
    assert torch.equal(out[:, log_stds], torch.zeros(4, 2))  # starts at log σ = 0
    assert head.free_log_std.requires_grad


@pytest.mark.parametrize("paradigm", ["ctce", "ctde", "dtde"])
def test_every_paradigm_builds_with_the_bounded_head(paradigm):
    config = build_config(
        "ppo",
        paradigm,
        MixedActionProbe,
        {"n_agents": 2},
        model={"bound_mean": True, "log_std_bounds": [-3.0, 0.0]},
        training={"train_batch_size_per_learner": 64, "minibatch_size": 32},
    )
    algo = build_algo(config)

    try:
        for module in learner_modules(algo).values():
            assert isinstance(module.pi, BoundedHead)
        algo.train()  # samples and learns through it
    finally:
        algo.stop()
