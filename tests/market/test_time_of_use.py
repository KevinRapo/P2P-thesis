"""Tariffs from the price files (``config/data/``): a series must fit the market step,
and the step's tariffs reach the market's inputs, the RL agents' price action and
their reward."""

from pathlib import Path

import pytest

from core.config import store
from core.config.scenario import DsoSetup, load_prices, price_at
from core.env.market_env import MarketEnv, zero_policy
from core.market.dso import Dso
from core.market.lem import LocalEnergyMarket

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
TOU_UTILITY = load_prices("synthetic_day", 1.0)["utility"]


def test_dso_keeps_its_setup_and_current_tariffs_separate():
    setup = DsoSetup(prices=load_prices("synthetic_day", 1.0), loss_factor=0.07)
    dso = Dso(setup)
    setup.loss_factor = 0.9
    setup.prices["utility"][17] = 9.0
    dso.set_hour(17)

    assert dso.setup.loss_factor == 0.07
    assert dso.transmission_loss(0.5, 2.0) == pytest.approx(0.07)
    assert dso.utility_price == 0.40
    assert dso.setup.utility_price == 0.30


def test_prices_must_fit_the_market_step():
    scenario = store.load(SCENARIO)
    scenario.grid.step_hours = 0.25
    assert any("96 steps" in problem for problem in scenario.problems())

    with pytest.raises(ValueError, match="a day has 96 steps"):
        LocalEnergyMarket(scenario)


def test_quarter_hour_steps_trade_at_their_prices():
    scenario = store.load(SCENARIO)
    scenario.grid.step_hours = 0.25
    scenario.dso.prices = "synthetic_day_15min"
    market = LocalEnergyMarket(scenario)
    market.reset()
    records = market.run_to_end()
    assert len(records) == 96
    assert records[27].inputs.utility_price == 0.20  # 06:45
    assert records[28].inputs.utility_price == 0.30  # 07:00
    assert records[68].inputs.utility_price == 0.40  # 17:00
    assert market.dso.utility_price == 0.20  # set for the next day's midnight


@pytest.fixture(scope="module")
def env() -> MarketEnv:
    return MarketEnv({"scenario": str(SCENARIO)})


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
