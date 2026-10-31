"""Loading a box must not let an obsolete request replace the current content."""

import asyncio
from types import SimpleNamespace

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from studio.components import cards


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_card_containers_keep_content_in_the_right_parent():
    placed = {}

    def root():
        with cards.stat_grid() as grid:
            with cards.section("Title", "Caption", "info") as card:
                body = ui.label("Body")

            sibling = ui.label("Sibling")

        outside = ui.label("Outside")
        placed.update(grid=grid, card=card, body=body, sibling=sibling, outside=outside)

    async with user_simulation(root) as user:
        await user.open("/")
        assert placed["body"].parent_slot.parent is placed["card"]
        assert placed["card"].parent_slot.parent is placed["grid"]
        assert placed["sibling"].parent_slot.parent is placed["grid"]
        assert placed["outside"].parent_slot.parent is not placed["grid"]
        await user.should_see("Title")
        await user.should_see("Caption")


@pytest.mark.anyio
@pytest.mark.parametrize("obsolete", [False, True])
@pytest.mark.parametrize("fails", [False, True])
@pytest.mark.parametrize("view", ["helper", "results"])
async def test_fill_handles_current_and_obsolete_results(
    monkeypatch, obsolete, fails, view
):
    started, release = asyncio.Event(), asyncio.Event()
    state = {"current": True}

    async def read(_):
        started.set()
        await release.wait()

        if fails:
            raise ValueError("read failed")

        return "Read result"

    monkeypatch.setattr(cards.run, "io_bound", read)

    def root():
        state["box"] = ui.column()

        if view == "results":
            from studio.pages.results.page import ResultsView

            page = ResultsView.__new__(ResultsView)
            page.box = state["box"]
            page.table = SimpleNamespace(selected=["run"])
            page.bar = SimpleNamespace(value="tab")
            page.tabs = {
                "tab": SimpleNamespace(
                    read=lambda keys: None, build=lambda keys, data: ui.label(data)
                )
            }
            page._drawn = 0
            state["page"] = page

    async with user_simulation(root) as user:
        await user.open("/")
        task = asyncio.create_task(
            state["page"].show()
            if view == "results"
            else cards.fill(
                state["box"],
                lambda: None,
                ui.label,
                current=lambda: state["current"],
            )
        )
        await asyncio.wait_for(started.wait(), 2)

        if obsolete:
            state["current"] = False

            if view == "results":
                state["page"]._drawn += 1

            state["box"].clear()

            with state["box"]:
                ui.label("New selection")

        release.set()
        result = await asyncio.wait_for(task, 2)
        expected = (
            "New selection"
            if obsolete
            else ("Failed: read failed" if fails else "Read result")
        )
        await user.should_see(expected)
        if view == "helper":
            assert result == (None if obsolete or fails else "Read result")

        if obsolete:
            await user.should_not_see("Read result")
            await user.should_not_see("Failed: read failed")
