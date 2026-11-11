"""The Studio's charts: one base class, two kinds, and the controls that change them.

    Chart          any Plotly figure on a page: ``draw()`` builds it from the
                   chart's options; ``show()`` places it; ``set(...)`` changes
                   options and redraws it in place
    SeriesChart    values along one axis (time of day, step, environment steps,
                   cumulative kWh): ``line``, ``bars``, ``level`` in ``draw()``
    NetworkChart   the network's topology, coloured by bus kind or voltage, with
                   ``links`` and ``rings`` drawn on it and a callback for bus clicks

A page's chart is a small subclass that only says what to draw (``DayChart``
below; the Results page's ``LearningChart``). A switch, dropdown or slider that
changes a chart comes from the chart itself (``chart.switch("training", ...)``),
so a page writes no redraw code; with ``memory`` set, those controls are remembered
between visits. Every figure gets the Studio's look from ``styled``; the colours with
a meaning are in ``studio/theme.py``.
"""

from __future__ import annotations

from itertools import cycle
from typing import Any, Callable, Optional, Sequence

import plotly.graph_objects as go
from nicegui import ui
from plotly.colors import sample_colorscale
from plotly.subplots import make_subplots

from core.grid.contract import BranchView, BusView, TopologyView
from core.market.clearing import DSO_ID
from studio.components.memory import remember
from studio.theme import BUS, ENERGY, HIGHLIGHT, LIMIT, MARKET, MUTED, SERIES


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
        # Under the x axis title at any legend size: anchored to the figure's bottom,
        # the plot area shrinks to make room for it
        legend=dict(orientation="h", yref="container", y=0, yanchor="bottom", x=0),
        hovermode="x unified",
        # The series' whole name in the hover label: Plotly cuts it at 15 characters,
        # which leaves a run's name as "results_form..."
        hoverlabel=dict(namelength=-1),
    )
    fig.update_xaxes(gridcolor="rgba(148,163,184,0.18)", zeroline=False)
    fig.update_yaxes(gridcolor="rgba(148,163,184,0.18)", zeroline=False)

    if x_title:
        fig.update_xaxes(title=x_title)

    if y_title:
        fig.update_yaxes(title=y_title)

    return fig


def rgba(color: str, alpha: float) -> str:
    """A ``#rrggbb`` colour with transparency (for bands and fills)."""
    r, g, b = (int(color[i : i + 2], 16) for i in (1, 3, 5))

    return f"rgba({r},{g},{b},{alpha})"


# --------------------------------------------------------------------------------------
# Chart: options -> figure, redrawn in place, with controls that change an option
# --------------------------------------------------------------------------------------
class Options(dict):
    """A chart's options, also readable as attributes (``self.o.day``)."""

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


