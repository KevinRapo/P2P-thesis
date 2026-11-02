"""Tariffs from the price files (``config/data/``): a series must fit the market step,
and the step's tariffs reach the market's inputs, the RL agents' price action and
their reward."""

from pathlib import Path

import pytest

from core.config import store
from core.config.scenario import DsoSetup, flat_prices, load_prices, price_at
from core.env.market_env import MarketEnv, zero_policy
from core.market.dso import Dso
from core.grid.contract import GridPath
from core.market.lem import LocalEnergyMarket
from core.market.order import Trade

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


def test_every_form_of_the_prices_comes_out_as_series():
    named = load_prices("synthetic_day", 1.0)
    flat = load_prices({"utility": 0.3, "feed_in": 0.08}, 1.0)
    mixed = load_prices({"utility": named["utility"], "feed_in": 0.08}, 1.0)
    assert (flat["utility"], flat["feed_in"]) == ([0.3] * 24, [0.08] * 24)
    assert (mixed["utility"], mixed["feed_in"]) == (named["utility"], [0.08] * 24)
    assert flat_prices({"utility": 0.3, "feed_in": 0.08})
    assert not flat_prices({"utility": named["utility"], "feed_in": 0.08})
    assert not flat_prices("synthetic_day")
    assert not any("cannot be read" in p for p in DsoSetup().problems(0.25))

    with pytest.raises(ValueError, match="a day has 24 steps"):
        load_prices({"utility": [0.3] * 3, "feed_in": 0.08}, 1.0)


def test_flat_tariffs_are_the_default_and_an_older_file_keeps_its_own():
    dso = Dso(DsoSetup())
    dso.set_hour(13)
    assert (dso.feed_in_tariff, dso.utility_price) == (0.08, 0.30)
    older = {"dso": {"prices": None, "feed_in_tariff": 0.1, "utility_price": 0.5}}
    assert store.from_dict(older).dso.prices == {"utility": 0.5, "feed_in": 0.1}
    named = {"dso": {"prices": "synthetic_day", "utility_price": 0.5}}
    assert store.from_dict(named).dso.prices == "synthetic_day"


def dated_prices() -> dict:
    day = {"utility": [0.3] * 24, "feed_in": [0.1] * 24}
    dear = {"utility": [0.5] * 24, "feed_in": [0.2] * 24}
    return day | {"days": {"2016-06-01": day, "2016-06-02": dear}}


def test_a_dated_file_trades_at_each_days_prices():
    dso = Dso(DsoSetup(prices=dated_prices()))
    dso.set_day("2016-06-02")
    dso.set_hour(5)
    assert (dso.feed_in_tariff, dso.utility_price) == (0.2, 0.5)
    assert dso.tariff_range(["2016-06-01", "2016-06-02"]) == (0.1, 0.5)

    with pytest.raises(ValueError, match="no day 2016-06-03"):
        dso.set_day("2016-06-03")


def test_the_price_files_of_2024_hold_every_day_with_room_for_peers():
    for name in ("de_2024", "de_2024_flat"):
        prices = load_prices(name, 1.0)
        assert len(prices["days"]) == 366
        assert not DsoSetup(prices=prices, peer_charge_kwh=0.2294).problems(1.0)


def test_a_peer_charge_above_the_tariffs_gap_is_a_problem():
    setup = DsoSetup(prices=dated_prices(), peer_charge_kwh=0.2)
    assert any("no gain from peers" in p for p in setup.problems(1.0))
    assert any("negative" in p for p in DsoSetup(peer_charge_kwh=-1).problems(1.0))


def test_the_peer_charge_is_the_buyers_and_lowers_the_peers_ceiling():
    dso = Dso(DsoSetup(peer_charge_kwh=0.1, fee_buyer_share=0.5))
    assert dso.peer_ceiling() == pytest.approx(0.2)
    assert dso.market_price() == pytest.approx((0.08 + 0.2) / 2)
    parts = dso.fees_of(2.0, 0.15, GridPath(), 0.0)
    trade = Trade("b", "s", 0.15, 2.0, 0.0, stage=1)
    charged = dso._charged(trade, parts)
    assert parts.peer_charge == pytest.approx(0.2)
    assert charged.seller_fee == pytest.approx((parts.total - 0.2) * 0.5)
    assert charged.buyer_fee == pytest.approx(0.2 + (parts.total - 0.2) * 0.5)
    unpaid = Dso(DsoSetup(peer_charge_kwh=0.1, fees_charged=False))
    assert unpaid.peer_ceiling() == pytest.approx(0.3)  # nobody pays: no ceiling


def test_the_price_action_stops_at_the_peer_ceiling():
    scenario = store.load(SCENARIO)
    scenario.dso.peer_charge_kwh = 0.1
    path = Path(__file__).parent / "_peer_charge.json"
    store.save(scenario, path)

    try:
        market = MarketEnv({"scenario": str(path)})
    finally:
        path.unlink()

    market.reset(seed=0)
    pid = market.agents_id[0]
    top = market.decode(pid, market.encode(pid, "buy", 1.0, 1.0))
    assert top is not None
    assert top.price == pytest.approx(market.market.dso.utility_price - 0.1)


def test_later_environments_keep_the_training_tariff_range():
    days = ["2016-06-01", "2016-06-02"]
    env = MarketEnv({"scenario": str(SCENARIO), "days": days})
    resolved = env.resolved_config()
    assert resolved["tariff_range"] == [0.08, 0.40]
    moved = MarketEnv(resolved | {"tariff_range": [0.0, 1.0]})
    assert (moved.feed_in_tariff, moved.utility_price) == (0.0, 1.0)


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
        assert record.inputs.utility_price == price_at(TOU_UTILITY, step)

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
