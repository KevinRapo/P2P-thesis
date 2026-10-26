"""Time-of-use tariffs (``core/config/scenario.py`` ``price_at``, ``Dso.set_hour``):
the step's tariffs reach the DSO's trades, the market's inputs, the RL agents'
price action and their reward; flat tariffs stay as they were."""

from dataclasses import replace
from pathlib import Path

import pytest

from core.config import store
from core.config.scenario import TOU_UTILITY, price_at
from core.env.market_env import MarketEnv, zero_policy
from core.market.dso import Dso

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"


def test_price_at_follows_the_schedule_and_wraps():
    assert [price_at(0.3, TOU_UTILITY, h) for h in (0, 6, 7, 16, 17, 21, 22, 23)] == [
        0.20,
        0.20,
        0.30,
        0.30,
        0.40,
        0.40,
        0.20,
        0.20,
    ]
    assert price_at(0.3, TOU_UTILITY, 24.0) == 0.20  # the next day's midnight
    assert price_at(0.3, None, 17) == 0.3  # flat
    late = [[6.0, 0.25], [18.0, 0.35]]
    assert price_at(0.3, late, 2) == 0.35  # before the first start: the day's last


def test_dso_sets_the_hours_tariffs_and_their_range():
    dso = Dso(0.08, 0.30, utility_schedule=TOU_UTILITY)
    dso.set_hour(18)
    assert (dso.feed_in_tariff, dso.utility_price) == (0.08, 0.40)
    assert dso.tariff_range() == (0.08, 0.40)
    flat = Dso(0.08, 0.30)
    flat.set_hour(18)
    assert (flat.utility_price, flat.tariff_range()) == (0.30, (0.08, 0.30))


def test_a_tariff_above_the_feed_in_is_required_every_hour():
    setup = store.load(SCENARIO).dso
    assert not replace(setup, utility_schedule=TOU_UTILITY).problems()
    low = [[0.0, 0.30], [12.0, 0.05]]
    assert replace(setup, utility_schedule=low).problems()


@pytest.fixture(scope="module")
def env() -> MarketEnv:
    return MarketEnv(
        {"scenario": str(SCENARIO), "dso": {"utility_schedule": TOU_UTILITY}}
    )


def test_every_step_trades_and_is_charged_at_its_hours_tariff(env):
    """With nobody ordering, each step's untraded import is charged at that step's
    time-of-use price, and the DSO's tariffs move on with the clock."""
    zero = zero_policy(env)
    obs, _ = env.reset(seed=0)
    assert env.market.dso.utility_price == 0.20  # midnight
    assert (env.feed_in_tariff, env.utility_price) == (0.08, 0.40)  # the day's range

    for step in range(env.market.n_steps):
        obs, rewards, terminated, _, _ = env.step(zero(obs))
        record = env.last_record
        assert record.inputs.utility_price == price_at(0.3, TOU_UTILITY, step)

        for pid, o in record.participants.items():
            expected = -record.inputs.utility_price * o.deferred_demand_kwh
            assert rewards[pid] == pytest.approx(expected / env.reward_scale)

    assert terminated["__all__"]
    assert env.market.dso.utility_price == 0.20  # set for the next day's midnight


def test_the_price_action_spans_the_steps_tariffs(env):
    """p = +1 asks the step's utility price, p = -1 the feed-in tariff."""
    env.reset(seed=0)

    while env.market.current_step < 18:  # into the evening peak
        env.step(zero_policy(env)(env._observe()))

    pid = env.agents_id[0]
    top = env.decode(pid, env.encode(pid, "buy", 1.0, 1.0))
    bottom = env.decode(pid, env.encode(pid, "buy", 1.0, 0.0))
    assert top is not None and top.price == pytest.approx(0.40)
    assert bottom is not None and bottom.price == pytest.approx(0.08)
