"""Fees on untraded energy, the transformer in the DSO trades' congestion, and the
zone bonus that never pays out (MP-1f, MP-4l, MP-4n).

Everything a participant settles with the DSO pays the fees of a DSO trade: what it
orders to the DSO in stage 3 and the energy no trade covered, which is settled with
the DSO at the same tariffs. Not ordering is then no cheaper than ordering the same
energy to the DSO.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import store
from core.config.scenario import DsoSetup
from core.grid.contract import GridAssessment, GridPath
from core.market.agent.battery import Battery
from core.market.agent.der import Participant
from core.market.dso import DSO_ID, Dso
from core.market.lem import LocalEnergyMarket, OrderIntent, net_bill
from core.market.order import UNTRADED

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
STEP = 12  # midday: the loading is high enough for a thermal fee


def market(**dso) -> LocalEnergyMarket:
    scenario = store.load(SCENARIO)

    for name, value in dso.items():
        setattr(scenario.dso, name, value)

    found = LocalEnergyMarket(scenario)
    found.reset()

    for _ in range(STEP):
        found.step({})

    return found


def untraded_of(record, pid: str):
    return next(t for t in record.untraded if pid in (t.buyer_id, t.seller_id))


# --------------------------------------------------------------------------------------
# Untraded energy is a settlement with the DSO
# --------------------------------------------------------------------------------------
def test_untraded_energy_is_settled_with_the_dso_at_the_tariff_and_pays_its_fees():
    m = market()
    r = m.step({})
    tariffs = r.inputs

    assert r.trades == [] and r.p2p_kwh == 0 and r.dso_kwh == 0
    assert {t.stage for t in r.untraded} == {UNTRADED}
    assert len(r.untraded) == len(r.participants)

    for pid, o in r.participants.items():
        t = untraded_of(r, pid)
        deficit = o.deferred_demand_kwh > 0

        assert t.quantity == pytest.approx(o.deferred_demand_kwh + o.deferred_supply_kwh)
        assert (t.buyer_id, t.seller_id) == ((pid, DSO_ID) if deficit else (DSO_ID, pid))
        assert t.price == (tariffs.utility_price if deficit else tariffs.feed_in_tariff)
        assert t.distance == pytest.approx(m._upstream(pid).distance_km)
        # the participant pays the whole fee, nobody else any of it
        assert (t.buyer_fee, t.seller_fee) == ((t.fees, 0.0) if deficit else (0.0, t.fees))
        assert t.fees == pytest.approx(t.fee_parts.total) and t.fees > 0
        assert o.fees == pytest.approx(t.fees)

    assert r.fees == pytest.approx(sum(t.fees for t in r.untraded))
    assert r.dso.fees == pytest.approx(r.fees)


def test_the_bill_has_the_fees_of_the_untraded_energy_in_it():
    r = market().step({})

    for pid, o in r.participants.items():
        retail = (
            r.inputs.feed_in_tariff * o.deferred_supply_kwh
            - r.inputs.utility_price * o.deferred_demand_kwh
        )
        assert net_bill(r, pid) == pytest.approx(retail - o.fees)
        assert o.profit == pytest.approx(-o.fees)


def test_ordering_the_energy_to_the_dso_costs_the_same_as_not_ordering_it():
    """P3 is short: its deficit untraded, or ordered to the DSO at the utility price
    (a stage-3 trade), pays the same fee, part by part."""
    quiet, active = market(), market()
    a = quiet.step({})
    deficit = -active.participants["P3"].net_kwh(STEP)
    b = active.step({"P3": OrderIntent("P3", True, active.dso.utility_price, deficit)})
    ordered = next(t for t in b.trades if t.buyer_id == "P3")
    left = untraded_of(a, "P3")

    assert ordered.stage == 3 and not any("P3" in (t.buyer_id, t.seller_id) for t in b.untraded)
    assert left.quantity == pytest.approx(deficit) and left.price == ordered.price

    for part in ("congestion", "thermal", "voltage", "transmission", "zone", "imbalance"):
        assert getattr(ordered.fee_parts, part) == pytest.approx(
            getattr(left.fee_parts, part)
        )

    assert ordered.buyer_fee == pytest.approx(left.buyer_fee)
    assert b.participants["P3"].fees == pytest.approx(a.participants["P3"].fees)


def test_when_the_fees_are_not_charged_the_untraded_energy_pays_nothing():
    r = market(fees_charged=False).step({})

    assert r.untraded
    assert all(t.buyer_fee == 0.0 and t.seller_fee == 0.0 for t in r.untraded)
    assert all(o.fees == 0.0 for o in r.participants.values())
    assert r.dso.fees == 0.0

    for pid, o in r.participants.items():
        retail = (
            r.inputs.feed_in_tariff * o.deferred_supply_kwh
            - r.inputs.utility_price * o.deferred_demand_kwh
        )
        assert net_bill(r, pid) == pytest.approx(retail)


def test_baseline_rows_and_trade_tables_carry_the_fees_of_the_untraded_energy():
    from core.env.market_env import _trade_rows
    from core.market.baseline import FEE_PARTS, _row

    m = market()
    r = m.step({})
    row = _row(m.scenario.grid.day, r, m)
    rows = _trade_rows(r)

    assert len(rows) == len(r.untraded) and {x["stage"] for x in rows} == {UNTRADED}

    for part in FEE_PARTS:
        expected = sum(getattr(t.fee_parts, part) for t in r.untraded)
        assert row[f"fee_{part}"] == pytest.approx(expected)

    assert sum(x["fee_voltage"] for x in rows) == pytest.approx(row["fee_voltage"])
    assert row["fee_voltage"] > 0


# --------------------------------------------------------------------------------------
# The transformer in a DSO trade's congestion
# --------------------------------------------------------------------------------------
def observed(dso: Dso, lines: dict, trafo: float | None) -> None:
    dso.observe(
        GridAssessment(
            step=0, converged=True, min_voltage_pu=1.0, max_voltage_pu=1.0,
            max_line_loading_percent=max(lines.values(), default=0.0),
            max_trafo_loading_percent=trafo, losses_kwh=0.0, external_grid_kwh=0.0,
            bus_voltage_pu={}, violations=(), line_loading_percent=lines,
        )
    )


def test_a_trade_with_the_dso_sees_the_transformer_a_peer_trade_does_not():
    dso = Dso(DsoSetup())
    observed(dso, {"l1": 40.0}, trafo=114.0)
    path = GridPath(lines=("l1",), zone_a="a", zone_b="b")

    assert dso.congestion(("l1",)) == pytest.approx(0.4)
    assert dso.congestion(("l1",), transformer=True) == 1.0  # capped at 100 %
    peer = dso.fees_of(1.0, 0.3, path, 0.0)
    to_dso = dso.fees_of(1.0, 0.3, path, 0.0, transformer=True)
    assert peer.congestion == 0.0  # 40 % is under the 80 % threshold
    assert to_dso.congestion == pytest.approx(0.5 * (1.0 - 0.8) * 0.3)
    assert to_dso.thermal > peer.thermal


def test_a_transformer_below_the_lines_changes_nothing_and_none_is_zero():
    dso = Dso(DsoSetup())
    observed(dso, {"l1": 60.0}, trafo=None)
    assert dso.trafo_loading_percent == 0.0
    assert dso.congestion(("l1",), transformer=True) == pytest.approx(0.6)
    observed(dso, {"l1": 60.0}, trafo=30.0)
    assert dso.congestion(("l1",), transformer=True) == pytest.approx(0.6)


# --------------------------------------------------------------------------------------
# The zone bonus cancels fees, it never pays out
# --------------------------------------------------------------------------------------
def test_the_zone_bonus_is_capped_at_the_fees_it_cancels():
    dso = Dso(DsoSetup(voltage_drop="measured"))
    observed(dso, {"l1": 90.0}, trafo=None)
    dso.bus_voltage_pu = {"a": 1.0}
    same_zone = GridPath(lines=("l1",), bus_a="a", bus_b="a")
    value = 2.0 * 0.2
    zone_factor = dso.setup.zone_factor

    # a fee far above the bonus: the bonus in full
    big = dso.fees_of(2.0, 0.2, same_zone, 0.0)
    assert big.congestion > 0 and big.zone == pytest.approx(-zone_factor * value)
    assert big.total >= 0

    # no fee at all: no bonus, and nothing is paid out
    quiet = Dso(DsoSetup())
    none = quiet.fees_of(2.0, 0.2, GridPath(), 0.0)
    assert none.zone == 0.0 and none.total == 0.0

    # a fee below the bonus: the bonus cancels exactly that
    small = Dso(DsoSetup(zone_factor=1.0, voltage_drop="measured"))
    small.bus_voltage_pu = {"a": 1.01}
    part = small.fees_of(2.0, 0.2, GridPath(bus_a="a", bus_b="a"), 0.0)
    assert part.voltage > 0
    assert part.zone == pytest.approx(-part.voltage) and part.total == pytest.approx(0.0)


def test_no_trade_of_a_played_day_has_a_negative_fee():
    m = market()
    records = [m.step({}) for _ in range(6)]
    assert all(t.fees >= 0.0 for r in records for t in (*r.trades, *r.untraded))


# --------------------------------------------------------------------------------------
# A household's own surplus counts against the battery room it may buy
# --------------------------------------------------------------------------------------
def person(net_kwh: float, soc: float) -> Participant:
    """A household whose generation less demand is ``net_kwh``, with a battery
    holding ``soc`` kWh of a 10 kWh pack (1-9 kWh window)."""
    from core.config.scenario import BatterySetup

    setup = BatterySetup(
        capacity_kwh=10.0,
        max_power_kw=50.0,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
        initial_soc=soc / 10.0,
    )
    battery = Battery(setup, step_hours=1.0)
    gen, dem = max(net_kwh, 0.0), max(-net_kwh, 0.0)
    return Participant("P", "bus", [], [gen], [dem], battery)


@pytest.mark.parametrize(
    "net, expected",
    [
        (-2.0, 2.0 + 4.0),  # short: buys its deficit and the whole room (9 - 5)
        (0.0, 4.0),
        (3.0, 1.0),  # the surplus fills 3 of the 4 kWh of room: 1 is left to buy
        (4.0, 0.0),
        (8.0, 0.0),  # more surplus than room: nothing to buy
    ],
)
def test_the_buy_limit_subtracts_the_households_own_surplus(net, expected):
    p = person(net, soc=5.0)
    assert p.battery_room()[0] == pytest.approx(4.0)
    assert p.max_buy_kwh(0) == pytest.approx(expected)


def test_a_household_without_a_battery_buys_only_its_deficit():
    p = Participant("P", "bus", [], [0.0], [3.0], None)
    assert p.max_buy_kwh(0) == pytest.approx(3.0)
    assert Participant("P", "bus", [], [3.0], [0.0], None).max_buy_kwh(0) == 0.0
