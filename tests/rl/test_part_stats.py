"""The per-part diagnostics (``policy.action_parts``, ``part_stats``): the parts are
cut from a module's outputs exactly as RLlib cuts them, and read per part."""

import numpy as np
import pytest
from gymnasium import spaces
from ray.rllib.algorithms.ppo.ppo_catalog import PPOCatalog
from ray.rllib.algorithms.ppo.torch.default_ppo_torch_rl_module import (
    DefaultPPOTorchRLModule,
)
from ray.rllib.core.models.catalog import Catalog
from ray.rllib.core.rl_module.rl_module import RLModuleSpec

from core.rl.config import MODEL
from core.rl.envs.probes import ConditionalPartProbe
from core.rl.policy import Policy, action_parts, observation_sample, part_stats

UNIT = spaces.Box(-1.0, 1.0, (1,), np.float32)
MARKET_LIKE = spaces.Dict(
    {
        "side": spaces.Discrete(2),
        "quantity": UNIT,
        "price": UNIT,
        "partner": spaces.Discrete(6),
    }
)


def test_parts_in_rllibs_order_and_sizes():
    """Sorted keys (partner, price, quantity, side), 6 + 2 + 2 + 2 = 12 inputs:
    what RLlib's composite distribution needs for this space."""
    parts = action_parts(MARKET_LIKE)
    assert [name for name, _, _ in parts] == ["partner", "price", "quantity", "side"]
    assert [size for _, _, size in parts] == [6, 2, 2, 2]

    rllib = Catalog._get_dist_cls_from_action_space(MARKET_LIKE, framework="torch")
    assert sum(size for _, _, size in parts) == rllib.required_input_dim(MARKET_LIKE)


def test_ctce_tuple_parts_are_named_after_their_agents():
    group = spaces.Tuple([MARKET_LIKE, MARKET_LIKE])
    names = [name for name, _, _ in action_parts(group, ["agent_2", "agent_10"])]
    parts = ["partner", "price", "quantity", "side"]
    assert names == [f"agent_2.{p}" for p in parts] + [f"agent_10.{p}" for p in parts]


def test_part_stats_of_an_untrained_module():
    """Every part gets its statistics; an untrained network's means are near 0,
    its spreads near σ = 1, its categories near uniform."""
    env = ConditionalPartProbe({"n_agents": 2})
    modules = {
        a: RLModuleSpec(
            module_class=DefaultPPOTorchRLModule,
            observation_space=env.observation_spaces[a],
            action_space=env.action_spaces[a],
            model_config=dict(MODEL),
            catalog_class=PPOCatalog,
        ).build()
        for a in env.agents_id
    }
    states = observation_sample(ConditionalPartProbe, {"n_agents": 2}, steps=16)
    assert len(states) == 16

    found = part_stats(Policy(modules, "dtde", env), states)
    first = env.agents_id[0]
    assert set(found) >= {
        f"{first}/level/mean",
        f"{first}/level/log_std",
        f"{first}/level/outside",
        f"{first}/side/entropy",
        f"{first}/side/top",
    }
    assert abs(found[f"{first}/level/mean"]) < 1.0
    assert 0.0 <= found[f"{first}/level/outside"] <= 1.0
    assert found[f"{first}/side/entropy"] == pytest.approx(np.log(2), abs=0.2)
