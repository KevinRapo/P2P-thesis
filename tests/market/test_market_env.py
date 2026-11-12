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

from core.config import store
from core.config.scenario import DsoSetup
from core.env import OBS_NAMES, MarketEnv, net_position_policy, zero_policy
from core.env.market_env import EXTRA_OBS, OBSERVATIONS
from core.env.reward import REWARDS, NetBillReward, SalazarReward, log_compress
from core.env_defaults import OBSERVATION_NAMES, REWARD_NAMES
from core.market.signals import KPIS, PRUNED_OBS
from core.rl.policy import evaluation
from core.market.clearing import Clearing, ClearingRules
from core.market.dso import DSO_ID, Dso
from core.market.lem import LocalEnergyMarket, OrderIntent
from core.market.order import Order

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
        obs, r, terminated, _, _ = env.step(policy(obs))
        rewards.append([r[a] for a in env.agents_id])
        records.append(env.last_record)

        if terminated["__all__"]:
            return np.array(rewards), records


def random_actions(env: MarketEnv, rng: np.random.Generator) -> dict:
    """A random mixed action per agent: side, quantity, price and partner."""
    return {
        a: {
            "side": int(rng.integers(2)),
            "quantity": rng.uniform(-1, 1, 1).astype(np.float32),
            "price": rng.uniform(-1, 1, 1).astype(np.float32),
            "partner": int(rng.integers(env.action_spaces[a]["partner"].n)),
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
    side Discrete(2), quantity and price Box(1), partner Discrete(N).
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
        assert space["side"].n == 2 and space["partner"].n == len(AGENTS)
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
    terminates (every agent and ``__all__``) and nothing is truncated: each day is a
    task of its own (RP-1f)."""
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
    """The zero policy's quantity share is 0, below the no-order threshold: no
    order at all. Each agent's
    reward is then only its untraded energy settled at retail, less the fees of
    that settlement with the DSO, ``(feed_in * deferred supply - utility *
    deferred demand - fees) / reward_scale`` (MP-1e, MP-1f)."""
    zero = zero_policy(env)
    obs = env.reset(seed=2)[0]

    while True:
        obs, rewards, terminated, _, _ = env.step(zero(obs))
        record = env.last_record
        assert len(record.orders) == 0
        utility = record.inputs.utility_price  # the step's
        feed_in = record.inputs.feed_in_tariff

        for a in AGENTS:
            o = record.participants[a]
            expected = feed_in * o.deferred_supply_kwh - utility * o.deferred_demand_kwh
            assert rewards[a] == pytest.approx((expected - o.fees) / env.reward_scale)

        if terminated["__all__"]:
            break


def test_reset_plays_the_day_asked_for(env):
    _, infos = env.reset(seed=0, options={"day": DAYS[-1]})
    assert infos["P1"]["day"] == DAYS[-1]
    with pytest.raises(ValueError, match="not one of the environment's days"):
        env.reset(options={"day": "2016-12-31"})


def test_the_reward_setting_chooses_the_calculation(env):
    """The default is the bill. ``"salazar"`` plays the same market and reports the
    same money, with a reward of its own; its names match the runner's."""
    assert isinstance(env.reward, NetBillReward)
    assert set(REWARDS) == set(REWARD_NAMES)
    salazar = MarketEnv(
        {
            "scenario": str(SCENARIO),
            "days": DAYS,
            "reward": "salazar",
            "grid_capacity_kwh": 50.0,
        }
    )
    assert isinstance(salazar.reward, SalazarReward)
    assert salazar.contract()["reward"] == "salazar"
    rng = np.random.default_rng(3)
    env.reset(seed=3, options={"day": DAYS[0]})
    salazar.reset(seed=3, options={"day": DAYS[0]})
    done = False

    while not done:
        actions = random_actions(env, rng)
        _, plain, _, _, infos = env.step(actions)
        _, shaped, ended, _, others = salazar.step(actions)
        done = ended["__all__"]
        for a in AGENTS:
            assert others[a]["bill"] == pytest.approx(infos[a]["bill"])
            assert np.isfinite(shaped[a])

    assert any(shaped[a] != pytest.approx(plain[a]) for a in AGENTS)


def test_the_observation_setting_chooses_the_signals(env):
    """The default is the paper's 42. ``"pruned"`` gives the same values under its
    22 names, with the peers' reputations after them, and the baseline still reads its
    signals by name; its names match the runner's."""
    assert set(OBSERVATIONS) == set(OBSERVATION_NAMES)
    assert env.obs_names[:42] == OBS_NAMES
    assert set(PRUNED_OBS) <= set(OBS_NAMES) and len(PRUNED_OBS) == 22
    pruned = MarketEnv(
        {"scenario": str(SCENARIO), "days": DAYS, "observation": "pruned"}
    )
    assert pruned.observation_spaces[AGENTS[0]].shape == (22 + len(AGENTS) - 1,)
    full, _ = env.reset(seed=3, options={"day": DAYS[0]})
    small, _ = pruned.reset(seed=3, options={"day": DAYS[0]})
    baseline = net_position_policy(env)
    reduced = net_position_policy(pruned)
    done = False

    while not done:
        for a in AGENTS:
            assert pruned.observation_spaces[a].contains(small[a])
            for i, name in enumerate(pruned.obs_names):
                assert small[a][i] == full[a][env.obs_names.index(name)]

        actions = baseline(full)
        same = reduced(small)
        for a in AGENTS:
            assert same[a]["side"] == actions[a]["side"]
            assert same[a]["quantity"] == pytest.approx(actions[a]["quantity"])

        full, _, ended, _, _ = env.step(actions)
        small, _, _, _, _ = pruned.step(same)
        done = ended["__all__"]


def test_an_unknown_observation_is_refused():
    with pytest.raises(ValueError, match="unknown observation"):
        MarketEnv({"scenario": str(SCENARIO), "days": DAYS, "observation": "nope"})


def test_a_reward_is_refused_without_what_it_needs():
    """An unknown name, and the salazar reward without a capacity."""
    with pytest.raises(ValueError, match="unknown reward"):
        MarketEnv({"scenario": str(SCENARIO), "days": DAYS, "reward": "nope"})

    with pytest.raises(ValueError, match="grid_capacity_kwh"):
        MarketEnv({"scenario": str(SCENARIO), "days": DAYS, "reward": "salazar"})


def test_reward_is_the_scaled_net_bill(env):
    """On random actions every agent's reward is ``(profit + feed_in * deferred
    supply - utility * deferred demand) / reward_scale``, read from the market's
    own record: the trades' profit, and the untraded energy settled at retail."""
    rng = np.random.default_rng(3)
    env.reset(seed=3)

    for _ in range(8):
        _, rewards, _, _, infos = env.step(random_actions(env, rng))
        for a in AGENTS:
            o = env.last_record.participants[a]
            tariffs = env.last_record.inputs
            bill = (
                o.profit
                + tariffs.feed_in_tariff * o.deferred_supply_kwh
                - tariffs.utility_price * o.deferred_demand_kwh
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
    none = len(AGENTS) - 1  # the last partner index: no preference

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
def test_net_position_acts_and_trades(env):
    """The market's own bidding rule, read from the observation, gives actions
    inside the action space and trades with peers on both days. Whether it beats
    the zero policy is a result, not a rule: with the untraded energy settled at
    retail (MP-1e), its orders that find no peer clear with the DSO at the same
    tariffs plus the grid fees, so on a scenario with little peer trade it can
    end below zero."""
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
    actions = {a: action(0, 0.5, 0.0, n - 1) for a in central.agents_id}
    obs, rewards, term, _, _ = central.step(actions)
    assert set(rewards) == set(central.agents_id)
    first = central.agents_id[0]
    np.testing.assert_array_equal(obs[first][d : 2 * d], obs[first][:d])

    grouped = CTCEEnv(config)
    obs, _ = grouped.reset(seed=1)
    assert obs[GROUP].shape == (n * d,)
    space = grouped.action_spaces[GROUP]
    assert list(space.spaces) == [env.action_spaces[a] for a in env.agents_id]
    joint = tuple(action(0, 0.5, 0.0, n - 1) for _ in range(n))
    assert space.contains(joint)
    _, rewards, _, _, infos = grouped.step({GROUP: joint})
    assert rewards[GROUP] == pytest.approx(sum(infos[GROUP]["rewards"].values()))


def test_order_prices_are_whole_cents_and_ties_go_by_reputation():
    market = LocalEnergyMarket(store.load(SCENARIO))
    market.reset()
    pid = next(iter(market.participants))
    pending = market.start_step({pid: OrderIntent(pid, True, 0.2341, 1.0)})
    assert [o.price for o in pending.orders] == [0.23]

    rules = ClearingRules(
        "average", Dso(DsoSetup()), 0.2, reputation={"a": 0.4, "b": 0.9}
    )
    orders = [
        Order("1", "a", 0.23, 1.0, True, 0.0),
        Order("2", "b", 0.23, 1.0, True, 1.0),
        Order("3", "c", 0.20, 1.0, False, 2.0),
    ]
    assert Clearing(rules).double_auction(orders).trades[0].buyer_id == "b"


def steps_of(env, steps):
    """``steps`` steps with the net-position rule: their flags and summed amounts."""
    obs = env._observe()
    policy = net_position_policy(env)
    stored = dict.fromkeys(env.agents_id, 0.0)

    for _ in range(steps):
        obs, rewards, terminated, truncated, infos = env.step(policy(obs))
        for pid in stored:
            stored[pid] += infos[pid]["stored_change_kwh"]

    return rewards, terminated, truncated, stored


def test_a_window_carries_its_state_over_midnight_and_ends_on_the_next_day():
    days = ["2016-06-01", "2016-06-02"]
    env = MarketEnv(
        {
            "scenario": str(SCENARIO),
            "days": days + ["2016-06-05"],  # a gap: no window starts on the 2nd or 5th
            "episode_days": 2,
            "truncate_episode": True,
            "random_start_soc": True,
        }
    )
    assert env.windows == [days]
    env.reset(seed=0)
    start = env._stored_kwh()
    _, terminated, truncated, _ = steps_of(env, 24)
    assert not truncated["__all__"] and env.market.scenario.grid.day == days[1]
    midnight = env._stored_kwh()
    assert midnight != start and env.market.current_step == 0
    assert env._reputations() != dict.fromkeys(env.agents_id, 0.5)
    _, terminated, truncated, stored = steps_of(env, 24)
    assert truncated["__all__"] and not terminated["__all__"]
    assert env.market.scenario.grid.day == "2016-06-03"  # the bootstrap state
    end = env._stored_kwh()
    assert end != midnight
    assert {a: end[a] - start[a] for a in end} != {}
    assert sum(stored.values()) == pytest.approx(
        sum(end.values()) - sum(midnight.values())
    )


def test_terminal_value_adds_the_stored_energy_to_a_drawn_days_last_reward():
    config = {"scenario": str(SCENARIO), "stored_kwh_value": 0.3}
    env = MarketEnv(config | {"terminal_value": True})
    plain = MarketEnv(config | {"energy_scale": env.energy_scale, "reward_scale": env.reward_scale})
    env.reset(seed=0)
    plain.reset(seed=0)
    last, *_, stored = steps_of(env, 24)
    expected, *_ = steps_of(plain, 24)

    for pid in stored:
        gain = 0.3 * stored[pid] / env.reward_scale
        assert last[pid] == pytest.approx(expected[pid] + gain)


def test_a_test_period_carries_the_state_and_starts_from_the_initial_one():
    env = MarketEnv({"scenario": str(SCENARIO)})
    env.reset(options={"day": env.days[0]})
    initial = env._stored_kwh()
    steps_of(env, 24)
    end = env._stored_kwh()
    assert end != initial
    _, infos = env.reset(options={"day": env.days[0], "carry": True, "period": "p"})
    assert env._stored_kwh() == end and infos[env.agents_id[0]]["period"] == "p"
    env.reset(options={"day": env.days[0]})
    assert env._stored_kwh() == initial


def test_a_step_keeps_what_the_results_need():
    config = {"scenario": str(SCENARIO), "days": DAYS, "reward": "salazar"}
    env = MarketEnv(config | {"grid_capacity_kwh": 100.0})
    act = net_position_policy(env)
    obs, _ = env.reset(seed=0)
    done = False

    while not done:
        obs, rewards, terminated, _, infos = env.step(act(obs))
        record, done = env.last_record, terminated["__all__"]
        first = infos[env.agents_id[0]]
        bought = sum(i["peer_bought_kwh"] for i in infos.values())
        assert bought == pytest.approx(record.p2p_kwh)
        assert bought == pytest.approx(sum(i["peer_sold_kwh"] for i in infos.values()))
        assert ("final" in first) == env.market.done or done
        state = first["shared_state"]
        assert np.isnan(state["peer_price"]) == (record.p2p_kwh == 0)
        assert state["utility_price"] == record.inputs.utility_price

        for pid, info in infos.items():
            parts = {k: v for k, v in info["state"].items() if k[:7] == "reward_"}
            assert info["demand_kwh"] == record.inputs.demand_kwh[pid]
            penalties = ("reward_dso_penalty", "reward_demand_penalty")
            raw = sum(-v if k in penalties else v for k, v in parts.items())
            assert rewards[pid] == pytest.approx(log_compress(raw))

    assert set(first["final"]) == set(KPIS)


def test_a_played_day_keeps_its_tables_and_training_does_not():
    config = {"scenario": str(SCENARIO), "days": DAYS}
    env = MarketEnv(config)
    act = net_position_policy(env)
    played = evaluation(
        MarketEnv, config, {"rule": act}, [0], [{"day": DAYS[0]}], by_step=True
    )
    trades, grid = played.tables["trades"], played.tables["grid"]
    assert len(grid) == len(played.steps) == env.market.n_steps
    assert (grid.step == played.steps.step).all()
    assert list(trades.columns[:5]) == ["policy", "episode", "seed", "day", "step"]
    assert any(c.startswith("bus_voltage/") for c in grid)
    assert any(c.startswith("line_loading/") for c in grid)
    peer = trades[trades.stage < 3]
    assert played.steps.peer_trades.sum() == len(peer)
    assert played.steps.p2p_kwh.sum() == pytest.approx(peer.kwh.sum())
    assert played.steps.mean_line_loading_percent.notna().all()
    assert "grid_balance_kwh" in played.steps

    obs, _ = env.reset(seed=0)
    infos = env.step(act(obs))[-1]
    assert "tables" not in infos[AGENTS[0]]
    assert "peer_trades" in infos[AGENTS[0]]["shared"]


def test_the_trades_add_up_to_the_dsos_profit():
    env = MarketEnv({"scenario": str(SCENARIO), "days": DAYS})
    obs, _ = env.reset(seed=0, options={"day": DAYS[0]})
    act, money, profit = net_position_policy(env), 0.0, 0.0

    for _ in range(env.market.n_steps):
        obs, _, _, _, infos = env.step(act(obs))
        profit += env.last_record.dso.profit

        for t in infos[AGENTS[0]]["tables"]["trades"]:
            money += t["buyer_fee"] + t["seller_fee"]

            if t["stage"] == 3:
                money += (1 if t["seller"] == DSO_ID else -1) * t["price"] * t["kwh"]

    assert money == pytest.approx(profit)


def test_rounding_an_order_price_stays_inside_the_bounds():
    from core.market.lem import _round_within

    assert _round_within(0.306, 0.0, 0.306, 2) == 0.30  # not up over 0.306
    assert _round_within(0.304, 0.0, 0.306, 2) == 0.30
    assert _round_within(0.0749, 0.0749, 1.0, 2) == 0.08  # not down under 0.0749
    assert _round_within(0.5, 0.0, 1.0, 2) == 0.5
    assert _round_within(0.5, 0.0, 0.306, 2) == 0.5  # outside to begin with: as is


def test_forecast_error_changes_only_the_forecasts_of_later_steps():
    """``forecast_error`` (E-05): the remaining demand and supply see each later step
    within ±e of its true value; the current step stays true, the error stays the
    same all day, and the market plays the true profiles."""
    e = 0.3
    noisy = MarketEnv(
        {"scenario": str(SCENARIO), "days": DAYS[:1], "forecast_error": e, "seed": 3}
    )
    noisy.reset(options={"day": DAYS[0]})
    m = noisy.market

    for pid in noisy.agents_id:
        p = m.participants[pid]
        now = noisy._forecasts(pid)
        later = sum(p.demand_kwh[1:])
        assert p.demand_kwh[0] + (1 - e) * later - 1e-9 <= now["remaining_demand"]
        assert now["remaining_demand"] <= p.demand_kwh[0] + (1 + e) * later + 1e-9

    first = {pid: noisy._forecasts(pid) for pid in noisy.agents_id}
    obs = noisy._observe()
    noisy.step(zero_policy(noisy)(obs))
    for pid in noisy.agents_id:  # step 1: the step-0 value has left the sum
        p = m.participants[pid]
        demand_factor = noisy._forecast[pid][0]
        expected = p.demand_kwh[1] + float(np.dot(p.demand_kwh[2:], demand_factor[2:]))
        assert noisy._forecasts(pid)["remaining_demand"] == pytest.approx(expected)
        assert first[pid] != noisy._forecasts(pid)

    true = MarketEnv({"scenario": str(SCENARIO), "days": DAYS[:1]})
    true.reset(options={"day": DAYS[0]})
    assert true._forecasts("P1") == {}

    with pytest.raises(ValueError, match="forecast_error"):
        MarketEnv({"scenario": str(SCENARIO), "forecast_error": 1.0})


def test_a_step_keeps_the_raw_action_with_or_without_an_order(env):
    """RP-7l: the four action parts as the policy gave them reach the step's state,
    also when the quantity share is in the no-order region."""
    env.reset(seed=0)
    actions = {a: env.encode(a, "sell", 0.0, 0.25) for a in env.agents_id}  # no order
    _, _, _, _, infos = env.step(actions)

    for a in env.agents_id:
        state = infos[a]["state"]
        assert state["side"] == "none" and state["action_side"] == 0.0
        assert state["action_quantity"] == pytest.approx(-1.0)
        assert state["action_price"] == pytest.approx(-0.5)
        assert state["action_partner"] == env.partners(a).index("none")


# --------------------------------------------------------------------------------------
# Every registered option keeps the contract (how to add one: Architecture ->
# Development -> Adding an option)
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", sorted(REWARDS))
def test_every_reward_pays_every_agent(name):
    """A registered reward gives every agent a finite number every step, the money
    (``bill``) is the same whichever reward, and the runner knows its name."""
    assert name in REWARD_NAMES
    config = {"scenario": str(SCENARIO), "days": DAYS[:1], "reward": name}
    if name == "salazar":
        config["grid_capacity_kwh"] = 50.0
    env = MarketEnv(config)
    plain = MarketEnv({"scenario": str(SCENARIO), "days": DAYS[:1]})
    rng = np.random.default_rng(1)
    env.reset(seed=1, options={"day": DAYS[0]})
    plain.reset(seed=1, options={"day": DAYS[0]})

    for _ in range(4):
        actions = random_actions(env, rng)
        _, rewards, _, _, infos = env.step(actions)
        _, _, _, _, reference = plain.step(actions)
        assert set(rewards) == set(AGENTS)
        assert all(np.isfinite(r) for r in rewards.values())
        assert all(infos[a]["bill"] == pytest.approx(reference[a]["bill"]) for a in AGENTS)


@pytest.mark.parametrize("name", sorted(OBSERVATIONS))
def test_every_observation_set_names_known_signals(name):
    """A registered observation set names only computed signals, builds its space
    and observes finite values; the runner knows its name."""
    assert name in OBSERVATION_NAMES
    assert set(OBSERVATIONS[name]) <= set(OBS_NAMES) | set(EXTRA_OBS)
    env = MarketEnv({"scenario": str(SCENARIO), "days": DAYS[:1], "observation": name})
    obs, _ = env.reset(seed=1, options={"day": DAYS[0]})
    size = len(OBSERVATIONS[name]) + len(AGENTS) - 1

    for a in AGENTS:
        assert obs[a].shape == (size,) and np.isfinite(obs[a]).all()
