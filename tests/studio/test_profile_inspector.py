"""The Inspect page's network profiles: the whole network and SimBench's study cases."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from core.grid.contract import NetworkRef
from studio.adapters.profile_service import ProfileService
from studio.components import network

REF = NetworkRef("simbench", "1-LV-rural3--2-sw")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_the_whole_network_with_a_study_case(monkeypatch):
    charts: list = []

    class Chart(network.NetworkPowerChart):
        def __init__(self, *args, **options):
            super().__init__(*args, **options)
            charts.append(self)

    monkeypatch.setattr(network, "NetworkPowerChart", Chart)
    holder = {}

    def root() -> None:
        holder["inspector"] = network.ProfileInspector(
            SimpleNamespace(profiles=ProfileService())
        )

    async with user_simulation(root) as user:
        await user.open("/")
        inspector = holder["inspector"]
        await inspector.show(REF)
        assert not inspector.case.visible  # only with the whole network

        inspector.view.set_value("network")
        await user.should_see("Whole network: every load")
        assert inspector.case.visible
        series = charts[-1].o.series
        assert list(series.y) == [
            "Demand (153)",
            "Generation (27)",
            "Storage (16)",
            "Net demand",
        ]
        assert not charts[-1].o.levels

        inspector.case.set_value("hL")
        await user.should_see("Upstream voltage 0.965 pu")
        assert charts[-1].o.levels["Demand (153)"] == pytest.approx(552.8)
        assert charts[-1].o.case == "hL"
        assert len(charts[-1].fig.layout.shapes) == 3  # demand, generation, net
        assert user.find(kind=ui.select).elements  # the case picker