class Chart:
    """A Plotly chart on a page. A subclass writes ``draw()``: it adds traces to
    ``self.fig`` (or returns a figure of its own) from the options in ``self.o``.

    Class attributes a subclass may set: ``height``, ``x_title``, ``y_title`` and
    ``layout`` (Plotly layout settings applied after the Studio's look, e.g.
    ``{"hovermode": "closest"}``). A page sets ``memory``, a name for this chart,
    before making its controls, to have them remembered.

    Args:
        height: Overrides the class' height.
        options: Whatever ``draw`` reads, e.g. the data and the switches' values.
    """

    height = 300
    x_title = ""
    y_title = ""
    layout: dict[str, Any] = {}

    def __init__(self, height: Optional[int] = None, **options: Any) -> None:
        self.o = Options(options)
        self.plot: Optional[ui.plotly] = None
        self.memory: Optional[str] = None

        if height is not None:
            self.height = height

    # --- What to draw (a subclass) ----------------------------------------------------
    def draw(self) -> Optional[go.Figure]:
        raise NotImplementedError

    def titles(self, x: Optional[str] = None, y: Optional[str] = None) -> None:
        """Axis titles that depend on the options (call in ``draw``)."""
        self._titles.update({k: v for k, v in (("x", x), ("y", y)) if v is not None})

    def after(self, **layout: Any) -> None:
        """Layout settings that depend on the options (call in ``draw``)."""
        self._after.update(layout)

    def figure(self) -> go.Figure:
        """The figure as the options are now, in the Studio's look."""
        self.fig = go.Figure()
        self._titles = {"x": self.x_title, "y": self.y_title}
        self._after = dict(self.layout)
        self._prepare()
        drawn = self.draw()

        if drawn is not None:
            self.fig = drawn

        styled(self.fig, self.height, self._titles["y"], self._titles["x"])
        self._finish()
        self.fig.update_layout(**self._after)

        return self.fig

    def _prepare(self) -> None:
        """What a kind of chart adds before ``draw`` (a subclass)."""

    def _finish(self) -> None:
        """What a kind of chart adds after the look (a subclass)."""

    # --- On the page ------------------------------------------------------------------
    def show(self) -> Chart:
        """Place the chart where the page is building (full width)."""
        self.plot = ui.plotly(self.figure()).classes("w-full")
        return self

    def set(self, **changes: Any) -> None:
        """Change options and redraw the chart in place."""
        self.o.update(changes)

        if self.plot is not None:
            self.plot.update_figure(self.figure())

    # --- Controls that change one option ----------------------------------------------
    def switch(self, option: str, label: str) -> ui.switch:
        """A switch for a yes/no option."""
        return self._remembered(
            option,
            ui.switch(
                label,
                value=bool(self.o.get(option)),
                on_change=lambda e: self.set(**{option: bool(e.value)}),
            ),
        )

    def select(self, option: str, choices: Any, label: str = "") -> ui.select:
        """A dropdown for an option with a few choices (a list, or value -> name)."""
        return self._remembered(
            option,
            ui.select(
                choices,
                value=self.o.get(option),
                label=label,
                on_change=lambda e: self.set(**{option: e.value}),
            ),
        )

    def slider(
        self, option: str, low: float, high: float, step: float, label: str = ""
    ) -> ui.slider:
        """A slider for a number option, with its label above."""
        if label:
            ui.label(label).classes("mls-card-caption")

        return self._remembered(
            option,
            ui.slider(
                min=low,
                max=high,
                step=step,
                value=self.o.get(option, low),
                on_change=lambda e: self.set(**{option: e.value}),
            ),
        )

    def _remembered(self, option: str, control: Any) -> Any:
        """Bring back a control's value, which sets the option and redraws."""
        if self.memory:
            remember(control, f"{self.memory}_{option}")

        return control


# --------------------------------------------------------------------------------------
# SeriesChart: values along one axis
# --------------------------------------------------------------------------------------
# What the hover shows: every series at the x under the pointer, or only the nearest.
HOVER = {"all": "All series", "one": "One series"}


