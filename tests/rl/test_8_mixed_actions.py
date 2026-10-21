"""Mixed actions (a categorical and a continuous part) in every paradigm.

The market's action is a ``Dict`` of categorical and continuous parts; probe 6,
``MixedActionProbe``, is the smallest environment with the same kind of action
(``choice``: Discrete(3), ``level``: Box(1)). These tests check, on built modules
and constructed batches (nothing is trained to convergence here; the training
check is ``scripts/probe_ppo.py``):

- the probe's optima and its reward routing;
- CTCE: the group's ``Tuple`` action goes back to each agent unchanged, in agent
  order, and the group acts with one composite distribution;
- CTDE: the actor reads the agent's own observation only, the critic the global
  state; DTDE and CTDE keep one value per agent, CTCE one for the group;
- PPO clips the ratio of each agent's whole action (all its parts) in DTDE and
  CTDE, and one ratio of the joint action in CTCE;
- the action RLlib's sampler sends to the environment is the action ``Policy``
  takes, and a restored checkpoint acts as the policy that was trained.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
import ray
import torch
from ray.rllib.core.columns import Columns
from ray.rllib.evaluation.postprocessing import Postprocessing

from core.rl import Run, load_policy, train
from core.rl.config import build_algo, build_config
from core.rl.envs.probes import MixedActionProbe
from core.rl.grouping import GROUP, CentralStateEnv, GroupedEnv, ungroup
from core.rl.policy import Policy, evaluation, to_env
from core.rl.train import learner_modules

CONFIG = {"n_agents": 3, "scramble_ids": True}
SMALL = {"train_batch_size_per_learner": 64, "minibatch_size": 32, "num_epochs": 1}
# Only the clipped surrogate in the loss, so it can be computed by hand.
SURROGATE_ONLY = SMALL | {"entropy_coeff": 0.0, "vf_loss_coeff": 0.0}


@pytest.fixture(scope="module", autouse=True)
def ray_session():
    ray.init(num_cpus=1, include_dashboard=False, log_to_driver=False)
    yield
    ray.shutdown()


def build(paradigm: str, training: dict = SMALL, env_class=MixedActionProbe):
    return build_algo(
        build_config("ppo", paradigm, env_class, CONFIG, seed=3, training=training)
    )


# --------------------------------------------------------------------------------------
# The probe
# --------------------------------------------------------------------------------------
def test_mixed_probe_optima_and_routing():
    """The best action (category c_i, level t_i) earns 2; the categories and
    levels differ per agent, so an agent given another's best action loses."""
    env = MixedActionProbe(CONFIG)
    env.reset(seed=0)
    best = env.best()
    _, rewards, *_ = env.step(best)
    assert all(r == pytest.approx(2.0) for r in rewards.values()), rewards
    assert len(set(env.choices.values())) == 3
    first, middle, last = env.agents_id
    swapped = dict(best)
    swapped[first], swapped[last] = best[last], best[first]
    env.reset(seed=0)
    _, rewards, *_ = env.step(swapped)
    assert rewards[middle] == pytest.approx(2.0)
    assert rewards[first] < 1.0 and rewards[last] < 1.0  # wrong category and level


# --------------------------------------------------------------------------------------
# CTCE: the Tuple of the agents' actions
# --------------------------------------------------------------------------------------
def test_ctce_group_action_round_trip():
    """GroupedEnv's action space is the agents' own spaces as a ``Tuple`` in
    environment order (not sorted); a group action reaches each agent as its own
    part, unchanged, and the group's reward is the sum of the agents'."""
    grouped = GroupedEnv({"env_class": MixedActionProbe, "env_config": CONFIG})
    inner = grouped.env
    space = grouped.action_spaces[GROUP]
    assert list(space.spaces) == [inner.action_spaces[a] for a in inner.agents_id]
    assert list(inner.agents_id) != sorted(inner.agents_id)
    best = inner.best()
    joint = tuple(best[a] for a in inner.agents_id)
    assert space.contains(joint)
    back = ungroup(joint, inner.agents_id)
    for a in inner.agents_id:
        assert back[a]["choice"] == best[a]["choice"]
        np.testing.assert_array_equal(back[a]["level"], best[a]["level"])
    grouped.reset(seed=0)
    _, rewards, *_, infos = grouped.step({GROUP: joint})
    assert rewards[GROUP] == pytest.approx(2.0 * len(inner.agents_id))
    assert infos[GROUP]["rewards"] == {a: pytest.approx(2.0) for a in inner.agents_id}
    with pytest.raises(ValueError, match="parts for"):
        ungroup(joint[:2], inner.agents_id)


