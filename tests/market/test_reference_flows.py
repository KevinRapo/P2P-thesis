"""The references on the market's own power flow and fees (``ceiling.references``).

A reference's schedule fixes every participant's injection, so it runs through the
market's power flow, and the non-P2P reference's settlements with the retailer are
charged as the market charges the energy no trade covers. Without batteries, the
non-P2P schedule is exactly what a market with nobody ordering does: every kWh
untraded. So that market, played step by step, is the check: the references must give
its flow, its losses, its loss charge and its fees to the cent.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core.config import store
from core.market import ceiling
from core.market.indicators import day_table
from core.market.lem import LocalEnergyMarket, net_bill

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
DAYS = ["2016-06-14", "2016-06-15"]


def scenario_without_batteries():
    scenario = store.load(SCENARIO)
    scenario.dso.losses = "bcdla"
    scenario.dso.fees_charged = True

    for person in scenario.participants:
        person.battery = None

    return scenario


@pytest.fixture(scope="module")
def played():
    """Two days of the market with nobody ordering, as the held-out tables of a run
    (``agent_steps``, ``steps``) and the records themselves."""
    scenario = scenario_without_batteries()
    market = LocalEnergyMarket(scenario)
    people, steps, records = [], [], []

    for day in DAYS:
        market.scenario.grid.day = day
        market.reset()

        while not market.done:
            r = market.step({})
            records.append((day, r))
            steps.append(
                {"policy": "net_position", "day": day, "period": "p", "step": r.step,
                 "feed_in_tariff": r.inputs.feed_in_tariff,
                 "utility_price": r.inputs.utility_price}
            )
            people.extend(
                {"policy": "net_position", "day": day, "period": "p", "step": r.step,
                 "agent": pid, "generation_kwh": o.generation_kwh,
                 "demand_kwh": o.demand_kwh, "soc": np.nan, "stored_change_kwh": 0.0}
                for pid, o in r.participants.items()
            )

    return asdict(scenario), pd.DataFrame(people), pd.DataFrame(steps), records


def sums(records, day, what):
    return sum(what(r) for d, r in records if d == day)


def test_the_non_p2p_reference_is_the_market_with_nobody_ordering(played):
    scenario, people, steps, records = played
    alone = ceiling.alone_days(people, steps, scenario)
    team = ceiling._alone(people, steps, scenario, ceiling._market_of(scenario))[1]

    for day in DAYS:
        row = team.loc[("non_p2p", day)]
        assert row.fees == pytest.approx(sums(records, day, lambda r: r.fees))
        assert row.loss_charge == pytest.approx(
            sums(records, day, lambda r: sum(o.loss_charge for o in r.participants.values()))
        )
        assert row.grid_losses_kwh == pytest.approx(
            sums(records, day, lambda r: r.grid.losses_kwh)
        )
        assert row.team_money == pytest.approx(
            sums(records, day, lambda r: sum(net_bill(r, p) for p in r.participants))
        )
        assert row.energy_money == pytest.approx(row.team_money + row.fees + row.loss_charge)

    # per participant too: the bill is the market's net bill
    for (day, agent), mine in alone.set_index(["day", "agent"]).bill.items():
        expected = sum(net_bill(r, agent) for d, r in records if d == day)
        assert mine == pytest.approx(expected)

    assert (alone.fees > 0).any() and (alone.energy_bill == alone.bill + alone.fees + alone.loss_charge).all()


def test_the_ceiling_has_the_flow_and_the_loss_charge_but_no_fees(played):
    scenario, people, steps, records = played
    top = ceiling.ceiling_days(people, steps, scenario)
    alone = ceiling.alone_days(people, steps, scenario)

    for day in DAYS:
        row = top.loc[("ceiling", day)]
        # without batteries nothing is chosen: the ceiling is the same flow
        assert row.grid_losses_kwh == pytest.approx(
            sums(records, day, lambda r: r.grid.losses_kwh)
        )
        assert row.loss_charge == pytest.approx(
            sums(records, day, lambda r: sum(o.loss_charge for o in r.participants.values()))
        )
        assert row.highest_voltage == pytest.approx(
            max(r.grid.max_voltage_pu for d, r in records if d == day)
        )
        assert row.highest_line_loading == pytest.approx(
            max(r.grid.max_line_loading_percent for d, r in records if d == day)
        )
        assert np.isnan(row.fees) and np.isnan(row.team_money)  # who traded with whom?
        # the program nets the community, so it earns at least what nobody netting does
        floor = alone.energy_bill.groupby(alone.day).sum()[day]
        assert row.energy_money >= floor - 1e-9


def test_without_the_grid_the_references_are_money_only(played):
    scenario, people, steps, records = played
    top = ceiling.ceiling_days(people, steps, scenario, grid=False)
    assert "grid_losses_kwh" not in top and top.team_money.isna().all()
    alone = ceiling.alone_days(people, steps, scenario, grid=False)
    assert alone.fees.isna().all() and (alone.bill == alone.energy_bill).all()


def test_a_scenario_too_short_for_the_market_gives_money_only(played):
    scenario, people, steps, records = played
    short = {"participants": scenario["participants"], "grid": {"step_hours": 1.0}}
    assert ceiling._market_of(short) is None
    assert "grid_losses_kwh" not in ceiling.ceiling_days(people, steps, short)


def test_the_day_table_has_both_vtis_and_their_difference_is_the_fees(played):
    scenario, people, steps, records = played
    refs = ceiling.references(people, steps, scenario)
    alone = refs.alone
    # A policy that does exactly what non-P2P does: every kWh untraded
    agents = pd.DataFrame(
        {
            "policy": "net_position", "day": alone.day, "agent": alone.agent,
            "bill": alone.bill, "fees": alone.fees + alone.loss_charge,
            "loss_charge": alone.loss_charge, "deferred_demand_kwh": 0.0,
            "deferred_supply_kwh": 0.0, "stored_change_kwh": 0.0,
        }
    )
    episodes = agents[["policy", "day"]].drop_duplicates().assign(fees=0.0)
    table = day_table(
        episodes, agents, ceiling=refs.ceiling, alone=refs.alone,
        day_references=refs.by_day, alone_team=refs.alone_team,
    )
    day = table.loc[("net_position", DAYS[0])]
    floor = table.loc[("non_p2p", DAYS[0])]

    assert day.energy_money == pytest.approx(floor.energy_money)
    assert day.team_money == pytest.approx(floor.team_money)
    assert day.energy_money == pytest.approx(
        day.team_money + agents.fees.groupby(agents.day).sum()[DAYS[0]]
    )

    # over the period: 0 before fees, and below 0 by (fees + loss charge) / reach after
    energy = table.energy_money.xs("net_position", level="policy").sum()
    after = table.team_money.xs("net_position", level="policy").sum()
    reach = (
        table.energy_money.xs("ceiling", level="policy").sum()
        - table.energy_money.xs("non_p2p", level="policy").sum()
    )
    assert reach > 0  # the ceiling nets the community: more than everybody alone
    assert day.vti == pytest.approx(0.0, abs=1e-9)
    assert day.vti_after_fees == pytest.approx((after - energy) / reach)
    assert day.vti - day.vti_after_fees == pytest.approx((energy - after) / reach)
    assert day.vti_after_fees < 0
    assert np.isnan(table.loc[("ceiling", DAYS[0])].vti_after_fees)
    assert floor.grid_losses_kwh > 0 and floor.fees > 0
