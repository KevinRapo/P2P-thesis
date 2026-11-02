"""Indicators from a run's tables, and comparing any runs."""

import numpy as np
import pandas as pd
import pytest

from core.market.signals import KPIS
from core.runner import indicators
from core.runner.indicators import INDICATORS, day_table

DAYS = ["d1", "d2"]


def tables():
    """Two policies and ``zero``'s twin on two days of two steps, two participants."""
    episodes, agents, steps, agent_steps = [], [], [], []

    for policy, gain in (("trained", 3.0), ("zero", 0.0), ("net_position", 1.0)):
        for day in DAYS:
            episodes.append({"policy": policy, "day": day, "p2p_kwh": 2.0})

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
                        "grid_import_kwh": 6.0,
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


def test_the_kpis_are_the_markets():
    assert set(indicators.KPIS) == set(KPIS)


def test_a_day_of_a_run():
    day = day_table(*tables()).loc[("trained", "d1")]
    assert day.team_money == 2.0
    assert day.gain_zero == 3.0 and day.gain_net_position == 2.0
    assert day.participants_better == 1
    assert day.peak_import_kw == 0.5 and day.peak_export_kw == 1.0  # 12 h steps
    assert day.hours_over_limit == 12.0
    assert day.fee_error_mean == 10.0 and day.fee_error_worst == 10.0
    assert day.mean_peer_price == pytest.approx(0.2)
    assert day.peer_price_position == pytest.approx(0.5)
    assert day.trading_ratio == pytest.approx((2 + 6) / (4 + 6))
    assert day.local_coverage == pytest.approx(1 - 1 / 4)  # 1 of 4 kWh from the DSO
    assert day.battery_throughput_kwh == 2.0
    assert day.end_reputation == 0.6
    assert day.buy_share == 0.5 and day.no_order_share == 0.0
    money = 2 * 1 * 0.1  # a surplus of 1 at each step, at the feed-in tariff
    assert day.reachable_share == pytest.approx(3.0 / (money - -1.0))


def test_an_older_run_leaves_what_it_lacks_empty():
    episodes, agents, _, _ = tables()
    days = day_table(episodes, agents)
    assert list(days.columns) == [i.name for i in INDICATORS]
    assert days.loc[("trained", "d1")].team_money == 2.0
    assert days.highest_line_loading.isna().all()


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
    )


def two_rewards(other_days=("d1", "d2")):
    rows = []

    for seed in (0, 1):
        for day, offset in zip(DAYS, (0.0, 10.0)):
            rows.append(
                (f"a{seed}", seed, "ctde", "bill", day, "trained", offset + seed)
            )
            rows.append((f"a{seed}", seed, "ctde", "bill", day, "zero", -5.0))

        for day, offset in zip(other_days, (0.0, 10.0)):
            value = offset + seed + 2.0
            rows.append((f"b{seed}", seed, "ctde", "salazar", day, "trained", value))
            rows.append((f"b{seed}", seed, "ctde", "salazar", day, "zero", -5.0))

    return long(rows)


def test_side_by_side_takes_any_runs():
    found = indicators.side_by_side(two_rewards(("d8", "d9")), ["reward"])
    row = found.set_index("reward").loc["salazar"]
    assert row["mean"] == 7.5 and row["values"] == [7.0, 8.0] and "low" not in found


def test_baselines_are_one_row_however_many_runs():
    found = indicators.baselines(two_rewards())
    assert len(found) == 1 and found.value.iloc[0] == -5.0


def test_against_its_own_baseline():
    found = indicators.against_baseline(two_rewards(), "zero")
    assert set(found.policy) == {"trained"}
    assert found[found.key == "a0"].value.tolist() == [5.0, 15.0]


def test_a_difference_is_paired_when_days_match_and_says_when_not():
    found = indicators.difference(two_rewards(), "reward", "bill").iloc[0]
    assert found.paired and found["mean"] == 2.0 and found["values"] == [2.0, 2.0]
    found = indicators.difference(two_rewards(("d8", "d9")), "reward", "bill").iloc[0]
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