def test_ctce_policy_acts_per_agent_from_one_distribution():
    """CTCE has one module; its composite distribution has one part per agent and
    action part, its log-probability is one number per sample (the joint action's),
    and ``Policy`` gives each agent a ``Dict`` action inside its own space."""
    algo = build("ctce")
    try:
        modules = learner_modules(algo)
        assert list(modules.keys()) == [GROUP]
        env = MixedActionProbe(CONFIG)
        obs, _ = env.reset(seed=0)
        module = modules[GROUP]
        x = torch.zeros(4, len(env.agents_id))
        with torch.no_grad():
            logits = module.forward_inference({Columns.OBS: x})[
                Columns.ACTION_DIST_INPUTS
            ]
        dist = module.get_inference_action_dist_cls().from_logits(logits)
        sample = dist.sample()
        assert isinstance(sample, tuple) and len(sample) == len(env.agents_id)
        assert dist.logp(sample).shape == (4,)  # one joint log-probability
        acts = Policy(modules, "ctce", env).act(obs)
        assert list(acts) == list(env.agents_id)
        for a, act in acts.items():
            assert env.action_spaces[a].contains(act), (a, act)
    finally:
        algo.stop()


# --------------------------------------------------------------------------------------
# CTDE: the actor reads the agent's own observation only
# --------------------------------------------------------------------------------------
def test_ctde_actor_ignores_central_inputs_with_mixed_actions():
    """With the mixed action, the CTDE actor's distribution inputs (every part's
    logits and means) do not move when only the global state changes, and do move
    with the agent's own observation; the critic reads the global state."""
    algo = build("ctde")
    try:
        modules = learner_modules(algo)
        env = CentralStateEnv({"env_class": MixedActionProbe, "env_config": CONFIG})
        for a in env.agents_id:
            module = modules[a]
            assert type(module).__name__ == "CTDEPPOModule"
            n = env.observation_spaces[a].shape[0]
            base = torch.zeros(1, n)
            central = base.clone()
            central[0, env.own_dims[a] :] = 0.8
            own = base.clone()
            own[0, : env.own_dims[a]] = 0.8
            with torch.no_grad():
                out = [
                    module.forward_inference({Columns.OBS: x})[
                        Columns.ACTION_DIST_INPUTS
                    ]
                    for x in (base, central, own)
                ]
                v_base = module.compute_values({Columns.OBS: base})
                v_central = module.compute_values({Columns.OBS: central})
            assert torch.equal(out[0], out[1]), f"{a}: actor reads the global state"
            assert not torch.equal(out[0], out[2]), f"{a}: actor ignores its own obs"
            assert not torch.equal(v_base, v_central), f"{a}: critic is not central"
    finally:
        algo.stop()


# --------------------------------------------------------------------------------------
# Rewards and values per agent (DTDE, CTDE) or for the group (CTCE)
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("paradigm", ["dtde", "ctde", "ctce"])
def test_rewards_and_values_are_routed_per_objective(paradigm):
    """DTDE and CTDE: one module, one value and one reward per agent (CentralStateEnv
    passes each agent's own reward through); CTCE: one module and one value for the
    group, whose reward is the sum."""
    algo = build(paradigm)
    try:
        env = MixedActionProbe(CONFIG)
        modules = learner_modules(algo)
        values = Policy(modules, paradigm, env).values(env.reset(seed=0)[0])
        if paradigm == "ctce":
            assert list(modules.keys()) == list(values) == [GROUP]
        else:
            assert list(modules.keys()) == list(env.agents_id) == list(values)
        if paradigm == "ctde":
            central = CentralStateEnv(
                {"env_class": MixedActionProbe, "env_config": CONFIG}
            )
            central.reset(seed=0)
            best = central.env.best()
            off = dict(best)
            first = central.agents_id[0]
            off[first] = {
                "choice": (best[first]["choice"] + 1) % 3,
                "level": best[first]["level"],
            }
            _, rewards, *_ = central.step(off)
            assert rewards[first] == pytest.approx(1.0)  # only its own reward falls
            assert all(rewards[a] == pytest.approx(2.0) for a in central.agents_id[1:])
    finally:
        algo.stop()


