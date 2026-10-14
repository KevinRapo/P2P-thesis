"""The market as an RL environment (``core/env/market_env.py``).

These tests check the translation between the agents and the market: spaces, the
order an action means, the reward, the end of the episode and the reproducibility
of the day draw. The market itself is validated elsewhere; here it is taken as
given.

Run with ``python -m pytest tests/test_market_env.py -q`` in the ``marlem`` conda
env. The first market reset of the process loads the SimBench network (~10 s); the
tests share one environment for that reason.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.env import OBS_NAMES, MarketEnv, net_position_policy, zero_policy

SCENARIO = (
    Path(__file__).resolve().parents[1] / "notebooks/scenarios/validate_market.json"
)
DAYS = ["2016-06-15", "2016-01-10"]
AGENTS = ["P1", "P2", "P3", "P4", "P5"]


@pytest.fixture(scope="module")
def env() -> MarketEnv:
    """One environment for the module (the slow first reset happens once)."""
    return MarketEnv({"scenario": str(SCENARIO), "days": DAYS})


def play(env: MarketEnv, policy, day: str):
    """One whole episode on ``day`` with ``policy``; returns the rewards as an
    array (steps x agents) and the records."""
    env.days, saved = [day], env.days
    obs, _ = env.reset()
    env.days = saved
    rewards, records = [], []
    while True:
        obs, r, terminated, _, _ = env.step(policy(obs))
        rewards.append([r[a] for a in env.agents_id])
        records.append(env.last_record)
        if terminated["__all__"]:
            return np.array(rewards), records


def random_actions(env: MarketEnv, rng: np.random.Generator) -> dict:
    return {a: rng.uniform(-1, 1, 2).astype(np.float32) for a in env.agents_id}


def first_step_where(env: MarketEnv, side: str):
    """Reset on the summer day and play zero actions until an agent can ``sell`` or
    ``buy``; returns that agent's id (the env is left at that step)."""
    env.days, saved = [DAYS[0]], env.days
    env.reset()
    env.days = saved
    zero = zero_policy(env)
    while not env.market.done:
        t = env.market.current_step
        for pid, p in env.market.participants.items():
            bound = p.max_sell_kwh(t) if side == "sell" else p.max_buy_kwh(t)
            if bound > 1e-3:
                return pid
        env.step(zero(None))
    raise AssertionError(f"nobody can {side} on {DAYS[0]}")


# --------------------------------------------------------------------------------------
# Spaces
# --------------------------------------------------------------------------------------
def test_spaces_and_observations(env):
    """One agent per participant in scenario order, observation of 16 numbers
    (``OBS_NAMES``), action of 2; observations stay finite and inside the space
    after the reset and after steps (the policy network expects both)."""
    assert env.agents_id == AGENTS
    assert env.agents == env.possible_agents == AGENTS
    assert len(OBS_NAMES) == 16
    for a in AGENTS:
        assert env.observation_spaces[a].shape == (16,)
        assert env.action_spaces[a].shape == (2,)

    rng = np.random.default_rng(0)
    obs, infos = env.reset(seed=0)
    assert set(infos) == set(AGENTS) and infos["P1"]["day"] in DAYS
    for step in range(6):
        for a in AGENTS:
            assert np.isfinite(obs[a]).all()
            assert obs[a].dtype == np.float32
            assert env.observation_spaces[a].contains(obs[a]), (a, step)
        obs, *_ = env.step(random_actions(env, rng))


# --------------------------------------------------------------------------------------
# Episodes
# --------------------------------------------------------------------------------------
def test_zero_episode_lasts_one_day(env):
    """A day of zero actions takes exactly ``n_steps`` steps; only the last one
    terminates (every agent and ``__all__``) and nothing is truncated: the day end
    is the real end of the task, not a cut."""
    zero = zero_policy(env)
    obs = env.reset(seed=1)[0]
    steps = 0
    while True:
        obs, _, terminated, truncated, _ = env.step(zero(obs))
        steps += 1
        assert not any(truncated.values())
        if steps < env.market.n_steps:
            assert not any(terminated.values())
        else:
            assert terminated["__all__"] and all(terminated[a] for a in AGENTS)
            break
    assert steps == env.market.n_steps == 24


def test_zero_actions_submit_no_orders(env):
    """The zero action is inside the dead zone: no order at all. Each agent's
    reward is then only what it had to import untraded, ``-utility * deferred /
    reward_scale`` (it earns nothing, and the import is charged)."""
    zero = zero_policy(env)
    obs = env.reset(seed=2)[0]
    utility = env.utility_price
    while True:
        obs, rewards, terminated, *_ = env.step(zero(obs))
        record = env.last_record
        assert len(record.orders) == 0
        for a in AGENTS:
            expected = -utility * record.participants[a].deferred_demand_kwh
            assert rewards[a] == pytest.approx(expected / env.reward_scale)
        if terminated["__all__"]:
            break


def test_reward_is_the_scaled_net_bill(env):
    """On random actions every agent's reward is ``(profit - utility * deferred
    demand) / reward_scale``, read from the market's own record; this is the
    definition the docstring gives for why profit alone is not enough."""
    rng = np.random.default_rng(3)
    env.reset(seed=3)
    for _ in range(8):
        _, rewards, _, _, infos = env.step(random_actions(env, rng))
        for a in AGENTS:
            o = env.last_record.participants[a]
            bill = o.profit - env.utility_price * o.deferred_demand_kwh
            assert rewards[a] == pytest.approx(bill / env.reward_scale)
            assert infos[a]["bill"] == pytest.approx(bill)
            assert infos[a]["profit"] == pytest.approx(o.profit)
            assert all(isinstance(v, float) for v in infos[a].values())


