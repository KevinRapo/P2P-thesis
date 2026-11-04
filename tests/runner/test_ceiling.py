"""The money ceiling: the linear program on cases worked out by hand, and the ceiling
of a run's test period from its held-out tables."""

import numpy as np
import pandas as pd
import pytest

from core.runner import ceiling
from core.runner.ceiling import POLICY, Store, ceiling_days, optimise
from core.runner import indicators
from core.runner.indicators import day_table

# Two steps: a surplus of 2 kWh while the feed-in tariff is 0, then a deficit of 2 kWh
# at a utility price of 0.5.
NET = np.array([2.0, -2.0])
FIT = np.array([0.0, 0.0])
UTIL = np.array([0.5, 0.5])


def store(**changes):
    setup = dict(
        capacity_kwh=10.0,
        min_soc=0.0,
        max_soc=1.0,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
        start_kwh=0.0,
    )
    return Store(**(setup | changes))


def test_without_a_battery_the_deficit_is_bought():
    assert optimise(NET, FIT, UTIL).value == pytest.approx(-1.0)


def test_a_lossless_battery_moves_the_surplus_to_the_deficit():
    plan = optimise(NET, FIT, UTIL, [store()])
    assert plan.value == pytest.approx(0.0)
    assert plan.steps.charge.tolist() == pytest.approx([2.0, 0.0])
    assert plan.steps.discharge.tolist() == pytest.approx([0.0, 2.0])


def test_losses_leave_part_of_the_deficit_to_buy():
    # 2 kWh in keeps 1.8; 1.8 out gives 1.62 at the bus; 0.38 bought at 0.5.
    plan = optimise(NET, FIT, UTIL, [store(charge_efficiency=0.9, discharge_efficiency=0.9)])
    assert plan.value == pytest.approx(-0.38 * 0.5)


def test_the_power_limit_caps_a_step():
    plan = optimise(NET, FIT, UTIL, [store(max_power_kw=0.5)], step_hours=2.0)
    assert plan.value == pytest.approx(-1.0 * 0.5)  # 1 kWh per 2 h step moved


def test_the_end_condition_keeps_a_full_battery_full():
    full = store(start_kwh=10.0)
    assert optimise(NET, FIT, UTIL, [full], keep_end=False).value == pytest.approx(0.0)
    # A full battery cannot take the surplus; ending full, it cannot give either.
    assert optimise(NET, FIT, UTIL, [full], keep_end=True).value == pytest.approx(-1.0)


def test_sites_net_only_inside():
    # Site 0 has the surplus, site 1 the deficit and the battery: nothing moves across.
    apart = np.array([[2.0, 0.0], [0.0, -2.0]])
    assert optimise(apart, FIT, UTIL, [store(site=1)]).value == pytest.approx(-1.0)
    together = optimise(apart.sum(axis=0), FIT, UTIL, [store()])
    assert together.value == pytest.approx(0.0)


def held_out():
    """One period of two one-step days, participants P1 (PV) and P2 (battery)."""
    rows, steps = [], []
    for d, (day, gen, fit, util) in enumerate((("d1", 2.0, 0.0, 0.5), ("d2", 0.0, 0.0, 0.5))):
        for agent, g in (("P1", gen), ("P2", 0.0)):
            demand = 2.0 if (agent == "P1" and day == "d2") else 0.0
            rows.append(
                {
                    "policy": "zero", "day": day, "period": "p", "step": 0,
                    "agent": agent, "generation_kwh": g, "demand_kwh": demand,
                    # P2 starts at 1 kWh and its first step does not change it
                    "soc": 0.1 if agent == "P2" else np.nan,
                    "stored_change_kwh": 0.0,
                }
            )
        steps.append({"policy": "zero", "day": day, "period": "p", "step": 0,
                      "feed_in_tariff": fit, "utility_price": util})
    battery = dict(capacity_kwh=10.0, min_soc=0.0, max_soc=1.0, charge_efficiency=1.0,
                   discharge_efficiency=1.0, initial_soc=0.5, max_power_kw=None)
    scenario = {"grid": {"step_hours": 1.0},
                "participants": [{"id": "P1", "battery": None},
                                 {"id": "P2", "battery": battery}]}
    return pd.DataFrame(rows), pd.DataFrame(steps), scenario


