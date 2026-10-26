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

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
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
        obs, r, _, truncated, _ = env.step(policy(obs))
        rewards.append([r[a] for a in env.agents_id])
        records.append(env.last_record)

        if truncated["__all__"]:
            return np.array(rewards), records


def random_actions(env: MarketEnv, rng: np.random.Generator) -> dict:
    """A random mixed action per agent: side, quantity, price and partner."""
    return {
        a: {
            "side": int(rng.integers(2)),
            "quantity": rng.uniform(-1, 1, 1).astype(np.float32),
            "price": rng.uniform(-1, 1, 1).astype(np.float32),
            "partner": int(rng.integers(len(AGENTS) + 1)),
        }
        for a in env.agents_id
    }


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
    """One agent per participant in scenario order. The observation: the paper's
    42 signals (``OBS_NAMES``: 16 market, 16 agent, 10 KPIs), then the N − 1 peers'
    reputations (42 + 4 = 46 with five agents). The action: the four parts of [P1] eq. 2,
    side Discrete(2), quantity and price Box(1), partner Discrete(N + 1).
    Observations stay finite and inside the space after the reset and after steps
    (the policy network expects both)."""
    assert env.agents_id == AGENTS
    assert env.agents == env.possible_agents == AGENTS
    assert len(OBS_NAMES) == 42
    assert env.obs_names[:42] == OBS_NAMES and len(env.obs_names) == 46

    for a in AGENTS:
        assert env.observation_spaces[a].shape == (46,)
        space = env.action_spaces[a]
        assert set(space.spaces) == {"side", "quantity", "price", "partner"}
        assert space["side"].n == 2 and space["partner"].n == len(AGENTS) + 1
        assert space["quantity"].shape == space["price"].shape == (1,)

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
    truncates (every agent and ``__all__``) and nothing terminates: the market goes
    on after midnight, so the return bootstraps from the final observation."""
    zero = zero_policy(env)
    obs = env.reset(seed=1)[0]
    steps = 0

    while True:
        obs, _, terminated, truncated, _ = env.step(zero(obs))
        steps += 1
        assert not any(terminated.values())

        if steps < env.market.n_steps:
            assert not any(truncated.values())
        else:
            assert truncated["__all__"] and all(truncated[a] for a in AGENTS)
            break

    assert steps == env.market.n_steps == 24


def test_zero_actions_submit_no_orders(env):
    """The zero policy's quantity share is 0, below the no-order threshold: no
    order at all. Each agent's
    reward is then only what it had to import untraded, ``-utility * deferred /
    reward_scale`` (it earns nothing, and the import is charged)."""
    zero = zero_policy(env)
    obs = env.reset(seed=2)[0]

    while True:
        obs, rewards, _, truncated, _ = env.step(zero(obs))
        record = env.last_record
        assert len(record.orders) == 0
        utility = record.inputs.utility_price  # the step's

        for a in AGENTS:
            expected = -utility * record.participants[a].deferred_demand_kwh
            assert rewards[a] == pytest.approx(expected / env.reward_scale)

        if truncated["__all__"]:
            break


def test_reset_plays_the_day_asked_for(env):
    _, infos = env.reset(seed=0, options={"day": DAYS[-1]})
    assert infos["P1"]["day"] == DAYS[-1]
    with pytest.raises(ValueError, match="not one of the environment's days"):
        env.reset(options={"day": "2016-12-31"})


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
            bill = (
                o.profit - env.last_record.inputs.utility_price * o.deferred_demand_kwh
            )
            assert rewards[a] == pytest.approx(bill / env.reward_scale)
            assert infos[a]["bill"] == pytest.approx(bill)
            assert infos[a]["profit"] == pytest.approx(o.profit)
            nested = {"state", "shared", "shared_state"}  # core/rl/policy.py
            assert set(infos[a]) >= nested
            assert all(
                isinstance(v, float) for k, v in infos[a].items() if k not in nested
            )
            labels = {"side", "partner"}  # the trace's labels; the rest numbers

            for part in nested:
                assert all(
                    isinstance(v, str if k in labels else float)
                    for k, v in infos[a][part].items()
                )

            shared = infos[a]["shared"]
            assert shared["p2p_kwh"] == pytest.approx(env.last_record.p2p_kwh)
            assert shared["bought_from_dso_kwh"] == pytest.approx(
                env.last_record.dso.sold_kwh
            )


# --------------------------------------------------------------------------------------
# Action decoding
# --------------------------------------------------------------------------------------
def action(side: int, quantity: float, price: float, partner: int) -> dict:
    return {
        "side": side,
        "quantity": np.array([quantity], dtype=np.float32),
        "price": np.array([price], dtype=np.float32),
        "partner": partner,
    }


def test_action_decoding_sell(env):
    """side 0 sells; quantity 1 offers everything the agent may sell (eq. 15a), up
    to the market's maximum order size; price -1 asks the feed-in tariff and +1
    the utility price. Checked on the orders as submitted, before any clearing. A
    quantity share below the no-order threshold places no order."""
    pid = first_step_where(env, "sell")
    t = env.market.current_step
    bound = env.market.participants[pid].max_sell_kwh(t)
    expected = min(bound, env.market.scenario.market.max_quantity)
    fit, utility = (
        env.market.dso.feed_in_tariff,
        env.market.dso.utility_price,
    )  # the step's
    none = len(AGENTS)  # the last partner index: no preference

    def order_for(q: float, p: float):
        env.step({pid: action(0, q, p, none)})
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

    # share (q + 1) / 2 = 0.049 is below the threshold 0.05: no order
    assert order_for(2 * 0.049 - 1, 0.0) == []


def test_action_decoding_buy(env):
    """side 1 buys; quantity 1 asks for everything the agent may buy (eq. 15b);
    share (q + 1) / 2 = 0.525 is half of it (the threshold is rescaled away:
    (0.525 - 0.05) / 0.95 = 0.5)."""
    pid = first_step_where(env, "buy")
    p = env.market.participants[pid]
    t = env.market.current_step
    bound = p.max_buy_kwh(t)
    intent = env.decode(pid, action(1, 1.0, 0.0, 0))
    assert intent.is_buy and intent.quantity_kwh == pytest.approx(bound)
    assert intent.price == pytest.approx(
        (env.market.dso.feed_in_tariff + env.market.dso.utility_price) / 2
    )
    half = env.decode(pid, action(1, 2 * 0.525 - 1, 0.0, 0))
    assert half.quantity_kwh == pytest.approx(bound / 2)
    # continuous parts are clipped to [-1, 1] first
    big = env.decode(pid, action(1, 5.0, 9.0, 0))
    assert big.quantity_kwh == pytest.approx(bound)
    assert big.price == pytest.approx(env.market.dso.utility_price)
    # encode is decode's inverse for baselines and tests
    again = env.decode(pid, env.encode(pid, "buy", 0.5, 1.0))
    assert again.quantity_kwh == pytest.approx(bound / 2, rel=1e-5)
    assert again.price == pytest.approx(env.market.dso.utility_price)

    with pytest.raises(ValueError, match="outside its space"):
        env.decode(pid, action(2, 1.0, 0.0, 0))


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
    """The market's own bidding rule, read from the observation, gives actions
    inside the action space and a total reward at least the zero policy's on both
    days: trading
    must beat spilling the surplus and paying the utility price for every import
    (otherwise the reward does not teach trading)."""
    for day in DAYS:
        zero_total = play(env, zero_policy(env), day)[0].sum()

        policy = net_position_policy(env)
        obs, _ = env.reset(seed=0)

        for a, act in policy(obs).items():
            assert env.action_spaces[a].contains(act)

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


def test_paradigm_wrappers_over_the_market(env):
    """The CTDE and CTCE wrappers see the market as the RL layer expects: under
    CTDEEnv each agent observes its own values followed by all agents'
    and keeps its own reward and its own mixed action; under CTCEEnv one agent
    observes everything, acts with a ``Tuple`` of the agents' ``Dict`` actions in
    agent order, and receives the sum of the rewards."""
    from core.rl.ctce import GROUP, CTCEEnv
    from core.rl.ctde import CTDEEnv

    config = {
        "env_class": MarketEnv,
        "env_config": {"scenario": str(SCENARIO), "days": DAYS},
    }
    n, d = len(env.agents_id), len(env.obs_names)

    central = CTDEEnv(config)
    obs, _ = central.reset(seed=1)
    assert all(o.shape == (d + n * d,) for o in obs.values())
    assert central.action_spaces == env.action_spaces
    actions = {a: action(0, 0.5, 0.0, n) for a in central.agents_id}
    obs, rewards, term, _, _ = central.step(actions)
    assert set(rewards) == set(central.agents_id)
    first = central.agents_id[0]
    np.testing.assert_array_equal(obs[first][d : 2 * d], obs[first][:d])

    grouped = CTCEEnv(config)
    obs, _ = grouped.reset(seed=1)
    assert obs[GROUP].shape == (n * d,)
    space = grouped.action_spaces[GROUP]
    assert list(space.spaces) == [env.action_spaces[a] for a in env.agents_id]
    joint = tuple(action(0, 0.5, 0.0, n) for _ in range(n))
    assert space.contains(joint)
    _, rewards, _, _, infos = grouped.step({GROUP: joint})
    assert rewards[GROUP] == pytest.approx(sum(infos[GROUP]["rewards"].values()))