# --------------------------------------------------------------------------------------
# PPO's clip: one ratio per agent's whole action (DTDE, CTDE), one joint (CTCE)
# --------------------------------------------------------------------------------------
def _constructed_batch(module, actions, ratios, advantages):
    """A batch for ``module`` whose old log-probabilities make the given ratios
    of the whole (composite) action under the module's current weights."""
    n = len(advantages)
    obs = torch.zeros((n, module.observation_space.shape[0]))
    with torch.no_grad():
        fwd = module.forward_train({Columns.OBS: obs})
        dist = module.get_train_action_dist_cls().from_logits(
            fwd[Columns.ACTION_DIST_INPUTS]
        )
        logp = dist.logp(actions)
    batch = {
        Columns.OBS: obs,
        Columns.ACTIONS: actions,
        Columns.ACTION_DIST_INPUTS: fwd[Columns.ACTION_DIST_INPUTS],
        Columns.ACTION_LOGP: logp - torch.log(torch.tensor(ratios)),
        Postprocessing.ADVANTAGES: torch.tensor(advantages),
        Postprocessing.VALUE_TARGETS: torch.zeros(n),
    }
    return batch


def _expected(ratios, advantages, clip=0.2) -> float:
    surrogate = [
        min(a * r, a * min(max(r, 1 - clip), 1 + clip))
        for r, a in zip(ratios, advantages)
    ]
    return -sum(surrogate) / len(surrogate)


RATIOS = [1.15**2, 0.5, 1.5, 1.1]  # the first: 1.15 per part, 1.3225 for both
ADVANTAGES = [1.0, 1.0, -1.0, 1.0]


@pytest.mark.parametrize("paradigm", ["dtde", "ctde"])
def test_ppo_clips_each_agents_whole_action(paradigm):
    """On a constructed batch, RLlib's PPO loss of an agent's module equals the
    clipped surrogate computed by hand with the ratio of the agent's whole action:
    the first row's two parts each have ratio 1.15 (inside the clip range) but the
    action 1.3225, which is clipped to 1.2 (clipping each part would have left both
    unclipped). Another agent's batch changes nothing
    in this agent's loss: each agent has its own ratio and clip."""
    algo = build(paradigm, SURROGATE_ONLY)
    try:
        learner = algo.learner_group._learner
        modules = learner.module
        a, b = MixedActionProbe(CONFIG).agents_id[:2]
        actions = {
            "choice": torch.tensor([0, 1, 2, 0]),
            "level": torch.tensor([[0.1], [-0.3], [0.5], [0.0]]),
        }
        batches = {
            a: _constructed_batch(modules[a], actions, RATIOS, ADVANTAGES),
            b: _constructed_batch(modules[b], actions, [1.0] * 4, ADVANTAGES),
        }

        def loss(mid):
            fwd = modules[mid].forward_train({Columns.OBS: batches[mid][Columns.OBS]})
            return float(
                learner.compute_loss_for_module(
                    module_id=mid,
                    config=learner.config.get_config_for_module(mid),
                    batch=batches[mid],
                    fwd_out=fwd,
                )
            )

        assert loss(a) == pytest.approx(_expected(RATIOS, ADVANTAGES), abs=1e-5)
        assert loss(b) == pytest.approx(_expected([1.0] * 4, ADVANTAGES), abs=1e-5)
        before = loss(a)
        batches[b] = _constructed_batch(modules[b], actions, [3.0] * 4, ADVANTAGES)
        assert loss(a) == pytest.approx(before)
    finally:
        algo.stop()


def test_ctce_clips_one_joint_ratio():
    """CTCE: the group's loss uses one ratio for the joint action of all agents
    (here 1.1 per agent, 1.331 for the group, clipped to 1.2)."""
    algo = build("ctce", SURROGATE_ONLY)
    try:
        learner = algo.learner_group._learner
        module = learner.module[GROUP]
        part = {
            "choice": torch.tensor([0, 1]),
            "level": torch.tensor([[0.2], [-0.2]]),
        }
        actions = (part, part, part)
        ratios, advantages = [1.1**3, 0.9], [1.0, 1.0]
        batch = _constructed_batch(module, actions, ratios, advantages)
        fwd = module.forward_train({Columns.OBS: batch[Columns.OBS]})
        loss = learner.compute_loss_for_module(
            module_id=GROUP,
            config=learner.config.get_config_for_module(GROUP),
            batch=batch,
            fwd_out=fwd,
        )
        assert float(loss) == pytest.approx(-(1.2 + 0.9) / 2, abs=1e-5)
    finally:
        algo.stop()


