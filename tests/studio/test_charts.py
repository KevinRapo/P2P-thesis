"""The Studio's chart classes (``studio/components/charts.py``), built from the
Components page's made-up data, without a browser."""

from __future__ import annotations

import pytest

from studio.components.charts import (
    Chart,
    DayChart,
    ElementsChart,
    NetworkChart,
    SeriesChart,
)
from studio.pages.components import DAY, HOURS, LabChart, SUN, TOPOLOGY, VOLTAGES
from studio.theme import BUS, LIMIT, SERIES


class TwoLines(SeriesChart):
    y_title = "kW"

    def draw(self) -> None:
        self.line(HOURS, SUN, "a")
        self.line(HOURS, SUN, "b", right=self.o.right)
        self.level(1.0, "limit", color=LIMIT)


def test_a_series_chart_draws_its_lines_levels_and_look():
    fig = TwoLines(right=False).figure()

    assert [t.name for t in fig.data] == ["a", "b"]
    assert [t.line.color for t in fig.data] == SERIES[:2]  # the palette, in order
    assert len(fig.layout.shapes) == 1  # the level
    assert fig.layout.yaxis.title.text == "kW"
    assert fig.layout.height == 300
    assert "yaxis2" not in fig.to_dict()["layout"]  # no right axis


def test_set_changes_an_option_and_the_figure_follows():
    chart = TwoLines(right=False)
    chart.set(right=True)  # not shown yet: only the option changes

    fig = chart.figure()
    assert fig.data[1].yaxis == "y2" and fig.layout.yaxis2.overlaying == "y"


def test_the_day_chart_sums_by_type_in_the_energy_colours():
    fig = DayChart(day=DAY, elements=DAY.owned()).figure()

    assert [t.name for t in fig.data] == ["Demand (2)", "Generation (1)"]
    assert fig.data[1].y == tuple(SUN)
    assert {t.line.shape for t in fig.data} == {"hv"}


def test_elements_chart_takes_its_y_title_from_the_options():
    chart = ElementsChart(day=DAY, lines={"x": SUN}, y_title="net kW")
    assert chart.figure().layout.yaxis.title.text == "net kW"


def test_the_network_by_kind_or_by_voltage():
    by_kind = NetworkChart(topology=TOPOLOGY, highlight={"B2"}).figure()
    buses = [t for t in by_kind.data if t.mode == "markers"]
    assert {t.marker.color for t in buses} <= set(BUS.values())
    assert any("B2" in t.customdata for t in buses)

    by_voltage = NetworkChart(topology=TOPOLOGY, voltages=VOLTAGES).figure()
    buses = [t for t in by_voltage.data if t.mode == "markers"]
    assert len(buses) == 1 and buses[0].marker.cmin == 0.93


def test_links_and_rings_skip_buses_the_network_lacks():
    class Overlay(NetworkChart):
        def draw(self) -> None:
            self.links([("B3", "B2", 2.0, ""), ("B3", "nowhere", 1.0, "")], "red", "L")
            self.rings([("B4", ""), ("nowhere", "")], "blue", "R")

    fig = Overlay(topology=TOPOLOGY).figure()
    links = [t for t in fig.data if t.name == "L"]
    rings = [t for t in fig.data if t.name == "R"]
    assert len(links) == 1 and links[0].line.width == 6.5  # the largest: 1.5 + 5
    assert len(rings) == 1 and len(rings[0].x) == 1


def test_network_charts_apply_the_shared_layout_options_on_every_draw():
    class Overlay(NetworkChart):
        def draw(self) -> None:
            self.after(title_text=self.o.title, showlegend=False)
            self.titles(x="distance")

    chart = Overlay(topology=TOPOLOGY, title="First")
    first = chart.figure()
    chart.set(title="Second")
    second = chart.figure()

    assert first.layout.title.text == "First"
    assert second.layout.title.text == "Second"
    assert second.layout.showlegend is False
    assert second.layout.hovermode == "closest"
    assert second.layout.xaxis.title.text == "distance"
    assert second.layout.yaxis.scaleanchor == "x"
    assert len(first.data) == len(second.data)  # drawing again does not add old traces


def test_a_plain_chart_gets_the_look_and_its_layout():
    class Box(Chart):
        layout = {"hovermode": "closest"}

        def draw(self) -> None:
            self.fig.add_box(y=[1, 2, 3])

    fig = Box(height=200).figure()
    assert fig.layout.height == 200 and fig.layout.hovermode == "closest"


@pytest.mark.parametrize("bars", [False, True])
def test_every_look_of_the_style_lab_draws(bars):
    options = dict(shape="hv", dash="dot", width=3, opacity=0.5, color="")
    options |= dict(markers=True, band=True, right=True, levels=True, pixels=360)
    fig = LabChart(bars=bars, **options).figure()

    assert fig.layout.height == 360
    assert fig.data[-1].name == "PV" and fig.data[-1].yaxis == "y2"
