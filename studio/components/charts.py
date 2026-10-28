"""Plotly figures of the Studio, built from two general kinds.

**Series**: values along one axis (time of day, market step, environment steps,
cumulative kWh). A figure is a list of ``Line``s (what to draw and how) and
``Level``s (horizontal reference lines), drawn by ``series_figure``; a page with
subplots draws each panel with ``add_series`` and ``add_levels``. The figures of
the day (``day_figure``, ``element_figure``) and ``line_figure`` are such lists.

**Network**: ``topology_figure`` draws the buses and branches; ``add_links``
(lines between two buses, e.g. trades) and ``add_rings`` (rings around buses, e.g.
orders) draw on top of it.

Every figure gets the Studio's look from ``styled``; a figure stays a plain
``go.Figure``, so a page can still add anything to it. The colours with a meaning
are in ``studio/theme.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Sequence

import plotly.graph_objects as go

from core.grid.contract import BusView, TopologyView
from studio.adapters.models import DayElement, DayProfiles, Series
from studio.theme import BUS, ENERGY, HIGHLIGHT, LIMIT, MUTED, SERIES


# --------------------------------------------------------------------------------------
# The look: every figure ends here
# --------------------------------------------------------------------------------------
def styled(
    fig: go.Figure, height: int, y_title: str = "", x_title: str = ""
) -> go.Figure:
    """The Studio's look on any figure: height, transparent background, font, grid
    lines, legend below. An axis title is set only when given, so a title the
    figure already has stays."""
    fig.update_layout(
        height=height,
        margin=dict(l=48, r=16, t=12, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", size=12, color="#64748B"),
        legend=dict(orientation="h", y=-0.22, x=0),
        hovermode="x unified",
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.18)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.18)", zeroline=False)

    if x_title:
        fig.update_xaxes(title=x_title)

    if y_title:
        fig.update_yaxes(title=y_title)

    return fig


def palette(keys: Sequence[str]) -> dict[str, str]:
    """A colour per key from the series palette, in order (it cycles)."""
    return {key: SERIES[i % len(SERIES)] for i, key in enumerate(keys)}


def rgba(color: str, alpha: float) -> str:
    """A ``#rrggbb`` colour with transparency (for bands and fills)."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))

    return f"rgba({r},{g},{b},{alpha})"


# --------------------------------------------------------------------------------------
# Series: values along one axis
# --------------------------------------------------------------------------------------
@dataclass
class Line:
    """One series to draw: its values, and how it looks.

    Attributes:
        name: The legend's name (and the hover's).
        y: The values.
        x: Its own x values; default: the figure's x.
        color: Default: the next colour of the palette.
        dash: ``"solid"``, ``"dot"``, ``"dash"`` or ``"dashdot"``.
        shape: ``"linear"``, or ``"hv"`` for a value that holds over a step
            (energy per market step).
        kind: ``"lines"``, ``"markers"``, ``"lines+markers"`` or ``"bar"``.
        width: Line width in pixels.
        opacity: 1 is solid; lower draws it faint.
        right: On the right axis (a second unit, e.g. price next to kWh).
        band: ``(low, high)``: a shaded band behind the line (e.g. mean ± σ).
        group: Lines of one group share one legend entry and show or hide
            together.
        legend: Whether the line has its own legend entry.
        options: Anything else for Plotly's trace (e.g. ``hovertemplate``).
    """

    name: str
    y: Sequence[Any]
    x: Optional[Sequence[Any]] = None
    color: Optional[str] = None
    dash: str = "solid"
    shape: str = "linear"
    kind: str = "lines"
    width: float = 2
    opacity: float = 1.0
    right: bool = False
    band: Optional[tuple[Sequence[float], Sequence[float]]] = None
    group: Optional[str] = None
    legend: bool = True
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Level:
    """A horizontal reference line across the figure (a tariff, a limit, zero, a
    baseline).

    Attributes:
        y: Where.
        label: Text at its left end; empty: none.
        color: Default: muted grey.
        dash: ``"dash"``, ``"dot"`` or ``"solid"``.
        width: Line width in pixels.
    """

    y: float
    label: str = ""
    color: str = MUTED
    dash: str = "dash"
    width: float = 1


