"""The scenario's baseline (``core/market/baseline.py``): its market played with the
bidding rule without noise, over a window of days."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import store
from core.market import baseline
from core.market.lem import LocalEnergyMarket, net_bill

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"
DAYS = ["2016-06-15", "2016-06-16"]


@pytest.fixture(scope="module")
def played():
    return baseline.play(store.load(SCENARIO), DAYS)


def test_a_day_is_the_market_played_with_the_rule_without_noise(played):
    """The first day is exactly the market with jitter 0 and no partners, step by
    step; the scenario given is not changed."""
    scenario = store.load(SCENARIO)
    jitter = scenario.market.bid_jitter
    market = LocalEnergyMarket(baseline.rule_scenario(scenario))
    market.scenario.grid.day = DAYS[0]
    market.reset()
    records = market.run_to_end()
    first = played.steps[played.steps.day == DAYS[0]]

    assert scenario.market.bid_jitter == jitter
    assert len(first) == len(records) == 24
    for row, record in zip(first.itertuples(), records):
        assert row.team_money == pytest.approx(
            sum(net_bill(record, pid) for pid in record.participants)
        )
        assert row.max_line_loading_percent == record.grid.max_line_loading_percent


def test_the_window_carries_the_batteries_into_the_next_day(played):
    assert len(played.steps) == 48 and list(played.steps.day.unique()) == DAYS
    assert len(played.line_loading) == len(played.bus_voltage) == 48
    assert played.worst_step() is not None


def test_the_summary_adds_up_the_steps(played):
    s = played.steps
    found = played.summary()
    assert found["steps"] == 48
    assert found["line_max_percent"] == s.max_line_loading_percent.max()
    assert found["team_money"] == pytest.approx(s.team_money.sum())
    assert found["grid_losses_kwh"] == pytest.approx(s.grid_losses_kwh.sum())
    assert 0 <= found["steps_violated"] <= 48


def test_a_sweep_plays_each_value_and_leaves_the_scenario_alone():
    scenario = store.load(SCENARIO)
    table = baseline.sweep(scenario, DAYS[:1], "grid.generation_scale", [1.0, 3.0])
    assert list(table["grid.generation_scale"]) == [1.0, 3.0]
    assert scenario.grid.generation_scale == 1.0
    # Three times the PV pushes more power into the lines at noon.
    assert table.line_max_percent[1] > table.line_max_percent[0]
