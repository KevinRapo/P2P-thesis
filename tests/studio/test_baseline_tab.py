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
    monkeypatch.setattr(tab_module, "services", lambda: fake_services(saved))

    async def root() -> None:
        tab_module.tab()

    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see("validate_market: 5 participants")
        sweep = next(iter(user.find("Sweep").elements))
        sweep.value = "generation_scale"
        values = next(iter(user.find("Values").elements))
        values.value = "1, 2"
        user.find("Play").click()

        # One day under each value, then once more as it is: a few seconds
        await user.should_see("Use in the scenario", retries=600)
        assert saved == []  # the sweep changed nothing