def test_a_period_carries_the_battery_from_day_to_day():
    agent_steps, steps, scenario = held_out()
    days = ceiling_days(agent_steps, steps, scenario)
    # d1's surplus goes into the battery, which covers d2's deficit: nothing is bought.
    assert days.team_money.tolist() == pytest.approx([0.0, 0.0])
    assert days.stored_change_kwh.tolist() == pytest.approx([2.0, -2.0])
    assert days.index.tolist() == [(POLICY, "d1"), (POLICY, "d2")]


def test_the_battery_starts_where_the_evaluation_started_it():
    agent_steps, steps, scenario = held_out()
    # Started at 1 kWh (soc 0.1 of 10), not at the setup's 5, with room up to 2 kWh:
    # it takes 1 kWh of d1's surplus, so 1 kWh of d2's deficit is bought at 0.5.
    scenario["participants"][1]["battery"]["max_soc"] = 0.2
    days = ceiling_days(agent_steps, steps, scenario)
    assert days.team_money.tolist() == pytest.approx([0.0, -0.5])


def test_without_the_tables_there_is_no_ceiling():
    assert ceiling_days(None, None, None) is None


def test_the_ceiling_is_a_policy_of_the_day_table():
    episodes = pd.DataFrame(
        [{"policy": p, "day": d} for p in ("trained", "zero", "net_position") for d in ("d1", "d2")]
    )
    agents = episodes.assign(agent="P1", bill=[1.0, 1.0, -1.0, -1.0, 0.0, 0.0],
                             deferred_demand_kwh=0.0, deferred_supply_kwh=0.0,
                             stored_change_kwh=0.0)
    top = pd.DataFrame(
        {"policy": POLICY, "day": ["d1", "d2"], "team_money": [5.0, 6.0],
         "stored_change_kwh": [0.0, 0.0]}
    ).set_index(["policy", "day"])
    day = day_table(episodes, agents, ceiling=top).loc[(POLICY, "d2")]
    assert day.team_money == 6.0
    assert day.gain_zero == 7.0 and day.gain_net_position == 6.0
    assert np.isnan(day.participants_better)


# --------------------------------------------------------------------------------------
# Non-P2P, VTI and PI: one period of two one-step days, feed-in 0.1, utility 0.5
# --------------------------------------------------------------------------------------
def alone_tables():
    zero = pd.DataFrame(
        [
            # P1 spills 2 kWh on d1 and lacks 1 on d2; P2 lacks 2 on d2.
            ("d1", "P1", 0.0, 2.0), ("d2", "P1", 1.0, 0.0),
            ("d1", "P2", 0.0, 0.0), ("d2", "P2", 2.0, 0.0),
        ],
        columns=["day", "agent", "deferred_demand_kwh", "deferred_supply_kwh"],
    ).assign(policy="zero", step=0, period="p")
    steps = pd.DataFrame(
        {"policy": "zero", "day": ["d1", "d2"], "step": 0,
         "feed_in_tariff": 0.1, "utility_price": 0.5}
    )
    return zero, steps


def test_on_their_own_the_spilled_surplus_earns_the_feed_in_tariff():
    own = indicators.non_p2p_bills(*alone_tables()).set_index(["day", "agent"]).bill
    assert own[("d1", "P1")] == pytest.approx(0.2)  # 2 kWh at 0.1
    assert own[("d2", "P1")] == pytest.approx(-0.5)
    assert own[("d2", "P2")] == pytest.approx(-1.0)