def add_series(
    fig: go.Figure,
    x: Optional[Sequence[Any]],
    lines: Sequence[Line],
    row: Optional[int] = None,
    col: Optional[int] = None,
) -> go.Figure:
    """Draw ``lines`` into ``fig`` (into one panel with ``row`` and ``col``, for a
    figure made with ``make_subplots``; a line on the right then needs the panel's
    ``secondary_y`` in its specs)."""
    colors = palette([line.name for line in lines])

    for line in lines:
        xs = list(line.x if line.x is not None else x)
        color = line.color or colors[line.name]
        group = line.group or line.name
        place: dict[str, Any] = {}

        if row is not None:
            place = dict(row=row, col=col or 1)
            if line.right:
                place["secondary_y"] = True
        elif line.right:
            place = dict(yaxis="y2")

        if line.band is not None:
            low, high = line.band
            fig.add_scatter(
                x=xs + xs[::-1],
                y=list(high) + list(low)[::-1],
                fill="toself",
                fillcolor=rgba(color, 0.12),
                line=dict(width=0),
                legendgroup=group,
                showlegend=False,
                hoverinfo="skip",
                **place,
            )

        common = dict(
            x=xs,
            y=list(line.y),
            name=line.name,
            legendgroup=group,
            showlegend=line.legend,
            opacity=line.opacity,
        )

        if line.kind == "bar":
            fig.add_bar(marker_color=color, **common, **place, **line.options)
        else:
            fig.add_scatter(
                mode=line.kind,
                line=dict(
                    color=color, dash=line.dash, shape=line.shape, width=line.width
                ),
                marker=dict(color=color),
                **common,
                **place,
                **line.options,
            )

    return fig


def add_levels(
    fig: go.Figure,
    levels: Sequence[Level],
    row: Optional[int] = None,
    col: Optional[int] = None,
) -> go.Figure:
    """Draw ``levels`` across ``fig`` (or across one panel)."""
    place = {} if row is None else dict(row=row, col=col or 1)

    for level in levels:
        label = (
            dict(annotation_text=level.label, annotation_position="top left")
            if level.label
            else {}
        )
        fig.add_hline(
            y=level.y,
            line=dict(color=level.color, dash=level.dash, width=level.width),
            **label,
            **place,
        )

    return fig


def series_figure(
    x: Optional[Sequence[Any]],
    lines: Sequence[Line],
    levels: Sequence[Level] = (),
    *,
    y_title: str = "",
    x_title: str = "",
    right_title: str = "",
    stacked: bool = False,
    height: int = 300,
) -> go.Figure:
    """The general series figure: ``lines`` along ``x`` (a line with its own x
    uses that), ``levels`` across, in the Studio's look.

    Args:
        x: The shared x values (time labels, steps, environment steps); ``None``
            when every line has its own.
        lines: What to draw, in legend order.
        levels: Reference lines.
        y_title: The left axis' title.
        x_title: The x axis' title.
        right_title: The right axis' title, for lines with ``right``.
        stacked: Bars stacked instead of side by side.
        height: Height in pixels.
    """
    fig = go.Figure()
    add_series(fig, x, lines)
    add_levels(fig, levels)
    styled(fig, height, y_title, x_title)

    if any(line.right for line in lines):
        fig.update_layout(
            yaxis2=dict(title=right_title, overlaying="y", side="right", showgrid=False)
        )

    if stacked:
        fig.update_layout(barmode="stack")

    return fig


def line_figure(
    series: Series, height: int = 300, dashed: tuple[str, ...] = (), kind: str = "line"
) -> go.Figure:
    """A ``Series``: one line (or bar group) per named y list.

    Args:
        series: The data.
        height: Height in pixels.
        dashed: Names drawn dashed, e.g. reference lines.
        kind: ``"line"`` or ``"bar"``.
    """
    lines = [
        Line(
            name,
            values,
            kind="bar" if kind == "bar" else "lines",
            dash="dash" if name in dashed else "solid",
        )
        for name, values in series.y.items()
    ]

    return series_figure(
        series.x,
        lines,
        y_title=series.y_label,
        x_title=series.x_label,
        height=height,
    )


# --------------------------------------------------------------------------------------
# A day of profiles
# --------------------------------------------------------------------------------------
DAY_NAMES = {"load": "Demand", "sgen": "Generation", "storage": "Storage"}