class SeriesChart(Chart):
    """Values along one axis. In ``draw()``, ``line`` and ``bars`` add a series
    (each takes the next palette colour unless given one), ``level`` a horizontal
    reference line; ``panels`` splits the figure into rows on one x axis.

    Class attributes besides ``Chart``'s: ``right_title`` (the right axis, for
    series with ``right=True``) and ``stacked`` (bars stacked). The option
    ``hover`` (``HOVER``) picks what the hover shows; ``hover_select`` is its
    control. Without it, the class' ``layout`` decides ("x unified" by default).
    """

    right_title = ""
    stacked = False

    def _prepare(self) -> None:
        self._colors = cycle(SERIES)
        self._right = False
        self._panels = False

    def hover_select(self, label: str = "Hover") -> ui.select:
        """A dropdown between every series at the pointer's x and only the nearest
        one: with many lines the unified label lists them all."""
        if self.o.get("hover") not in HOVER:
            closest = self.layout.get("hovermode") == "closest"
            self.o["hover"] = "one" if closest else "all"

        return self.select("hover", HOVER, label)

    def _finish(self) -> None:
        hover = self.o.get("hover")

        if hover in HOVER:  # after the class' own layout, so the choice wins
            self.after(hovermode="closest" if hover == "one" else "x unified")

        if self._right and not self._panels:
            self.fig.update_layout(
                yaxis2=dict(
                    title=self.right_title, overlaying="y", side="right", showgrid=False
                )
            )

        if self.stacked:
            self.fig.update_layout(barmode="stack")

    # --- What draw() calls ------------------------------------------------------------
    def panels(self, titles: Sequence[str], right: Sequence[bool] = ()) -> None:
        """Split the figure into one row per title, on a shared x axis; ``right``
        says which rows have a right axis."""
        rows = len(titles)
        self._panels = True
        self.fig = make_subplots(
            rows=rows,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            subplot_titles=list(titles),
            specs=[[{"secondary_y": i < len(right) and right[i]}] for i in range(rows)],
        )

    def line(
        self,
        x: Sequence[Any],
        y: Sequence[Any],
        name: str,
        color: Optional[str] = None,
        dash: str = "solid",
        shape: str = "linear",
        markers: bool = False,
        width: float = 2,
        opacity: float = 1.0,
        band: Optional[tuple[Sequence[float], Sequence[float]]] = None,
        group: Optional[str] = None,
        legend: bool = True,
        right: bool = False,
        row: Optional[int] = None,
        **trace: Any,
    ) -> None:
        """A line. ``shape="hv"`` holds each value over its step (energy per market
        step); ``band=(low, high)`` shades a band behind it; ``group`` gives lines
        one legend entry; ``right`` puts it on the right axis; ``row`` in a panel;
        ``trace`` passes anything else to Plotly (e.g. ``hovertemplate``)."""
        color = color or next(self._colors)
        x = list(x)
        place = self._place(right, row)
        group = group or name

        if band is not None:
            low, high = band
            self.fig.add_scatter(
                x=x + x[::-1],
                y=list(high) + list(low)[::-1],
                fill="toself",
                fillcolor=rgba(color, 0.12),
                line=dict(width=0),
                legendgroup=group,
                showlegend=False,
                hoverinfo="skip",
                **place,
            )

        self.fig.add_scatter(
            x=x,
            y=list(y),
            name=name,
            mode="lines+markers" if markers else "lines",
            line=dict(color=color, dash=dash, shape=shape, width=width),
            opacity=opacity,
            legendgroup=group,
            showlegend=legend,
            **place,
            **trace,
        )

    def bars(
        self,
        x: Sequence[Any],
        y: Sequence[Any],
        name: str,
        color: Optional[str] = None,
        right: bool = False,
        row: Optional[int] = None,
        **trace: Any,
    ) -> None:
        """Bars (side by side, or stacked with the class' ``stacked``)."""
        self.fig.add_bar(
            x=list(x),
            y=list(y),
            name=name,
            marker_color=color or next(self._colors),
            **self._place(right, row),
            **trace,
        )

    def level(
        self,
        y: float,
        label: str = "",
        color: str = MUTED,
        dash: str = "dash",
        width: float = 1,
        row: Optional[int] = None,
    ) -> None:
        """A horizontal reference line (a tariff, a limit, zero, a baseline)."""
        text = dict(annotation_text=label, annotation_position="top left")
        self.fig.add_hline(
            y=y,
            line=dict(color=color, dash=dash, width=width),
            **(text if label else {}),
            **({} if row is None else dict(row=row, col=1)),
        )

    def _place(self, right: bool, row: Optional[int]) -> dict[str, Any]:
        """Where a trace goes: a panel's row (and its right axis), or the right axis
        of a figure without panels."""
        if row is not None:
            return (
                dict(row=row, col=1, secondary_y=True)
                if right
                else dict(row=row, col=1)
            )

        if right:
            self._right = True
            return dict(yaxis="y2")

        return {}


# --------------------------------------------------------------------------------------
# Series charts used on more than one page
# --------------------------------------------------------------------------------------
DAY_NAMES = {"load": "Demand", "sgen": "Generation", "storage": "Storage"}


