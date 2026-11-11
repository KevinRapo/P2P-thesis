"""Indicators from a run's tables, and comparing any runs."""

import numpy as np
import pandas as pd
import pytest

from core.market.dso import DSO_ID
from core.market.signals import KPIS
from core.runner import indicators
from core.runner.indicators import INDICATORS, day_table

DAYS = ["d1", "d2"]


def trade(step, buyer, seller, price, kwh, stage=2):
    return {
        "policy": "trained",
        "day": "d1",
        "step": step,
        "buyer": buyer,
        "seller": seller,
        "price": price,
        "kwh": kwh,
        "stage": stage,
        "buyer_fee": 0.1,
        "seller_fee": 0.0,
        "peer_charge": 0.0,
    }


def trades():
    """``trained`` on ``d1``: three peer trades at 0.2 between tariffs of 0.1 and
    0.3, and one each way with the DSO; no trades otherwise."""
    rows = [
        trade(0, "P1", "P2", 0.2, 3.0),
        trade(1, "P1", "P2", 0.2, 1.0),
        trade(1, "P2", "P1", 0.2, 4.0, stage=1),
        trade(0, "P1", "DSO", 0.3, 2.0, stage=3),
        trade(1, "DSO", "P2", 0.1, 1.0, stage=3),
    ]

    return pd.DataFrame(rows)


def tables():
    """Two policies on two days of two steps, two participants."""
    episodes, agents, steps, agent_steps = [], [], [], []

    for policy, gain in (("trained", 3.0), ("net_position", 1.0)):
        for day in DAYS:
            episodes.append(
                {
                    "policy": policy,
                    "day": day,
                    "p2p_kwh": 2.0,
                    "bought_from_dso_kwh": 1.0,
                    "sold_to_dso_kwh": 1.0,
                    "trade_losses_kwh": 0.4,
                    "peer_trades": 3,
                }
            )

            for agent, bill in (("P1", gain), ("P2", -1.0)):
                agents.append(
                    {
                        "policy": policy,
                        "day": day,
                        "agent": agent,
                        "bill": bill,
                        "deferred_demand_kwh": 1.0,
                        "deferred_supply_kwh": 0.0,
                        "stored_change_kwh": -1.0,
                    }
                )

            for step in (0, 1):
                steps.append(
                    {
                        "policy": policy,
                        "day": day,
                        "step": step,
                        "p2p_kwh": 1.0,
                        "peer_price": 0.2 if step else np.nan,
                        "feed_in_tariff": 0.1,
                        "utility_price": 0.3,
                        "grid_import_kwh": (2 if policy == "net_position" else 1)
                        * (step + 1),
                        "mean_line_loading_percent": 20.0 + step,
                        "grid_export_kwh": step * 12.0,
                        "voltage_violations": step,
                        "loading_violations": 0,
                        "max_line_loading_percent": 50.0 + step,
                        "fee_max_line_loading_percent": 40.0 + step,
                        "max_trafo_loading_percent": 30.0,
                        "min_voltage_pu": 0.98,
                        "max_voltage_pu": 1.02,
                    }
                )

                for agent, demand, generation in (("P1", 2.0, 0.0), ("P2", 0.0, 3.0)):
                    agent_steps.append(
                        {
                            "policy": policy,
                            "day": day,
                            "step": step,
                            "agent": agent,
                            "demand_kwh": demand,
                            "generation_kwh": generation,
                            "bought_kwh": demand / 2,
                            "sold_kwh": generation,
                            "peer_bought_kwh": demand / 4,
                            "deferred_demand_kwh": 0.0,
                            "charge_kwh": 0.5,
                            "discharge_kwh": 0.0,
                            "reputation": 0.6,
                            "side": "buy" if demand else "sell",
                        }
                    )

    return tuple(pd.DataFrame(t) for t in (episodes, agents, steps, agent_steps))


def alone():
    """Each participant's non-P2P money on each day: P1 0, P2 -1 (``alone_days``)."""
    return pd.DataFrame(
        [
            {"day": d, "agent": a, "bill": b, "stored_change_kwh": 0.0, "period": "p"}
            for d in DAYS
            for a, b in (("P1", 0.0), ("P2", -1.0))
        ]
    )


def test_the_kpis_are_the_markets():
    assert set(indicators.KPIS) == set(KPIS)


