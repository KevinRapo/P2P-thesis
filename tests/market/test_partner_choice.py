"""The learned partner β ([P1] eq. 2) from the action to the clearing.

``MarketEnv``'s ``partner`` action part is an index into the agent's candidates
(the other participants in scenario order, the DSO, no preference). These tests
check the mapping, that the chosen partner reaches the order unchanged (never
replaced by the scenario's rule-based choice), what the partner observation holds
and when, how stage 1 of the clearing treats compatible, incompatible and
one-sided choices, and that a run's scales stay those of its training days.

The market's clearing is not changed by V2: stage 1 pairs agents that named each
other on opposite sides with bid >= ask, an order naming the DSO waits for stage
3, every other order goes to the double auction.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from core.env import SCALE_KEYS, MarketEnv, zero_policy
from core.market.dso import DSO_ID

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
DAY = "2016-06-15"
AGENTS = ["P1", "P2", "P3", "P4", "P5"]


@pytest.fixture(scope="module")
def env() -> MarketEnv:
    return MarketEnv({"scenario": str(SCENARIO), "days": [DAY]})


@pytest.fixture(scope="module")
def pair(env) -> tuple[int, str, str]:
    """A step of the day at which one agent can sell and another can buy: (step,
    seller, buyer)."""
    env.reset(seed=0)
    zero = zero_policy(env)

    while not env.market.done:
        t = env.market.current_step
        people = env.market.participants
        sellers = [a for a in AGENTS if people[a].max_sell_kwh(t) > 0.05]
        buyers = [a for a in AGENTS if people[a].max_buy_kwh(t) > 0.05]

        for s in sellers:
            for b in buyers:
                if b != s:
                    return t, s, b

        env.step(zero(None))

    raise AssertionError(f"no step on {DAY} with a seller and a buyer")


def at_step(env: MarketEnv, t: int) -> None:
    """Reset to the start of ``DAY`` and play no orders up to step ``t``."""
    env.reset(seed=0)
    zero = zero_policy(env)

    while env.market.current_step < t:
        env.step(zero(None))


def play(env, pair, seller_price, buyer_price, seller_names, buyer_names):
    """The step ``pair`` with only the seller and the buyer ordering (half of what
    each may trade), each naming a partner; returns the record and the infos."""
    t, s, b = pair
    at_step(env, t)
    actions = zero_policy(env)(None)
    actions[s] = env.encode(s, "sell", 0.5, seller_price, seller_names)
    actions[b] = env.encode(b, "buy", 0.5, buyer_price, buyer_names)
    *_, infos = env.step(actions)

    return env.last_record, infos


def stage(record, number: int):
    return [t for t in record.trades if t.stage == number]


# --------------------------------------------------------------------------------------
# The mapping from the action to the order
# --------------------------------------------------------------------------------------
def test_candidates_are_stable_and_name_dso_and_no_preference(env):
    """Each agent's candidates: the others in scenario order, the DSO, none; the
    partner part has one value per candidate."""
    assert env.partners("P1") == ["P2", "P3", "P4", "P5", "DSO", "none"]
    assert env.partners("P3") == ["P1", "P2", "P4", "P5", "DSO", "none"]

    for a in AGENTS:
        assert env.action_spaces[a]["partner"].n == len(env.partners(a))

    assert env.contract()["partners"]["P4"] == env.partners("P4")


def test_partner_index_reaches_the_intent(env, pair):
    """Index k of the partner part becomes ``OrderIntent.partner_id``: a peer, the
    DSO (``DSO_ID``), or None for no preference."""
    t, s, _ = pair
    at_step(env, t)

    for k, name in enumerate(env.partners(s)):
        action = env.encode(s, "sell", 0.5, 0.5)
        action["partner"] = k
        intent = env.decode(s, action)
        expected = {"DSO": DSO_ID, "none": None}.get(name, name)
        assert intent.partner_id == expected, (k, name)


def test_explicit_choice_is_never_replaced_by_the_rule(env, pair):
    """With the scenario's rule-based partner choice switched on, an RL agent's
    explicit "no preference" and its named peer reach the orders unchanged: the
    rule only fills in orders the market's own bidding rule makes."""
    t, s, b = pair
    env.market.scenario.market.partner_preference = True

    try:
        record, infos = play(env, pair, 0.2, 0.8, None, s)
    finally:
        env.market.scenario.market.partner_preference = False

    orders = {o.agent_id: o for o in record.orders}
    assert orders[s].partner_id is None
    assert orders[b].partner_id == s
    assert infos[s]["state"]["partner"] == "none"
    assert infos[b]["state"]["partner"] == s


