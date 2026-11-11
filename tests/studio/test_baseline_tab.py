"""The Market page's Baseline tab plays the Scenario page's scenario with the rule,
alone or as a sweep, and saves a picked value only when asked."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui.testing import user_simulation

from core.config import store
from core.grid.contract import BranchView, BusView, TopologyView
from studio.pages.market import baseline as tab_module

SCENARIO = Path(__file__).resolve().parents[2] / "config/scenarios/validate_market.json"


def fake_services(saved: list):
    scenario = store.load(SCENARIO)
    topology = TopologyView(
        (BusView("A", 0.0, 0.0, "load", 0.4), BusView("B", 1.0, 0.0, "load", 0.4)),
        (BranchView("L1", "A", "B", "line"),),
        "A",
    )
    return SimpleNamespace(
        scenario=SimpleNamespace(
            current=lambda: scenario,
            shown_name=lambda: "validate_market",
            save=lambda: saved.append(scenario.grid.generation_scale),
        ),
        grid=SimpleNamespace(topology=lambda source: topology),
    )


@pytest.mark.anyio
async def test_a_sweep_plays_and_saves_nothing_until_asked(monkeypatch):
    saved: list = []
    fake = fake_services(saved)
    monkeypatch.setattr(tab_module, "services", lambda: fake)

    async def root() -> None:
        tab_module.tab()

    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see("validate_market: 5 participants")
        generation = next(iter(user.find("Generation × values").elements))
        generation.value = "2, 1"
        load = next(iter(user.find("Load × values").elements))
        load.value = "1.5"
        user.find("Play").click()

        # Two combinations of one day: a few seconds
        await user.should_see("Use in the scenario", retries=600)
        await user.should_see("Generation ×2, Load ×1.5")
        assert saved == []  # the sweep changed nothing
        user.find("Use in the scenario").click()  # the row shown first: ×2, ×1.5
        assert saved == [2.0]
        assert fake.scenario.current().grid.load_scale == 1.5
