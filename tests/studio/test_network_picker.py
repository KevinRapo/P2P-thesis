"""The network picker when the server stops while it reads the catalog."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from nicegui.testing.user_simulation import user_simulation

from studio.components import network


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_a_read_ended_by_the_server_stopping_changes_nothing(monkeypatch):
    pickers: list = []

    async def stopping(*_) -> None:  # NiceGUI's answer while the server stops
        return None

    async def on_pick(_) -> None:
        pass

    def root() -> None:
        services = SimpleNamespace(grid=SimpleNamespace(list_networks=None))
        pickers.append(network.NetworkPicker(services, network.DEFAULT_SOURCE, on_pick))

    monkeypatch.setattr(network, "run", SimpleNamespace(io_bound=stopping))

    async with user_simulation(root) as user:
        await user.open("/")
        await pickers[0]._on_source()
        assert pickers[0].networks == []