# --------------------------------------------------------------------------------------
# Action decoding
# --------------------------------------------------------------------------------------
def test_action_decoding_sell(env):
    """a0 = 1 offers everything the agent may sell (eq. 15a), up to the market's
    maximum order size; a1 = -1 asks the feed-in tariff and a1 = 1 the utility
    price. Checked on the orders as submitted, before any clearing. A value in the
    dead zone places no order."""
    pid = first_step_where(env, "sell")
    t = env.market.current_step
    bound = env.market.participants[pid].max_sell_kwh(t)
    expected = min(bound, env.market.scenario.market.max_quantity)
    fit, utility = env.feed_in_tariff, env.utility_price

    def order_for(a0: float, a1: float):
        env.step({pid: np.array([a0, a1], dtype=np.float32)})
        return [o for o in env.last_record.orders if o.agent_id == pid]

    # one order per step: the same agent is tried again at the next step
    (low,) = order_for(1.0, -1.0)
    assert not low.is_buy
    assert low.quantity == pytest.approx(expected, rel=1e-6)
    assert low.price == pytest.approx(fit)

    while env.market.participants[pid].max_sell_kwh(env.market.current_step) <= 1e-3:
        env.step({})
    t = env.market.current_step
    bound = env.market.participants[pid].max_sell_kwh(t)
    (high,) = order_for(1.0, 1.0)
    assert high.quantity == pytest.approx(min(bound, 100.0), rel=1e-6)
    assert high.price == pytest.approx(utility)

    assert order_for(0.049, 0.0) == []


def test_action_decoding_buy(env):
    """a0 = -1 asks for everything the agent may buy (eq. 15b), a0 = -0.525 half of
    it (the dead zone is rescaled away: (0.525 - 0.05) / 0.95 = 0.5)."""
    pid = first_step_where(env, "buy")
    p = env.market.participants[pid]
    t = env.market.current_step
    bound = p.max_buy_kwh(t)
    intent = env.decode(pid, np.array([-1.0, 0.0], dtype=np.float32))
    assert intent.is_buy and intent.quantity_kwh == pytest.approx(bound)
    assert intent.price == pytest.approx((env.feed_in_tariff + env.utility_price) / 2)
    half = env.decode(pid, np.array([-0.525, 0.0], dtype=np.float32))
    assert half.quantity_kwh == pytest.approx(bound / 2)
    # clipped to [-1, 1] first
    big = env.decode(pid, np.array([-5.0, 9.0], dtype=np.float32))
    assert big.quantity_kwh == pytest.approx(bound)
    assert big.price == pytest.approx(env.utility_price)


# --------------------------------------------------------------------------------------
# Reproducibility
# --------------------------------------------------------------------------------------
def test_same_seed_same_day_and_observations(env):
    """The same seed draws the same day and gives identical observations, in the
    same env reset twice and in a second env built with that seed; different seeds
    reach both days (the day draw is the only randomness of an episode)."""
    obs1, info1 = env.reset(seed=7)
    obs2, info2 = env.reset(seed=7)
    assert info1["P1"]["day"] == info2["P1"]["day"]
    for a in AGENTS:
        np.testing.assert_array_equal(obs1[a], obs2[a])

    other = MarketEnv({"scenario": str(SCENARIO), "days": DAYS, "seed": 7})
    assert other.energy_scale == env.energy_scale
    obs3, info3 = other.reset()
    assert info3["P1"]["day"] == info1["P1"]["day"]
    for a in AGENTS:
        np.testing.assert_array_equal(obs1[a], obs3[a])

    drawn = {env.reset(seed=s)[1]["P1"]["day"] for s in range(12)}
    assert drawn == set(DAYS)


# --------------------------------------------------------------------------------------
# Baselines
# --------------------------------------------------------------------------------------
def test_net_position_beats_zero(env):
    """The market's own bidding rule, read from the observation, gives actions in
    [-1, 1] and a total reward at least the zero policy's on both days: trading
    must beat spilling the surplus and paying the utility price for every import
    (otherwise the reward does not teach trading)."""
    for day in DAYS:
        zero_total = play(env, zero_policy(env), day)[0].sum()

        policy = net_position_policy(env)
        obs, _ = env.reset(seed=0)
        for a in policy(obs).values():
            assert a.shape == (2,) and (np.abs(a) <= 1.0).all()
        net_total, records = play(env, policy, day)
        net_total = net_total.sum()
        print(f"{day}: zero {zero_total:.3f}, net position {net_total:.3f}")
        assert any(r.p2p_kwh > 0 for r in records)
        assert net_total >= zero_total


# --------------------------------------------------------------------------------------
# RLlib
# --------------------------------------------------------------------------------------
def test_passes_rllib_environment_check(env):
    """RLlib's multi-agent environment check (reset, a sampled step, dict keys,
    rewards, terminations and infos per agent) runs without error. In Ray 2.51
    the check is ``check_multiagent_environments`` (``check_env`` no longer
    exists in ``ray.rllib.utils``)."""
    from ray.rllib.utils.pre_checks.env import check_multiagent_environments

    check_multiagent_environments(env)