# --------------------------------------------------------------------------------------
# The same action in training and in evaluation
# --------------------------------------------------------------------------------------
class RecordingProbe(MixedActionProbe):
    """Probe 6 that reports the action each agent received in its infos."""

    def step(self, action_dict):
        received = {a: action_dict[a] for a in self.agents_id}
        obs, rewards, terminateds, truncateds, _ = super().step(action_dict)
        return (
            obs,
            rewards,
            terminateds,
            truncateds,
            {a: {"received": received[a]} for a in self.agents_id},
        )


@pytest.mark.parametrize("paradigm", ["dtde", "ctde", "ctce"])
def test_sampler_and_policy_send_the_same_action(paradigm):
    """RLlib's sampler without exploration (its connectors, unsquashing and all)
    sends the environment exactly the action ``Policy`` computes from the
    learner's module for the same observation: one action semantics in training
    and in evaluation."""
    algo = build(paradigm, env_class=RecordingProbe)
    try:
        episodes = algo.env_runner.sample(num_episodes=1, explore=False)
        infos = episodes[0].get_infos(-1)
        if paradigm == "ctce":
            received = {a: i["received"] for a, i in infos[GROUP]["infos"].items()}
        else:
            received = {a: i["received"] for a, i in infos.items()}
        env = RecordingProbe(CONFIG)
        obs, _ = env.reset(seed=0)  # probe 6 always starts at observation 0
        acted = Policy(learner_modules(algo), paradigm, env).act(obs)
        for a in env.agents_id:
            assert int(received[a]["choice"]) == acted[a]["choice"], a
            np.testing.assert_allclose(
                np.asarray(received[a]["level"]).reshape(-1),
                acted[a]["level"],
                rtol=1e-6,
                atol=1e-7,
            )
    finally:
        algo.stop()


def test_to_env_rescales_only_continuous_parts():
    """``to_env`` rescales and clips a continuous part to its bounds (as RLlib's
    ``normalize_actions``) and leaves a categorical part as its index."""
    from gymnasium import spaces

    space = spaces.Dict(
        {"pick": spaces.Discrete(4), "x": spaces.Box(0.0, 10.0, (1,), np.float32)}
    )
    out = to_env({"pick": np.array(3), "x": np.array([0.0], np.float32)}, space)
    assert out["pick"] == 3 and isinstance(out["pick"], int)
    np.testing.assert_allclose(out["x"], [5.0])
    out = to_env({"pick": np.array(1), "x": np.array([7.0], np.float32)}, space)
    np.testing.assert_allclose(out["x"], [10.0])  # clipped


# --------------------------------------------------------------------------------------
# Checkpoints: the restored policy is the trained one
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("paradigm", ["dtde", "ctde", "ctce"])
def test_checkpoint_restores_the_trained_policy(paradigm, tmp_path):
    """A short run saves its checkpoint; ``load_policy`` restores modules in the
    run's agent order whose evaluation on the run's own seeds repeats the final
    evaluation the trainer wrote, to the last digit, and whose actions lie in each
    agent's space."""
    record = train(
        Run(
            "ppo",
            paradigm,
            MixedActionProbe,
            CONFIG,
            budget=64,
            seed=5,
            eval_episodes=3,
            training=SMALL,
            out_dir=tmp_path / paradigm,
        )
    )
    assert record["status"] == "completed"
    policy, saved = load_policy(record["out_dir"])
    env = MixedActionProbe(saved["env_config"])
    expected = list(env.agents_id) if paradigm != "ctce" else [GROUP]
    assert list(policy.modules.keys()) == expected
    found = evaluation(
        MixedActionProbe, saved["env_config"], {"trained": policy}, saved["eval_seeds"]
    )
    again = float(found.summary.set_index("policy").loc["trained", "team_return_mean"])
    assert again == record["final"]["team_return_mean"]
    obs, _ = env.reset(seed=0)
    for a, act in policy.act(obs).items():
        assert env.action_spaces[a].contains(act)
    assert saved["spaces"][env.agents_id[0]]["action"].startswith("Dict(")
    assert not math.isnan(saved["settings_effective"]["clip_param"])
