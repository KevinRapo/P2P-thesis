"""The thesis scenario's market settings (``config/scenarios/thesis_rural1.json``):
the imbalance fee off (MP-4m) and a minimum order quantity that keeps the numerical
dust out of the order book (MP-2g)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import store
from core.market.lem import LocalEnergyMarket, OrderIntent

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/thesis_rural1.json"


@pytest.fixture(scope="module")
def scenario():
    return store.load(SCENARIO)


def test_the_imbalance_fee_is_off_and_the_rest_of_the_fees_stay_on(scenario):
    assert scenario.dso.imbalance_factor == 0.0
    assert scenario.dso.fees_charged
    assert scenario.dso.voltage_drop == "measured"
    assert scenario.dso.losses == "bcdla"


def test_an_order_below_the_minimum_quantity_is_dropped_not_traded(scenario):
    assert scenario.market.min_quantity == pytest.approx(0.001)
    market = LocalEnergyMarket(scenario)
    market.reset()
    pid = scenario.participants[0].id
    seller = market.participants[pid]
    seller.generation_kwh[0], seller.demand_kwh[0] = 5.0, 0.0  # something to sell
    price = market.dso.feed_in_tariff
    dust = {pid: OrderIntent(pid, False, price, 1e-7)}
    small = {pid: OrderIntent(pid, False, price, 0.002)}

    assert market.start_step(dust).orders == ()
    market.pending = None
    assert [o.quantity for o in market.start_step(small).orders] == [0.002]