def test_vti_and_pi_over_the_period():
    own = indicators.non_p2p_bills(*alone_tables())  # team: 0.2, then -1.5
    bills = {"trained": ([0.0, 0.0], [-0.5, -0.6]), "zero": ([0.0, -0.5], [0.0, -1.0])}
    agents = pd.DataFrame(
        [
            {"policy": p, "day": d, "agent": a, "bill": b}
            for p, by in bills.items()
            for a, days in zip(("P1", "P2"), by)
            for d, b in zip(("d1", "d2"), days)
        ]
    )
    team = agents.groupby(["policy", "day"]).bill.sum().rename("team_money")
    references = pd.Series(
        [0.2, -1.5, 1.0, 0.7],
        index=pd.MultiIndex.from_tuples(
            [(indicators.NON_P2P, "d1"), (indicators.NON_P2P, "d2"),
             (POLICY, "d1"), (POLICY, "d2")], names=["policy", "day"]
        ),
        name="team_money",
    )
    out = pd.concat([team, references]).to_frame()
    scores = indicators._period_scores(out, agents, own)
    # Period sums: non-P2P -1.3, ceiling 1.7, so 3.0 to reach.
    assert scores.vti[("trained", "d1")] == pytest.approx((-1.1 + 1.3) / 3.0)
    assert scores.vti[("trained", "d2")] == scores.vti[("trained", "d1")]  # per period
    assert scores.vti[("zero", "d1")] == pytest.approx((-1.5 + 1.3) / 3.0)
    assert scores.vti[(POLICY, "d1")] == 1.0 and scores.vti[(indicators.NON_P2P, "d1")] == 0
    # P1 beats its -0.3 on its own with 0; P2's -1.1 does not beat -1.0.
    assert scores.pi[("trained", "d1")] == 0.5
    assert scores.pi[("zero", "d1")] == 0.0  # equal is not better
    assert np.isnan(scores.pi[(POLICY, "d1")])


def test_equality_is_one_minus_gini_on_non_negative_gains():
    # Gains 0, 0, 3: pairs |0-3| twice each way = 12; 2 * 3 * 3 = 18.
    assert indicators.equality([0.0, 0.0, 3.0]) == pytest.approx(1 - 12 / 18)
    assert indicators.equality([2.0, 2.0, 2.0]) == 1.0


def test_equality_stays_in_bounds_with_losses():
    # +1 and -1: |2| twice = 4 over 2 * 2 * 2 = 8.
    assert indicators.equality([1.0, -1.0]) == pytest.approx(0.5)
    assert indicators.equality([-1.0, -1.0]) == 1.0  # equal losses: read with the VTI
    assert np.isnan(indicators.equality([0.0, 0.0]))


def test_ei_over_the_period_is_on_the_gains():
    own = indicators.non_p2p_bills(*alone_tables())
    agents = pd.DataFrame(
        [{"policy": "trained", "day": d, "agent": a, "bill": b}
         for a, bills in (("P1", (0.0, 0.0)), ("P2", (-0.5, -0.6)))
         for d, b in zip(("d1", "d2"), bills)]
    )
    team = agents.groupby(["policy", "day"]).bill.sum().rename("team_money")
    index = pd.MultiIndex.from_tuples(
        [(indicators.NON_P2P, "d1"), (indicators.NON_P2P, "d2"),
         (POLICY, "d1"), (POLICY, "d2")], names=["policy", "day"]
    )
    out = pd.concat([team, pd.Series([0.2, -1.5, 1.0, 0.7], index, name="team_money")])
    scores = indicators._period_scores(out.to_frame(), agents, own)
    # Gains: P1 0 - (-0.3) = 0.3, P2 -1.1 - (-1.0) = -0.1.
    assert scores.ei[("trained", "d1")] == pytest.approx(indicators.equality([0.3, -0.1]))


def test_the_community_technical_indices():
    # One day of two steps, two participants. Step 0: P1 uses 4, P2 makes 1 -> net 3
    # imported. Step 1: P1 uses 1 (+1 charging), P2 makes 5 -> net -3 exported.
    rows = [
        (0, "P1", 4.0, 0.0, 0.0, 0.0), (0, "P2", 0.0, 1.0, 0.0, 0.0),
        (1, "P1", 1.0, 0.0, 1.0, 0.0), (1, "P2", 0.0, 5.0, 0.0, 0.0),
    ]
    a = pd.DataFrame(rows, columns=["step", "agent", "demand_kwh", "generation_kwh",
                                    "charge_kwh", "discharge_kwh"]).assign(policy="p", day="d")
    day = indicators._community_indicators(a).loc[("p", "d")]
    # |net| 3 + 3 over consumption 6 and production 6
    assert day.energy_balance_index == pytest.approx(1 - 6 / 12)
    assert day.peak_to_average == pytest.approx(3 / 3)
    assert day.self_sufficiency_index == pytest.approx(1 - 3 / 6)


