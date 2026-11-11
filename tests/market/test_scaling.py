"""The network under more stress (MP-4i): ``grid.load_scale``, ``generation_scale``
and ``storage_scale`` multiply the power of every element of their kind, the
participants' included, where the power is read: their demand and generation, their
batteries, and the background in the power flow. 1.0 changes nothing."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from core.config import store
from core.market.lem import LocalEnergyMarket
from core.runner.ceiling import _batteries

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"


def market(**scales) -> LocalEnergyMarket:
    scenario = store.load(SCENARIO)
    for name, value in scales.items():
        setattr(scenario.grid, name, value)
    m = LocalEnergyMarket(scenario)
    m.reset()
    return m


@pytest.fixture(scope="module")
def plain() -> LocalEnergyMarket:
    return market()


def test_one_changes_nothing(plain):
    same = market(load_scale=1.0, generation_scale=1.0, storage_scale=1.0)
    day = plain.scenario.grid.day
    assert same.profiles(day) == plain.profiles(day)


def test_participants_demand_and_generation_scale_by_their_kind(plain):
    day = plain.scenario.grid.day
    scaled = market(load_scale=1.5, generation_scale=2.0)
    before, after = plain.profiles(day), scaled.profiles(day)

    for pid, (generation, demand) in before.items():
        np.testing.assert_allclose(after[pid][0], 2.0 * np.array(generation))
        np.testing.assert_allclose(after[pid][1], 1.5 * np.array(demand))


def test_batteries_scale_in_the_market_and_in_the_ceiling(plain):
    scaled = market(storage_scale=2.0)

    for pid, p in plain.participants.items():
        if p.battery is None:
            continue
        b, c = p.battery.setup, scaled.participants[pid].battery.setup
        assert c.capacity_kwh == pytest.approx(2.0 * b.capacity_kwh)
        assert c.max_power_kw == pytest.approx(2.0 * b.max_power_kw)
        assert c.initial_soc == b.initial_soc

    saved = {"grid": {"storage_scale": 2.0}, "participants": [
        {"id": "A", "battery": {"capacity_kwh": 10.0, "max_power_kw": 5.0}},
        {"id": "B", "battery": None},
    ]}
    assert _batteries(saved) == {"A": {"capacity_kwh": 20.0, "max_power_kw": 10.0}}


def test_the_background_scales_in_the_power_flow():
    """At noon, every generator not taken over by a participant injects twice as
    much."""
    plain, scaled = market(), market(generation_scale=2.0)
    for _ in range(13):  # steps 0-12: the last one played is noon
        plain.step()
        scaled.step()
    owned = plain.grid._owned_rows["sgen"]
    a, b = plain.grid._net.sgen.p_mw, scaled.grid._net.sgen.p_mw
    free = [i for i in a.index if i not in owned]

    assert free and a[free].abs().sum() > 0
    np.testing.assert_allclose(b[free], 2.0 * a[free])


def test_a_negative_factor_is_a_scenario_problem():
    scenario = deepcopy(store.load(SCENARIO))
    scenario.grid.generation_scale = -1.0
    assert any("Generation scale" in p for p in scenario.problems())


def test_the_studio_shows_the_scaled_day():
    """The Scenario and Summary pages' day view reads the same scaled power as the
    market: a participant's generation in the view is its market generation."""
    from studio.adapters.profile_service import ProfileService

    scenario = store.load(SCENARIO)
    scenario.grid.generation_scale, scenario.grid.load_scale = 2.0, 1.5
    day = ProfileService().day_profiles(scenario)
    m = LocalEnergyMarket(scenario)
    m.reset()
    hours = scenario.grid.step_hours

    for pid, (generation, demand) in m.profiles(scenario.grid.day).items():
        mine = [e for e in day.elements if e.owner == pid]
        g = np.sum([e.kw for e in mine if e.element_type == "sgen"] or [[0.0]], axis=0)
        d = np.sum([e.kw for e in mine if e.element_type == "load"] or [[0.0]], axis=0)
        np.testing.assert_allclose(np.broadcast_to(g * hours, len(generation)), generation)
        np.testing.assert_allclose(np.broadcast_to(d * hours, len(demand)), demand)