def test_the_dso_is_the_markets():
    assert indicators.DSO == DSO_ID


def test_a_day_of_a_run():
    day = day_table(*tables(), alone=alone()).loc[("trained", "d1")]
    assert day.team_money == 2.0
    assert day.gain_net_position == 2.0
    assert day.participants_better == 1  # P1 beats its 0 alone; P2 only equals its -1
    assert day.peak_import_kw == 2 / 12 and day.peak_export_kw == 1.0  # 12 h steps
    assert day.hours_over_limit == 12.0
    assert day.fee_error_mean == 10.0 and day.fee_error_worst == 10.0
    assert day.mean_peer_price == pytest.approx(0.2)
    assert day.peer_price_position == pytest.approx(0.5)
    assert day.trading_ratio == pytest.approx((2 + 6) / (4 + 6))
    assert day.local_coverage == pytest.approx(1 - 1 / 4)  # 1 of 4 kWh from the DSO
    assert day.battery_throughput_kwh == 2.0
    assert day.end_reputation == 0.6
    assert day.buy_share == 0.5 and day.no_order_share == 0.0


def test_the_indicators_of_the_trades():
    days = day_table(*tables(), trades())
    day = days.loc[("trained", "d1")]
    assert day.peer_trades == 3
    assert day.mean_trade_kwh == pytest.approx(8 / 3)
    assert day.market_concentration == pytest.approx(0.5**2 + 0.5**2)
    assert day.buyer_gain == pytest.approx(0.1 * 8)
    assert day.seller_gain == pytest.approx(0.1 * 8)
    assert day.dso_money == pytest.approx(0.3 * 2 - 0.1 * 1 + 5 * 0.1)
    quiet = days.loc[("net_position", "d1")]
    assert quiet.buyer_gain == 0.0 and quiet.dso_money == 0.0


def test_the_dso_is_paid_for_the_demand_left_untraded_and_the_buyer_pays_the_charge():
    episodes, agents, steps, agent_steps = tables()
    agent_steps["deferred_demand_kwh"] = 1.0  # per agent and step: 2 kWh a step
    rows = trades().assign(peer_charge=0.05)
    day = day_table(episodes, agents, steps, agent_steps, rows).loc[("trained", "d1")]
    assert day.buyer_gain == pytest.approx(0.1 * 8 - 0.05 * 3)  # three peer trades
    # the fixture's 0.5 plus 4 kWh drawn untraded at the utility price of 0.3
    assert day.dso_money == pytest.approx(0.3 * 2 - 0.1 * 1 + 5 * 0.1 + 4 * 0.3)
    quiet = day_table(episodes, agents, steps, agent_steps, rows).loc[
        ("net_position", "d1")
    ]
    assert quiet.dso_money == pytest.approx(4 * 0.3)
    assert np.isnan(quiet.mean_trade_kwh) and np.isnan(quiet.market_concentration)


def test_the_indicators_of_the_other_tables():
    day = day_table(*tables(), alone=alone()).loc[("trained", "d1")]
    assert day.worst_participant_gain == 0.0  # P2's bill is the same as alone
    assert day.self_sufficiency == pytest.approx(1 - 1 / 4)
    assert day.load_factor == pytest.approx(1.5 / 2)
    assert day.peak_reduction_kw == pytest.approx(2 / 12)
    assert day.trade_loss_ratio == pytest.approx(0.4 / 4)
    assert day.mean_line_loading == pytest.approx(20.5)


def test_an_older_run_leaves_what_it_lacks_empty():
    episodes, agents, _, _ = tables()
    days = day_table(episodes, agents)
    assert list(days.columns) == [i.name for i in INDICATORS]
    assert days.loc[("trained", "d1")].team_money == 2.0
    assert days.highest_line_loading.isna().all()
    assert days.mean_trade_kwh.isna().all() and days.load_factor.isna().all()
    steps = tables()[2].drop(columns="mean_line_loading_percent")
    older = day_table(episodes, agents, steps, tables()[3])
    assert older.mean_line_loading.isna().all() and older.buyer_gain.isna().all()


def long(rows):
    """A long table: (key, seed, paradigm, reward, day, policy, value)."""
    names = ["key", "seed", "paradigm", "reward", "day", "policy", "value"]
    frame = pd.DataFrame(rows, columns=names)

    return frame.assign(
        indicator="team_money",
        observation="paper",
        prices="p",
        network="n",
        peer_charge=0.0,
        grid_method="ac",
        test_days="d",
        participants=13,
        participant_set="13 (abc123)",
        batteries=5,
    )


