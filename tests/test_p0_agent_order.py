"""Regression test for stable grouped-agent identity mapping (P0-10)."""

from gymnasium import spaces
from numpy import array, float32

import pytest

from src.environment.base import TrainingMode
from src.environment.train import GroupedLEM, RLTrainer
from utils import create_env_config


def test_grouped_tuple_spaces_follow_declared_agent_order() -> None:
    agent_order = ("agent_2", "agent_10")
    dict_space = spaces.Dict({
        "agent_10": spaces.Box(low=array([10.0], dtype=float32), high=array([11.0], dtype=float32), dtype=float32),
        "agent_2": spaces.Box(low=array([2.0], dtype=float32), high=array([3.0], dtype=float32), dtype=float32),
    })

    tuple_space = GroupedLEM._dict_to_tuple_space(dict_space, agent_order)

    assert tuple_space.spaces[0].low[0] == 2.0
    assert tuple_space.spaces[1].low[0] == 10.0


def test_ctde_training_is_explicitly_disabled_until_actor_training_is_valid() -> None:
    with pytest.raises(ValueError, match="CTDE is disabled"):
        RLTrainer(create_env_config(), training=TrainingMode.CTDE, iters=1, checkpoint_freq=1, cpus=1, gpus=0)