def clock(labels: Sequence[str]) -> list[str]:
    """The time of day of each step label (``"2016-06-15 13:00"`` -> ``"13:00"``)."""
    return [label[-5:] for label in labels]


def day_figure(
    day: DayProfiles,
    elements: list[DayElement],
    height: int = 280,
    faint: bool = False,
) -> go.Figure:
    """Demand, generation and storage of ``elements``, each summed per step.

    Args:
        day: The day's profiles (time axis and step length).
        elements: The elements to sum, e.g. all participants'.
        height: Height in pixels.
        faint: Draw dashed and light, for elements that are switched off.
    """
    lines = []

    for kind, name in DAY_NAMES.items():
        group = [e for e in elements if e.element_type == kind]

        if group:
            lines.append(
                Line(
                    f"{name} ({len(group)})",
                    day.total_kw(group),
                    color=ENERGY[kind],
                    shape="hv",
                    dash="dash" if faint else "solid",
                    opacity=0.55 if faint else 1.0,
                )
            )

    return series_figure(clock(day.x), lines, y_title="kW", height=height)


def element_figure(
    day: DayProfiles,
    lines: dict[str, list[float]],
    height: int = 280,
    y_title: str = "kW",
) -> go.Figure:
    """One line per name over the day (colours from the series palette)."""
    drawn = [Line(name, kw, shape="hv") for name, kw in lines.items()]

    return series_figure(clock(day.x), drawn, y_title=y_title, height=height)


# --------------------------------------------------------------------------------------
# Network: the topology, and what is drawn on it
# --------------------------------------------------------------------------------------
def _bus_color(kind: str) -> str:
    """Marker colour for a bus kind; combined kinds fall back to their main element."""
    if kind in BUS:
        return BUS[kind]

    if "storage" in kind:
        return BUS["storage"]

    return BUS["load+pv"] if "pv" in kind else BUS["load"]


def _branch_trace(fig: go.Figure, pos: dict, branches: list, **line) -> None:
    """Draw branches as one line trace (``None`` breaks the line between segments)."""
    xs, ys = [], []

    for br in branches:
        if br.from_bus in pos and br.to_bus in pos:
            (x0, y0), (x1, y1) = pos[br.from_bus], pos[br.to_bus]
            xs += [x0, x1, None]
            ys += [y0, y1, None]

    if xs:
        fig.add_scatter(
            x=xs, y=ys, mode="lines", line=line, hoverinfo="skip", showlegend=False
        )