def two_rewards(other_days=("d1", "d2")):
    rows = []

    for seed in (0, 1):
        for day, offset in zip(DAYS, (0.0, 10.0)):
            rows.append(
                (f"a{seed}", seed, "ctde", "bill", day, "trained", offset + seed)
            )
            rows.append((f"a{seed}", seed, "ctde", "bill", day, "net_position", -5.0))

        for day, offset in zip(other_days, (0.0, 10.0)):
            value = offset + seed + 2.0
            rows.append((f"b{seed}", seed, "ctde", "salazar", day, "trained", value))
            rows.append((f"b{seed}", seed, "ctde", "salazar", day, "net_position", -5.0))

    return long(rows)


def test_side_by_side_takes_any_runs():
    found = indicators.side_by_side(two_rewards(("d8", "d9")), ["reward"])
    row = found.set_index("reward").loc["salazar"]
    assert row["mean"] == 7.5 and row["values"] == [7.0, 8.0] and "low" not in found


def test_baselines_are_one_row_however_many_runs():
    found = indicators.baselines(two_rewards())
    assert len(found) == 1 and found.value.iloc[0] == -5.0


def test_against_its_own_baseline():
    found = indicators.against_baseline(two_rewards(), "net_position")
    assert set(found.policy) == {"trained"}
    assert found[found.key == "a0"].value.tolist() == [5.0, 15.0]


def test_a_difference_is_paired_when_days_match_and_says_when_not():
    found = indicators.difference(two_rewards(), "reward", "bill").iloc[0]
    assert found.paired and found["mean"] == 2.0 and found["values"] == [2.0, 2.0]
    found = indicators.difference(two_rewards(("d8", "d9")), "reward", "bill").iloc[0]
    assert not found.paired and found["mean"] == 2.0


def test_a_difference_is_not_paired_across_participant_sets():
    """Same days, prices and network, but as many participants placed elsewhere
    (RP-7h): the two sides played different markets, so they are not paired."""
    table = two_rewards()
    table.loc[table.reward == "salazar", "participant_set"] = "13 (def456)"
    found = indicators.difference(table, "reward", "bill").iloc[0]
    assert not found.paired and found["mean"] == 2.0


def test_a_difference_splits_on_what_else_differs_and_pools_on_request():
    table = pd.concat([two_rewards(), two_rewards().assign(paradigm="dtde")])
    table["key"] = table.key + table.paradigm
    assert len(indicators.difference(table, "reward", "bill")) == 2
    assert len(indicators.difference(table, "reward", "bill", within=[])) == 1


def test_an_interval_starts_at_five_seeds():
    assert "low" not in indicators.spread([1.0, 2.0, 3.0, 4.0])
    row = indicators.spread([1.0, 2.0, 3.0, 4.0, 5.0])
    assert row["low"] < row["mean"] < row["high"]


def test_a_row_counts_seeds_not_runs():
    table = pd.concat([two_rewards(), two_rewards().assign(paradigm="dtde")])
    table["key"] = table.key + table.paradigm
    row = indicators.side_by_side(table, ["reward"]).iloc[0]
    assert row["n"] == 2 and row["values"] == [5.0, 6.0]


def test_a_pair_uses_only_the_days_both_sides_have():
    table = two_rewards()
    gone = (table.reward == "salazar") & (table.day == "d2")
    table.loc[gone, "value"] = np.nan
    found = indicators.difference(table, "reward", "bill").iloc[0]
    assert found.paired and found["mean"] == 2.0


def test_baselines_are_apart_by_what_they_were_played_on():
    table = pd.concat([two_rewards(), two_rewards().assign(grid_method="graph")])
    table["key"] = table.key + table.grid_method
    assert len(indicators.baselines(table)) == 2


def test_baselines_are_apart_by_the_participants_they_were_played_with():
    table = pd.concat([two_rewards(), two_rewards().assign(participants=43)])
    table["key"] = table.key + table.participants.astype(str)
    assert len(indicators.baselines(table)) == 2
    table = pd.concat([two_rewards(), two_rewards().assign(batteries=0)])
    table["key"] = table.key + table.batteries.astype(str)
    assert len(indicators.baselines(table)) == 2