# --------------------------------------------------------------------------------------
# Stage 1: mutual preferences
# --------------------------------------------------------------------------------------
def test_compatible_mutual_choice_trades_in_stage_1(env, pair):
    """Seller and buyer name each other, bid >= ask: they trade in stage 1, the
    infos report it (preference_kwh, partner_mutual) for both."""
    _, s, b = pair
    record, infos = play(env, pair, 0.2, 0.8, b, s)
    (trade,) = stage(record, 1)
    assert (trade.seller_id, trade.buyer_id) == (s, b)

    for a in (s, b):
        assert infos[a]["preference_kwh"] == pytest.approx(trade.quantity)
        assert infos[a]["state"]["partner_mutual"] == 1.0

    assert infos[s]["shared"]["preference_kwh"] == pytest.approx(trade.quantity)


def test_incompatible_prices_do_not_trade_in_stage_1(env, pair):
    """Mutual names but bid < ask: no stage-1 trade (and no auction trade
    either); both still see that the choice was mutual."""
    _, s, b = pair
    record, infos = play(env, pair, 0.9, 0.1, b, s)
    assert stage(record, 1) == [] and stage(record, 2) == []
    assert infos[s]["state"]["partner_mutual"] == 1.0
    assert infos[s]["preference_kwh"] == 0.0


def test_one_sided_choice_goes_to_the_auction(env, pair):
    """The seller names the buyer, the buyer names nobody: no stage-1 trade, but
    the prices cross, so they trade in the double auction (stage 2)."""
    _, s, b = pair
    record, infos = play(env, pair, 0.2, 0.8, b, None)
    assert stage(record, 1) == []
    assert {(t.seller_id, t.buyer_id) for t in stage(record, 2)} == {(s, b)}
    assert infos[s]["state"]["partner_mutual"] == 0.0
    assert np.isnan(infos[b]["state"]["partner_mutual"])  # named no peer


def test_naming_the_dso_skips_the_peers(env, pair):
    """An order naming the DSO stays out of stages 1 and 2 and is cleared by the
    DSO in stage 3, even with a crossing bid available."""
    _, s, b = pair
    record, infos = play(env, pair, 0.2, 0.8, "DSO", None)
    assert stage(record, 1) == [] and stage(record, 2) == []
    assert any(t.seller_id == s for t in stage(record, 3))
    assert infos[s]["state"]["partner"] == DSO_ID


# --------------------------------------------------------------------------------------
# What the agents observe of their partners
# --------------------------------------------------------------------------------------
def test_partner_observation_and_its_timing(env, pair):
    """The partner block holds, in candidate order, the peers' reputations as the
    last step left them."""
    env.reset(seed=0)
    names = list(env.obs_names)
    _, s, b = pair
    play(env, pair, 0.2, 0.8, b, s)
    obs = env._observe()
    m = env.market

    for a in AGENTS:
        o = obs[a]
        peers = env.partners(a)[:-2]
        reps = [o[names.index(f"partner_rep_{k}")] for k in range(1, len(peers) + 1)]
        np.testing.assert_allclose(
            reps, [m.participants[c].reputation for c in peers], rtol=1e-6
        )


# --------------------------------------------------------------------------------------
# Scales: resolved on the training days, kept for the held-out days
# --------------------------------------------------------------------------------------
def test_training_scales_are_kept_on_other_days(env):
    """``resolved_config`` holds the scales computed on the training days; an
    environment for other days built from it keeps them, while one built without
    them would compute its own (here: different)."""
    resolved = env.resolved_config()
    assert resolved["energy_scale"] == env.energy_scale
    assert resolved["reward_scale"] == env.reward_scale
    winter = {"scenario": str(SCENARIO), "days": ["2016-01-10"]}
    own = MarketEnv(winter)
    assert own.energy_scale != env.energy_scale  # the bug a frozen scale avoids
    kept = MarketEnv(winter | {k: resolved[k] for k in SCALE_KEYS})
    assert (kept.energy_scale, kept.reward_scale) == (
        env.energy_scale,
        env.reward_scale,
    )


def test_heldout_config_uses_the_runs_training_scales(tmp_path):
    """The runner's held-out evaluation plays the test days with the scales
    recorded in the run's run.json, not scales of the test days."""
    from core.runner.launch import heldout_env_config
    from core.runner.spec import Experiment

    experiment = Experiment.from_dict(
        {
            "scenario": "config/scenarios/validate_market.json",
            "train_days": ["2016-06-15"],
            "test_days": ["2016-01-10"],
            "algorithms": ["ppo"],
            "paradigms": ["dtde"],
            "seeds": [0],
            "budget": 100,
        },
        "x",
    )
    record = {"env_config": {"energy_scale": 12.5, "reward_scale": 3.75, "days": []}}
    config = heldout_env_config(experiment, tmp_path, None, record)
    assert config["days"] == ["2016-01-10"]
    assert (config["energy_scale"], config["reward_scale"]) == (12.5, 3.75)
