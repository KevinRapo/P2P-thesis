"""CTDE: what each network may see, checked on the built modules (nothing trained).

CTDE keeps one module per agent. The actor must read only the agent's own
observation (decentralised execution); the critic reads the global state too
(centralised training). These tests build the CTDE PPO modules and probe them.
"""

import numpy as np
import pytest
import ray
import torch
from ray.rllib.core.columns import Columns

from core.rl.envs.probes import ActionProbe
from core.rl.config import build_config
from core.rl.ctde import CTDEEnv, central_obs
from core.rl.train import learner_modules

CONFIG = {"n_agents": 3, "scramble_ids": True}
SMALL = {"train_batch_size_per_learner": 64, "minibatch_size": 32, "num_epochs": 1}


@pytest.fixture(scope="module", autouse=True)
def ray_session():
    ray.init(num_cpus=1, include_dashboard=False, log_to_driver=False)
    yield
    ray.shutdown()


def test_central_state_layout():
    """Each agent observes its own observation first, then every agent's in
    environment order, and keeps its own reward."""
    env = CTDEEnv({"env_class": ActionProbe, "env_config": CONFIG})
    obs, _ = env.reset(seed=3)
    raw = ActionProbe(CONFIG).reset(seed=3)[0]

    for a in env.agents_id:
        expected = np.concatenate([raw[a], *[raw[b] for b in env.agents_id]])
        np.testing.assert_array_equal(obs[a], expected)
        assert env.own_dims[a] == 1

    np.testing.assert_array_equal(
        obs[env.agents_id[0]], central_obs(raw, env.agents_id)[env.agents_id[0]]
    )
    actions = {a: np.array([t], np.float32) for a, t in env.env.targets.items()}
    _, rewards, *_ = env.step(actions)
    assert all(r == pytest.approx(1.0) for r in rewards.values()), rewards


def test_actor_is_local_critic_is_central():
    """One CTDE module per agent; its action output ignores the global-state part
    of the input, and its value depends on it."""
    algo = build_config("ppo", "ctde", ActionProbe, CONFIG, training=SMALL).build_algo()
    try:
        modules = learner_modules(algo)
        agents = ActionProbe(CONFIG).agents_id
        assert sorted(modules.keys()) == sorted(agents)
        module = modules[agents[0]]
        assert type(module).__name__.startswith("CTDE")
        base = torch.zeros(1, 4)
        other = base.clone()
        other[0, 1:] = 0.9  # the global-state part only
        own = base.clone()
        own[0, 0] = 0.9  # the agent's own observation

        def actor(x):
            with torch.no_grad():
                return module.forward_inference({Columns.OBS: x})[
                    Columns.ACTION_DIST_INPUTS
                ]

        assert torch.equal(actor(base), actor(other)), "actor reads the global state"
        assert not torch.equal(actor(base), actor(own)), "actor ignores its own obs"

        with torch.no_grad():
            v0 = module.compute_values({Columns.OBS: base})
            v1 = module.compute_values({Columns.OBS: other})

        assert not torch.equal(v0, v1), "critic ignores the global state"
    finally:
        algo.stop()
