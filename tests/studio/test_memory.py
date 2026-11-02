"""Coming back to a page: each visit builds it anew, and what the browser chose comes
back (``studio/components/memory.py``). A second ``user.open`` is that visit."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from nicegui import app, ui
from nicegui.testing.user_simulation import user_simulation

from studio.adapters.profile_service import ProfileService
from studio.components.charts import SeriesChart
from studio.components.memory import keep, recalled, remember
from studio.components.network import is_day
from studio.pages import inspect


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_a_choice_comes_back_on_the_next_visit():
    built: list = []

    def root() -> None:
        built.append(remember(ui.select(["a", "b"], value="a"), "t_choice"))

    async with user_simulation(root) as user:
        await user.open("/")
        assert built[-1].value == "a"
        built[-1].set_value("b")

        await user.open("/")
        assert len(built) == 2 and built[-1].value == "b"


@pytest.mark.anyio
async def test_a_choice_no_longer_offered_is_the_default_not_a_crash():
    built: list = []

    def root() -> None:
        app.storage.user["t_gone"] = "deleted"
        built.append(remember(ui.select(["a", "b"], value="a"), "t_gone"))

    async with user_simulation(root) as user:
        await user.open("/")
        assert built[-1].value == "a"


@pytest.mark.anyio
async def test_bringing_a_value_back_runs_no_handler_connected_after_it():
    calls: list = []

    def root() -> None:
        app.storage.user["t_quiet"] = "b"
        choice = remember(ui.select(["a", "b"], value="a"), "t_quiet")
        calls.append(choice.value)
        choice.on_value_change(lambda e: calls.append("handler"))

    async with user_simulation(root) as user:
        await user.open("/")
        assert calls == ["b"]


@pytest.mark.anyio
async def test_the_rest_keeps_a_value_and_rules_one_out():
    def root() -> None:
        keep("t_list", ["x"])
        assert recalled("t_list") == ["x"]
        assert recalled("t_list", "default", allowed=["y"]) == "default"
        assert recalled("t_none", "default") == "default"
        assert recalled("t_list", "default", allowed=lambda v: False) == "default"

    async with user_simulation(root) as user:
        await user.open("/")


def test_a_half_typed_start_day_is_no_day():
    assert is_day("2016-06-15")
    assert not is_day("2016-06-")
    assert not is_day(None)


class _Line(SeriesChart):
    def draw(self) -> None:
        self.line([0, 1], [1, 2], self.o.name)


@pytest.mark.anyio
async def test_a_charts_controls_come_back_and_redraw_it():
    charts: list = []

    def root() -> None:
        chart = _Line(name="a", band=False).show()
        chart.memory = "t_chart"
        chart.select("name", ["a", "b"], "Name")
        chart.switch("band", "Band")
        charts.append(chart)

    async with user_simulation(root) as user:
        await user.open("/")
        assert charts[-1].fig.data[0].name == "a"
        keep_name = next(iter(user.find(kind=ui.select).elements))
        keep_name.set_value("b")
        assert charts[-1].fig.data[0].name == "b"

        await user.open("/")
        assert charts[-1].o.name == "b" and charts[-1].fig.data[0].name == "b"


@pytest.mark.anyio
async def test_a_chart_without_memory_keeps_nothing():
    def root() -> None:
        chart = _Line(name="a").show()
        chart.select("name", ["a", "b"], "Name")
        ui.label(str(sorted(k for k in app.storage.user if "name" in k)))

    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see("[]")


@pytest.mark.anyio
async def test_the_prices_tab_comes_back_also_from_a_half_typed_day():
    charts: list = []

    class Chart(inspect.PriceChart):
        def __init__(self, *args, **options):
            super().__init__(*args, **options)
            charts.append(self)

    def root() -> None:
        inspect.PriceChart = Chart
        inspect._prices_tab(SimpleNamespace(profiles=ProfileService()))

    original = inspect.PriceChart

    try:
        async with user_simulation(root) as user:
            await user.open("/")
            next(iter(user.find(marker="price-file").elements)).set_value(
                "de_2024_flat"
            )
            day = next(iter(user.find(kind=ui.input).elements))
            day.set_value("2024-03-04")

            await user.open("/")
            assert charts[-1].o.name == "de_2024_flat"
            assert charts[-1].fig.data[0].x[0] == "2024-03-04 00:00"

            next(iter(user.find(kind=ui.input).elements)).set_value("2024-03-")
            await user.open("/")  # the day is left half typed: the default, no crash
            assert charts[-1].fig.data[0].x[0] == "2024-06-19 00:00"
    finally:
        inspect.PriceChart = original