def test_alone_nobody_shares_the_battery():
    # The period of ``held_out``: P1's surplus on d1 could fill P2's battery and cover
    # P1's deficit on d2 (the ceiling: nothing bought), but alone P1 sells it at 0
    # and buys 2 kWh at 0.5; P2's battery has nothing of its own to move.
    agent_steps, steps, scenario = held_out()
    alone = ceiling.alone_days(agent_steps, steps, scenario).set_index(["day", "agent"])
    assert alone.bill[("d1", "P1")] == pytest.approx(0.0)
    assert alone.bill[("d2", "P1")] == pytest.approx(-1.0)
    assert alone.bill.xs("P2", level="agent").tolist() == pytest.approx([0.0, 0.0])
    assert set(alone.period) == {"p"}


def test_alone_the_battery_owner_trades_its_own_hours():
    # One owner, no PV: 1 kWh demand at 0.2 then 1 kWh at 0.5; a lossless battery
    # starting empty must end empty, so it can only shift: buy 2 kWh at 0.2.
    rows = [("d", s, "P", 0.0, 1.0, 0.0, 0.0) for s in (0, 1)]
    agent_steps = pd.DataFrame(rows, columns=["day", "step", "agent", "generation_kwh",
                                              "demand_kwh", "soc", "stored_change_kwh"])
    agent_steps = agent_steps.assign(policy="zero", period="p")
    steps = pd.DataFrame({"policy": "zero", "day": "d", "period": "p", "step": [0, 1],
                          "feed_in_tariff": 0.0, "utility_price": [0.2, 0.5]})
    battery = dict(capacity_kwh=10.0, min_soc=0.0, max_soc=1.0, charge_efficiency=1.0,
                   discharge_efficiency=1.0, initial_soc=0.0, max_power_kw=None)
    scenario = {"participants": [{"id": "P", "battery": battery}]}
    alone = ceiling.alone_days(agent_steps, steps, scenario)
    assert alone.bill.sum() == pytest.approx(-0.4)
    assert alone.stored_change_kwh.sum() == pytest.approx(0.0)


def test_each_day_is_its_own_horizon():
    # ``held_out``'s days apart: d1's surplus cannot reach d2's deficit, and P2's
    # battery starts each day at its initial 5 kWh and must end there: d2's 2 kWh are
    # bought even at the ceiling.
    agent_steps, steps, scenario = held_out()
    top, alone = ceiling.day_references(agent_steps, steps, scenario)
    assert top.team_money.tolist() == pytest.approx([0.0, -1.0])
    assert alone.groupby("day").bill.sum().tolist() == pytest.approx([0.0, -1.0])


def test_the_technical_indices_over_the_period():
    rows = [
        ("d1", 0, "P1", 4.0, 0.0), ("d1", 0, "P2", 0.0, 1.0),
        ("d2", 0, "P1", 1.0, 0.0), ("d2", 0, "P2", 0.0, 5.0),
    ]
    a = pd.DataFrame(rows, columns=["day", "step", "agent", "demand_kwh",
                                    "generation_kwh"])
    a = a.assign(policy="p", period="x", charge_kwh=0.0, discharge_kwh=0.0)
    found = indicators._community_indicators(a)
    # Each day: |net| 3 over 5 and 4 over 6; the period: 7 over 11, on both days.
    assert found.energy_balance_index[("p", "d1")] == pytest.approx(1 - 3 / 5)
    assert found.energy_balance_index_period.tolist() == pytest.approx([1 - 7 / 11] * 2)
    assert found.peak_to_average_period[("p", "d1")] == pytest.approx(4 / 3.5)


def test_without_a_battery_no_program_is_solved(monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("linprog called without a battery")

    monkeypatch.setattr(ceiling, "linprog", never)
    plan = optimise(NET, FIT, UTIL)
    assert plan.value == pytest.approx(-1.0)
    assert plan.steps["import"].tolist() == [0.0, 2.0]
    assert plan.charge.shape == (2, 0)  # no battery columns, as from the program
    # With a feed-in tariff above the utility price buying to sell would pay: the
    # program decides (and finds no bounded optimum).
    monkeypatch.undo()
    with pytest.raises(ValueError):
        optimise(NET, np.array([0.6, 0.6]), UTIL)