def clock(labels: Sequence[str]) -> list[str]:
    """The time of day of each step label (``"2016-06-15 13:00"`` -> ``"13:00"``)."""
    return [label[-5:] for label in labels]


class DayChart(SeriesChart):
    """Demand, generation and storage of some elements, each summed per step.

    Options: ``day`` (``DayProfiles``), ``elements`` (e.g. ``day.owned()``),
    ``faint`` (dashed and light, for elements that are switched off).
    """

    height = 280
    y_title = "kW"

    def draw(self) -> None:
        day, faint = self.o.day, self.o.get("faint", False)

        for kind, name in DAY_NAMES.items():
            group = [e for e in self.o.elements if e.element_type == kind]

            if group:
                self.line(
                    clock(day.x),
                    day.total_kw(group),
                    f"{name} ({len(group)})",
                    color=ENERGY[kind],
                    shape="hv",
                    dash="dash" if faint else "solid",
                    opacity=0.55 if faint else 1.0,
                )


class NetworkPowerChart(SeriesChart):
    """The whole network's demand, generation, storage and net demand over a window
    (``ProfileService.network_power``), and, when a study case is given, its levels
    as dashed horizontal lines in the same colours. Options: ``series``, ``case``
    (name or None), ``levels`` (the case's values by series name)."""

    height = 340

    def draw(self) -> None:
        s, levels = self.o.series, self.o.get("levels") or {}
        self.titles(x=s.x_label, y=s.y_label)
        colors = {DAY_NAMES[k]: c for k, c in ENERGY.items()} | {"Net demand": MUTED}

        for name, values in s.y.items():
            color = colors.get(name.split(" (")[0])
            dash = "dot" if name == "Net demand" else "solid"
            self.line(s.x, values, name, color=color, dash=dash)

            if name in levels:
                self.level(
                    levels[name], f"{self.o.case}: {name}", color=color or MUTED
                )


class ElementsChart(SeriesChart):
    """One line per name over the day. Options: ``day``, ``lines`` (name -> values
    per step), ``y_title`` (default kW)."""

    height = 280

    def draw(self) -> None:
        self.titles(y=self.o.get("y_title", "kW"))

        for name, values in self.o.lines.items():
            self.line(clock(self.o.day.x), values, name, shape="hv")


class SeriesModelChart(SeriesChart):
    """A ``Series`` (the profile service's) as lines or bars. Options: ``series``,
    ``kind`` (``"line"`` or ``"bar"``), ``dashed`` (names drawn dashed)."""

    def draw(self) -> None:
        s = self.o.series
        self.titles(x=s.x_label, y=s.y_label)

        for name, values in s.y.items():
            if self.o.get("kind") == "bar":
                self.bars(s.x, values, name)
            else:
                dash = "dash" if name in self.o.get("dashed", ()) else "solid"
                self.line(s.x, values, name, dash=dash)


class PriceChart(SeriesChart):
    """A price file's series, each price held over its market step. Options:
    ``name`` (the file), ``read`` (name -> ``Series``)."""

    height = 340

    def draw(self) -> None:
        s = self.o.read(self.o.name)
        self.titles(x=s.x_label, y=s.y_label)

        for label, values in s.y.items():
            self.line(s.x, values, label, shape="hv", markers=len(s.x) == 1)


