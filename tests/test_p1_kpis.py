"""Golden definitions for recorded descriptive metrics (P1-07)."""

import pytest

from src.agent.der import DERAgent
from src.coordination.implicit_cooperation import ImplicitCooperation
from src.market.matching import MatchingHistory
from src.market.order import Order, Trade


def test_kpis_use_explicit_turnover_physical_imbalance_and_local_share() -> None:
    first = DERAgent("a", 10.0, generation_profile=[3.0], demand_profile=[1.0])
    second = DERAgent("b", 10.0, generation_profile=[0.0], demand_profile=[4.0])
    orders = [Order("buy", "b", 4.0, 1.0, True, 0.0),
              Order("sell", "a", 2.0, 1.0, False, 0.0)]
    trades = [Trade("b", "a", 2.0, 1.0, 0.0), Trade("b", "DSO", 5.0, 2.0, 0.0)]

    kpis = ImplicitCooperation(10.0).get_kpis(0, "DSO", [first, second], orders, trades, 0.2,
                                               MatchingHistory())

    assert kpis["settlement_turnover"] == 12.0
    assert kpis["traded_energy"] == 3.0
    assert kpis["bid_ask_spread"] == 2.0
    assert kpis["physical_supply_demand_imbalance"] == pytest.approx(0.2)
    assert kpis["local_trade_share"] == pytest.approx(1 / 3)
    assert "social_welfare" not in kpis