def topology_figure(
    topology: TopologyView,
    voltages: dict[str, float] | None = None,
    highlight: set[str] | None = None,
    height: int = 420,
    violating: set[str] | None = None,
) -> go.Figure:
    """Network plot. Buses carry their ID as ``customdata`` for click handlers.

    Args:
        topology: Buses and branches.
        voltages: Voltage per bus; colours the buses on a fixed 0.93 to 1.05 pu scale.
        highlight: Buses outlined in amber (selected bus, participants).
        height: Height in pixels.
        violating: Buses outlined in red (outside their voltage limits).
    """
    pos = {b.id: (b.x, b.y) for b in topology.buses}
    fig = go.Figure()
    lines = [br for br in topology.branches if br.kind == "line"]
    # Lines first (dotted when open), then transformers and switches drawn thick.
    _branch_trace(
        fig,
        pos,
        [br for br in lines if br.closed],
        color="rgba(100,116,139,0.6)",
        width=1.5,
    )
    _branch_trace(
        fig,
        pos,
        [br for br in lines if not br.closed],
        color="rgba(100,116,139,0.45)",
        width=1,
        dash="dot",
    )
    _branch_trace(
        fig,
        pos,
        [br for br in topology.branches if br.kind in ("trafo", "switch")],
        color="#0F172A",
        width=3,
    )

    def hover(b: BusView) -> str:
        """Hover text: bus ID, kind, voltage level and, after a preview, the voltage."""
        text = f"{b.id}<br>{b.kind} · {b.vn_kv} kV"

        if voltages and b.id in voltages:
            text += f"<br>{voltages[b.id]:.3f} pu"

        return text

    def size(b: BusView) -> int:
        """Marker size: external grid large, buses with elements medium, empty buses
        small.
        """
        return 16 if b.kind == "external_grid" else (9 if b.kind != "bus" else 6)

    def outline(group: list[BusView]) -> dict:
        """Amber outline for highlighted buses (selected bus, participants), red for
        buses outside their voltage limits."""
        bad = [bool(violating) and b.id in violating for b in group]
        marked = [bool(highlight) and b.id in highlight for b in group]

        return dict(
            width=[3 if m or v else 0.5 for m, v in zip(marked, bad)],
            color=[LIMIT if v else HIGHLIGHT for v in bad],
        )

    # After a preview: one trace coloured by voltage. Otherwise one trace per bus kind,
    # so the legend explains the colours.
    if voltages:
        group = topology.buses
        fig.add_scatter(
            x=[b.x for b in group],
            y=[b.y for b in group],
            mode="markers",
            customdata=[b.id for b in group],
            text=[hover(b) for b in group],
            hoverinfo="text",
            showlegend=False,
            marker=dict(
                size=[size(b) for b in group],
                color=[voltages.get(b.id, 1.0) for b in group],
                colorscale="RdYlGn",
                cmin=0.93,
                cmax=1.05,
                colorbar=dict(title="V (pu)", thickness=12),
                line=outline(group),
            ),
        )
    else:
        kinds = sorted(
            {b.kind for b in topology.buses}, key=lambda k: k != "external_grid"
        )
        for kind in kinds:
            group = [b for b in topology.buses if b.kind == kind]
            fig.add_scatter(
                x=[b.x for b in group],
                y=[b.y for b in group],
                mode="markers",
                name=kind.replace("_", " "),
                customdata=[b.id for b in group],
                text=[hover(b) for b in group],
                hoverinfo="text",
                marker=dict(
                    size=[size(b) for b in group],
                    color=_bus_color(kind),
                    line=outline(group),
                ),
            )

    fig = styled(fig, height)
    fig.update_layout(hovermode="closest", legend=dict(orientation="h", y=-0.02))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x")

    return fig


@dataclass
class Link:
    """A line between two buses (a trade, later perhaps a loaded line).

    Attributes:
        a: One bus.
        b: The other bus.
        amount: Sets the width, relative to the largest of its group.
        text: Hover text.
    """

    a: str
    b: str
    amount: float = 1.0
    text: str = ""


@dataclass
class Ring:
    """A ring around a bus (an order, a participant).

    Attributes:
        bus: Where.
        text: Hover text.
    """

    bus: str
    text: str = ""


def add_links(
    fig: go.Figure,
    topology: TopologyView,
    links: Sequence[Link],
    color: str,
    name: str,
    dash: str = "solid",
) -> go.Figure:
    """Draw ``links`` on a topology figure as one legend group, wider for a larger
    amount; links to a bus the topology lacks are left out."""
    pos = {b.id: (b.x, b.y) for b in topology.buses}
    drawn = [link for link in links if link.a in pos and link.b in pos]
    biggest = max((link.amount for link in drawn), default=0.0) or 1.0

    for n, link in enumerate(drawn):
        (x0, y0), (x1, y1) = pos[link.a], pos[link.b]
        fig.add_scatter(
            x=[x0, x1],
            y=[y0, y1],
            mode="lines",
            line=dict(color=color, width=1.5 + 5 * link.amount / biggest, dash=dash),
            opacity=0.8,
            name=name,
            legendgroup=name,
            showlegend=n == 0,
            hoverinfo="text",
            text=link.text,
        )

    return fig


def add_rings(
    fig: go.Figure,
    topology: TopologyView,
    rings: Sequence[Ring],
    color: str,
    name: str,
    size: int = 20,
) -> go.Figure:
    """Draw ``rings`` on a topology figure as one legend entry; rings on a bus the
    topology lacks are left out."""
    pos = {b.id: (b.x, b.y) for b in topology.buses}
    drawn = [ring for ring in rings if ring.bus in pos]

    if drawn:
        fig.add_scatter(
            x=[pos[r.bus][0] for r in drawn],
            y=[pos[r.bus][1] for r in drawn],
            mode="markers",
            name=name,
            hoverinfo="text",
            text=[r.text for r in drawn],
            marker=dict(
                size=size, symbol="circle-open", color=color, line=dict(width=3)
            ),
        )

    return fig