class TradedChart(SeriesChart):
    """A day's energy traded per step, stacked: peer to peer (with its stage-1 part,
    the partner preferences, apart when known) and with the DSO; the peer price on the
    right, no point in a step without peer trades. The Market page's day and the
    Results page's Market tab.

    Options: ``x`` (the steps), ``p2p`` and ``dso`` (kWh per step), ``price``,
    ``stage1`` (kWh per step, part of ``p2p``; or None), ``compared`` (another run's
    ``(x, p2p)``, a dotted line; or None), ``x_title``.
    """

    y_title = "kWh"
    right_title = "price per kWh"
    stacked = True

    def draw(self) -> None:
        o = self.o
        self.titles(x=o.get("x_title"))
        p2p = list(o.p2p)

        if o.get("stage1") is not None:
            stage1 = list(o.stage1)
            auction = [p - s for p, s in zip(p2p, stage1)]
            self.bars(o.x, stage1, "Peer to peer, stage 1", color=MARKET["p2p"])
            self.bars(
                o.x,
                auction,
                "Peer to peer, auction",
                color=rgba(MARKET["p2p"], 0.55),
            )
        else:
            self.bars(o.x, p2p, "Peer to peer", color=MARKET["p2p"])

        self.bars(o.x, o.dso, "With the DSO", color=MARKET["dso"])
        price = [c if p > 0 else None for c, p in zip(o.price, p2p)]
        self.line(o.x, price, "Peer price", MARKET["sell"], markers=True, right=True)

        if o.get("compared") is not None:
            x, other = o.compared
            self.line(x, other, "Peer to peer (compared)", MARKET["p2p"], "dot", "hv")


class VoltageChart(SeriesChart):
    """A day's lowest and highest bus voltage after each step, the limits dashed.

    Options: ``x``, ``highest``, ``lowest`` (pu per step), ``limits`` (the lowest and
    highest allowed voltage; empty: none drawn), ``compared`` (another run's
    ``(x, highest, lowest)``, dotted; or None), ``x_title``.
    """

    y_title = "V (pu)"

    def draw(self) -> None:
        o = self.o
        self.titles(x=o.get("x_title"))
        self.line(o.x, o.highest, "Highest V", color=MARKET["sell"], markers=True)
        self.line(o.x, o.lowest, "Lowest V", color=MARKET["buy"], markers=True)

        if o.get("compared") is not None:
            x, highest, lowest = o.compared
            self.line(x, highest, "Highest V (compared)", MARKET["sell"], "dot")
            self.line(x, lowest, "Lowest V (compared)", MARKET["buy"], "dot")

        for v in o.get("limits", ()):
            self.level(v, color=LIMIT)


# --------------------------------------------------------------------------------------
# NetworkChart: the topology, and what is drawn on it
# --------------------------------------------------------------------------------------
def _bus_color(kind: str) -> str:
    """Marker colour for a bus kind; combined kinds fall back to their main element."""
    if kind in BUS:
        return BUS[kind]

    if "storage" in kind:
        return BUS["storage"]

    return BUS["load+pv"] if "pv" in kind else BUS["load"]


def _bus_size(b: BusView) -> int:
    """External grid large, buses with elements medium, empty buses small."""
    return 16 if b.kind == "external_grid" else (9 if b.kind != "bus" else 6)


