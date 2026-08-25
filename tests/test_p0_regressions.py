"""Focused regression tests for P0 settlement and pricing defects."""

import pytest

from src.agent.battery import Battery, BatteryState
from src.agent.der import DERAgent
from src.environment.base import RLAlgorithm, TrainingMode
from src.environment.train import RLTrainer
from src.grid.base import GridTopology
from src.grid.network import GridNetwork
from src.market.dso import DSOAgent
from src.market.matching import MarketConfig, OrderMatcher
from src.market.mechanism import (
    AveragePricing,
    BidAskSpreadPricing,
    BuyerPricing,
    ProportionalSurplusPricing,
    SellerPricing,
)
from src.market.order import Order, Trade


def _orders() -> tuple[Order, Order]:
    return (
        Order("buy", "buyer", 120.0, 10.0, True, 0.0),
        Order("sell", "seller", 80.0, 10.0, False, 0.0),
    )


def test_pricing_mechanisms_use_named_buy_sell_arguments() -> None:
    buy_order, sell_order = _orders()

    assert BuyerPricing().calculate_price(buy_order, sell_order) == 120.0
    assert SellerPricing().calculate_price(buy_order, sell_order) == 80.0
    assert AveragePricing().calculate_price(buy_order, sell_order) == 100.0
    assert BidAskSpreadPricing().calculate_price(buy_order, sell_order, factor=0.25) == 90.0
    assert ProportionalSurplusPricing().calculate_price(buy_order, sell_order, reference_price=100.0) == 100.0


def test_matching_preserves_submitted_order_quantities() -> None:
    grid = GridNetwork(topology=GridTopology.MESH, num_nodes=2)
    dso = DSOAgent("DSO", [80.0], [120.0], grid)
    matcher = OrderMatcher(2, MarketConfig(min_price=0.0, max_price=200.0), grid, dso)
    buy_order, sell_order = _orders()

    result = matcher.match_orders(0, [buy_order, sell_order], {"buyer": 0.5, "seller": 0.5})

    assert buy_order.quantity == 10.0
    assert sell_order.quantity == 10.0
    assert sum(trade.quantity for trade in result.trades) == pytest.approx(10.0)


def test_cash_ledger_conserves_every_trade_payment_and_fee() -> None:
    grid = GridNetwork(topology=GridTopology.MESH, num_nodes=2)
    dso = DSOAgent("DSO", [80.0], [120.0], grid)
    matcher = OrderMatcher(2, MarketConfig(min_price=0.0, max_price=200.0), grid, dso)
    buy_order, sell_order = _orders()

    result = matcher.match_orders(0, [buy_order, sell_order], {"buyer": 0.5, "seller": 0.5})
    trade = result.trades[0]

    assert matcher.get_agent_cash_position("buyer") == pytest.approx(-(trade.price * trade.quantity + trade.fees))
    assert matcher.get_agent_cash_position("seller") == pytest.approx(trade.price * trade.quantity)
    assert matcher.get_agent_cash_position("DSO") == pytest.approx(trade.fees)
    assert sum(matcher.cash_ledger.values()) == pytest.approx(0.0)


def test_battery_trade_balance_treats_purchase_as_energy_inflow() -> None:
    battery = Battery(10.0, min_soc=0.0, max_soc=1.0)
    battery.energy_level = 5.0
    agent = DERAgent("agent", 10.0, battery, generation_profile=[0.0], demand_profile=[0.0])

    agent.update_battery_from_trades(0, energy_bought=2.0)
    assert battery.state is BatteryState.CHARGING
    assert battery.energy_level == pytest.approx(7.0)

    agent.update_battery_from_trades(0, energy_sold=2.0)
    assert battery.state is BatteryState.DISCHARGING
    assert battery.energy_level == pytest.approx(5.0)


def test_battery_clips_at_exact_bounds_and_applies_efficiency_once() -> None:
    battery = Battery(10.0, min_soc=0.1, max_soc=0.9, charge_efficiency=0.8, discharge_efficiency=0.5, initial_soc=0.1)

    assert battery.charge(20.0) == pytest.approx(8.0)
    assert battery.energy_level == pytest.approx(9.0)
    assert battery.discharge(20.0) == pytest.approx(4.0)
    assert battery.energy_level == pytest.approx(1.0)


def test_trade_records_source_delivered_and_loss_energy_separately() -> None:
    trade = Trade("buyer", "seller", 1.0, 10.0, 0.0, transmission_loss=0.6)

    assert trade.quantity == pytest.approx(trade.delivered_quantity + trade.transmission_loss)
    assert trade.delivered_quantity == pytest.approx(9.4)


def test_ctde_training_is_explicitly_disabled_until_local_actors_are_trained() -> None:
    trainer = object.__new__(RLTrainer)
    trainer.algorithm = RLAlgorithm.PPO
    trainer.training = TrainingMode.CTDE

    with pytest.raises(ValueError, match="CTDE is disabled"):
        trainer._check_init()