class NetworkChart(Chart):
    """The network: branches, then the buses coloured by kind, or by voltage when
    ``voltages`` is given. A subclass's ``draw()`` adds ``links`` and ``rings``
    on top (the base draws nothing more).

    Options: ``topology`` (``TopologyView``); ``voltages`` (bus -> pu, coloured on
    a fixed 0.93 to 1.05 scale); ``loading`` (line -> percent, the closed lines
    coloured on a fixed 0 to 100 % scale); ``highlight`` (buses ringed in amber:
    participants, the selected bus); ``participants`` (bus -> participant, a red
    ring around each, with its legend entry); ``violating`` (buses ringed in red).

    Args:
        on_bus: Called with the bus ID when a bus is clicked.
    """

    height = 420
    layout = {"hovermode": "closest"}

    def __init__(
        self,
        height: Optional[int] = None,
        on_bus: Optional[Callable[[str], Any]] = None,
        **options: Any,
    ) -> None:
        super().__init__(height, **options)
        self.on_bus = on_bus

    def draw(self) -> None:
        """Nothing beyond the network (a subclass adds links and rings)."""

    def _prepare(self) -> None:
        topology: TopologyView = self.o.topology
        self.pos = {b.id: (b.x, b.y) for b in topology.buses}
        self._branches(topology)
        self._buses(topology)
        marked = self.o.get("participants") or {}
        self.rings(list(marked.items()), LIMIT, "Participant", size=18)

    def _finish(self) -> None:
        self.fig.update_xaxes(visible=False)
        self.fig.update_yaxes(visible=False, scaleanchor="x")

    def show(self) -> NetworkChart:
        super().show()

        if self.on_bus is not None:
            self.plot.on("plotly_click", self._clicked)

        return self

    async def _clicked(self, event: Any) -> None:
        """A click on a bus (buses carry their ID as ``customdata``)."""
        points = (event.args or {}).get("points") or [{}]
        bus = points[0].get("customdata")

        if bus:
            result = self.on_bus(bus)

            if hasattr(result, "__await__"):
                await result

    # --- What draw() calls ------------------------------------------------------------
    def links(
        self,
        links: Sequence[tuple[str, str, float, str]],
        color: str,
        name: str,
        dash: str = "solid",
    ) -> None:
        """Lines between two buses, ``(bus a, bus b, amount, hover text)`` each,
        wider for a larger amount, as one legend entry (e.g. trades)."""
        drawn = [k for k in links if k[0] in self.pos and k[1] in self.pos]
        biggest = max((k[2] for k in drawn), default=0.0) or 1.0

        for n, (a, b, amount, text) in enumerate(drawn):
            (x0, y0), (x1, y1) = self.pos[a], self.pos[b]
            self.fig.add_scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(color=color, width=1.5 + 5 * amount / biggest, dash=dash),
                opacity=0.8,
                name=name,
                legendgroup=name,
                showlegend=n == 0,
                hoverinfo="text",
                text=text,
            )

    def rings(
        self, rings: Sequence[tuple[str, str]], color: str, name: str, size: int = 20
    ) -> None:
        """Rings around buses, ``(bus, hover text)`` each, as one legend entry
        (e.g. orders)."""
        drawn = [r for r in rings if r[0] in self.pos]

        if drawn:
            self.fig.add_scatter(
                x=[self.pos[bus][0] for bus, _ in drawn],
                y=[self.pos[bus][1] for bus, _ in drawn],
                mode="markers",
                name=name,
                hoverinfo="text",
                text=[text for _, text in drawn],
                customdata=[bus for bus, _ in drawn],  # a click on a ring is its bus's
                marker=dict(
                    size=size, symbol="circle-open", color=color, line=dict(width=3)
                ),
            )

    def trade_links(
        self,
        trades: Sequence[tuple[str, str, float, float, int]],
        bus_of: dict[str, str],
    ) -> None:
        """The trades as links, ``(seller, buyer, kWh, price, stage)`` each: peer
        trades solid, the DSO's dashed, to the external grid (``bus_of``: participant
        -> bus)."""
        ext = self.o.topology.external_grid_bus

        def bus(agent: str) -> str:
            return ext if agent == DSO_ID else bus_of.get(agent, ext)

        for stages, color, name, dash in (
            ((1, 2), MARKET["p2p"], "Peer trade", "solid"),
            ((3,), MARKET["dso"], "DSO trade", "dash"),
        ):
            links = [
                (
                    bus(seller),
                    bus(buyer),
                    kwh,
                    f"{seller} → {buyer}: {kwh:.2f} kWh at {price:.3f}",
                )
                for seller, buyer, kwh, price, stage in trades
                if stage in stages
            ]
            self.links(links, color, name, dash)

    # --- The network itself -----------------------------------------------------------
    def _branches(self, topology: TopologyView) -> None:
        """Lines (dotted when open, coloured by loading when it is given), then
        transformers and switches drawn thick."""
        lines = [br for br in topology.branches if br.kind == "line"]
        loading = self.o.get("loading")
        closed = [br for br in lines if br.closed]

        if loading is not None:
            self._loaded(closed, loading)
            closed = []

        for branches, look in (
            (closed, dict(color="rgba(100,116,139,0.6)", width=1.5)),
            (
                [br for br in lines if not br.closed],
                dict(color="rgba(100,116,139,0.45)", width=1, dash="dot"),
            ),
            (
                [br for br in topology.branches if br.kind in ("trafo", "switch")],
                dict(color="#0F172A", width=3),
            ),
        ):
            xs, ys = [], []

            for br in branches:
                if br.from_bus in self.pos and br.to_bus in self.pos:
                    (x0, y0), (x1, y1) = self.pos[br.from_bus], self.pos[br.to_bus]
                    xs += [x0, x1, None]  # None breaks the line between segments
                    ys += [y0, y1, None]

            if xs:
                self.fig.add_scatter(
                    x=xs,
                    y=ys,
                    mode="lines",
                    line=look,
                    hoverinfo="skip",
                    showlegend=False,
                )

    def _loaded(self, lines: list[BranchView], loading: dict[str, float]) -> None:
        """Each line in the colour of its loading (grey without a value), and the
        colour bar."""
        scale = "YlOrRd"

        for br in lines:
            if br.from_bus not in self.pos or br.to_bus not in self.pos:
                continue

            percent = loading.get(br.id)
            known = percent is not None and percent == percent
            color = (
                sample_colorscale(scale, [min(max(percent, 0.0), 100.0) / 100.0])[0]
                if known
                else "rgba(100,116,139,0.4)"
            )
            (x0, y0), (x1, y1) = self.pos[br.from_bus], self.pos[br.to_bus]
            self.fig.add_scatter(
                x=[x0, x1],
                y=[y0, y1],
                mode="lines",
                line=dict(color=color, width=3),
                hoverinfo="text",
                text=f"{br.id}: {percent:.0f} %" if known else br.id,
                showlegend=False,
            )

        self.fig.add_scatter(  # carries the colour bar
            x=[None],
            y=[None],
            mode="markers",
            marker=dict(
                color=[0],
                colorscale=scale,
                cmin=0,
                cmax=100,
                showscale=True,
                colorbar=dict(
                    title=dict(text="Line loading %", side="right"),
                    thickness=12,
                    x=1.16,
                ),
            ),
            hoverinfo="skip",
            showlegend=False,
        )

    def _buses(self, topology: TopologyView) -> None:
        """One trace per bus kind (so the legend explains the colours), or after a
        power flow one trace coloured by voltage."""
        voltages = self.o.get("voltages")
        highlight = self.o.get("highlight") or set()
        violating = self.o.get("violating") or set()

        def hover(b: BusView) -> str:
            text = f"{b.id}<br>{b.kind} · {b.vn_kv} kV"
            return text + (
                f"<br>{voltages[b.id]:.3f} pu" if voltages and b.id in voltages else ""
            )

        def outline(group: list[BusView]) -> dict:
            return dict(
                width=[
                    3 if b.id in highlight or b.id in violating else 0.5 for b in group
                ],
                color=[LIMIT if b.id in violating else HIGHLIGHT for b in group],
            )

        if voltages:
            groups = [(None, list(topology.buses))]
        else:
            kinds = sorted(
                {b.kind for b in topology.buses}, key=lambda k: k != "external_grid"
            )
            groups = [(k, [b for b in topology.buses if b.kind == k]) for k in kinds]

        for kind, group in groups:
            marker = dict(size=[_bus_size(b) for b in group], line=outline(group))

            if kind is None:
                marker |= dict(
                    color=[voltages.get(b.id, 1.0) for b in group],
                    colorscale="RdYlGn",
                    cmin=0.93,
                    cmax=1.05,
                    colorbar=dict(title=dict(text="V (pu)", side="right"), thickness=12),
                )
            else:
                marker["color"] = _bus_color(kind)

            self.fig.add_scatter(
                x=[b.x for b in group],
                y=[b.y for b in group],
                mode="markers",
                name=kind.replace("_", " ") if kind else "",
                showlegend=kind is not None,
                customdata=[b.id for b in group],
                text=[hover(b) for b in group],
                hoverinfo="text",
                marker=marker,
            )
