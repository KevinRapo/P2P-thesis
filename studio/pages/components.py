"""Components: every base building block of the Studio, drawn with made-up values.

A reference for writing pages: each card runs one small demo function and shows
that function's own code under it, so what is shown is what runs. The Style lab
tries a line's look live. Nothing here reads the scenario, a network or a run;
the values are invented. The blocks that need the services (network picker,
profile inspector, run table) are listed with the pages that show them live.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import time
from typing import Callable

from nicegui import ui

from core.grid.contract import BranchView, BusView, TopologyView
from core.market.order import Trade
from studio.adapters.models import DayElement, DayProfiles, Series
from studio.components.cards import (
    busy,
    failed,
    fill,
    key_values,
    not_implemented,
    placeholder,
    section,
    stat,
    stat_grid,
)
from studio.components.charts import (
    Chart,
    DayChart,
    ElementsChart,
    NetworkChart,
    SeriesChart,
    SeriesModelChart,
    clock,
)
from studio.components.labels import BACKGROUNDS, MECHANISMS, STEP_LENGTHS
from studio.components.tables import data_table, trades_table
from studio.layout import shell
from studio.theme import BUS, ENERGY, HIGHLIGHT, LIMIT, MARKET, MUTED, PALETTE, SERIES

# --------------------------------------------------------------------------------------
# Made-up data: a day of four elements, a six-bus network, three trades, three rows
# --------------------------------------------------------------------------------------
LABELS = [f"2016-06-15 {h:02d}:00" for h in range(24)]
HOURS = clock(LABELS)
SUN = [max(0.0, 4.0 * (1 - abs(h - 13) / 6)) for h in range(24)]
DEMAND = [0.6 + (1.2 if 17 <= h <= 21 else 0.0) for h in range(24)]
MORNING = [0.8 + (0.6 if 7 <= h <= 9 else 0.0) for h in range(24)]

DAY = DayProfiles(
    x=LABELS,
    step_hours=1.0,
    elements=[
        DayElement(id="load 1", element_type="load", bus="B2", owner="P1", kw=DEMAND),
        DayElement(id="load 2", element_type="load", bus="B4", owner="P2", kw=MORNING),
        DayElement(id="pv 1", element_type="sgen", bus="B3", owner="P1", kw=SUN),
        DayElement(id="load 3", element_type="load", bus="B5", kw=[1.0] * 24),
    ],
)

TOPOLOGY = TopologyView(
    buses=(
        BusView("B0", 0.0, 0.0, "external_grid", 20.0),
        BusView("B1", 0.0, -1.0, "bus", 0.4),
        BusView("B2", -1.0, -2.0, "load", 0.4),
        BusView("B3", 0.0, -2.0, "pv", 0.4),
        BusView("B4", 1.0, -2.0, "load+pv", 0.4),
        BusView("B5", 0.0, -3.0, "storage", 0.4),
    ),
    branches=(
        BranchView("trafo", "B0", "B1", "trafo"),
        BranchView("line 1", "B1", "B2", "line"),
        BranchView("line 2", "B1", "B3", "line"),
        BranchView("line 3", "B1", "B4", "line"),
        BranchView("line 4", "B3", "B5", "line"),
        BranchView("switch", "B2", "B5", "switch", closed=False),
    ),
    external_grid_bus="B0",
)
VOLTAGES = {"B0": 1.0, "B1": 1.0, "B2": 0.97, "B3": 1.02, "B4": 0.99, "B5": 0.92}

TRADES = [
    Trade("P2", "P1", price=0.12, quantity=1.5, timestamp=0, distance=0.3, stage=1),
    Trade("P3", "P1", price=0.11, quantity=0.8, timestamp=0, distance=0.5, stage=2),
    Trade("P3", "DSO", price=0.25, quantity=0.4, timestamp=0, distance=0.9, stage=3),
]

ROWS = [
    {"id": "P1", "bus": "B2", "battery": "10 kWh", "state": "done", "c": "positive"},
    {"id": "P2", "bus": "B4", "battery": "—", "state": "running", "c": "info"},
    {"id": "P3", "bus": "B5", "battery": "5 kWh", "state": "failed", "c": "negative"},
]


# --------------------------------------------------------------------------------------
# A demo card: the function's docstring as title and caption, its output, its code
# --------------------------------------------------------------------------------------
def _code(fn: Callable) -> str:
    """The body of ``fn`` without its docstring, as written."""
    source = textwrap.dedent(inspect.getsource(fn))
    body = ast.parse(source).body[0].body
    has_doc = isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
    first = body[1 if has_doc and len(body) > 1 else 0].lineno
    lines = source.splitlines()[first - 1 :]

    return textwrap.dedent("\n".join(lines)).strip()


def cards(*demos: Callable) -> None:
    """One card per demo function: title and caption from its docstring (first
    line, then the rest), what it builds, then its code."""
    for fn in demos:
        title, _, caption = (fn.__doc__ or fn.__name__).strip().partition("\n")

        with section(title, " ".join(caption.split()), "widgets"):
            fn()
            ui.code(_code(fn), language="python").classes("w-full")


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """One tab per kind of component, and the Style lab."""
    tabs_ = {
        "layout": ("Layout", "dashboard", _layout),
        "text": ("Text and tiles", "text_fields", _text),
        "colours": ("Colours", "palette", _colours),
        "states": ("States", "hourglass_empty", _states),
        "tables": ("Tables", "table_chart", _tables),
        "series": ("Series charts", "show_chart", _series),
        "network": ("Network charts", "hub", _network),
        "lab": ("Style lab", "science", _lab),
    }

    with shell(
        "components",
        "Components",
        "The Studio's base building blocks with made-up values, each with the code "
        "that draws it. Imports: studio/components/.",
    ):
        # Tab bar: one tab per kind of component
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            for name, (label, icon, _) in tabs_.items():
                ui.tab(name, label=label, icon=icon)

        # keep_alive=False: a hidden tab is drawn again when opened, so its Plotly
        # charts get the right width
        with ui.tab_panels(tabs, value="layout", keep_alive=False).classes(
            "w-full bg-transparent"
        ):
            for name, (_, _, build) in tabs_.items():
                with ui.tab_panel(name).classes("p-0 gap-4"):
                    build()


# --------------------------------------------------------------------------------------
# Layout: cards, rows, the empty box, tabs, expansion and dialog, buttons
# --------------------------------------------------------------------------------------
def card_demo() -> None:
    """section: the card
    Every card on every page; title, caption and icon are optional."""
    with section("Title", "A caption under the title", "hub"):
        ui.label("Anything built here goes inside the card.")


def row_demo() -> None:
    """Cards side by side: ui.row
    A row puts its children next to each other; a column (the default inside a
    card) stacks them. A fixed share instead: classes="basis-1/3" on one card."""
    with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
        with section("Left", icon="west", classes="grow basis-0"):
            ui.label("grow basis-0: equal widths")
        with section("Right", icon="east", classes="grow basis-0"):
            ui.label("items-stretch: equal heights")


def box_demo() -> None:
    """An empty box, filled later
    The pattern of every page: the layout builds empty boxes, a function fills them
    once the data is there."""
    box = ui.column().classes("w-full")

    def draw() -> None:
        box.clear()

        with box:
            ui.label(f"Drawn into the box at {time.strftime('%H:%M:%S')}")

    ui.button("Fill the box", on_click=draw).props("outline no-caps")


def tabs_demo() -> None:
    """Tabs
    The tab bar and the panels are two elements, joined by the tab names."""
    with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
        ui.tab("a", label="First", icon="looks_one")
        ui.tab("b", label="Second", icon="looks_two")

    with ui.tab_panels(tabs, value="a").classes("w-full bg-transparent"):
        with ui.tab_panel("a"):
            ui.label("First tab")
        with ui.tab_panel("b"):
            ui.label("Second tab")


def expansion_demo() -> None:
    """Expansion and dialog
    Something hidden until opened, and a pop-up window."""
    with ui.expansion("More settings", icon="tune").classes("w-full"):
        ui.label("Hidden until opened")

    with ui.dialog() as dialog, ui.card().classes("w-[420px] gap-3"):
        ui.label("A pop-up window").classes("text-h6")

        with ui.row().classes("w-full justify-end"):
            ui.button("Close", on_click=dialog.close).props("flat no-caps")

    ui.button("Open the dialog", on_click=dialog.open).props("outline no-caps")


def buttons_demo() -> None:
    """Buttons
    The props the pages use, from the main action to the least."""
    with ui.row().classes("gap-2"):
        ui.button("Unelevated", icon="play_arrow").props("unelevated no-caps")
        ui.button("Outline", icon="refresh").props("outline no-caps")
        ui.button("Flat", icon="close").props("flat no-caps")
        ui.button("Danger", icon="stop_circle").props("outline no-caps color=negative")
        ui.button("Not wired", on_click=lambda: not_implemented("Not wired"))


def _layout() -> None:
    cards(card_demo, row_demo, box_demo, tabs_demo, expansion_demo, buttons_demo)


# --------------------------------------------------------------------------------------
# Text and tiles
# --------------------------------------------------------------------------------------
def text_demo() -> None:
    """Text classes
    mls-* are ours (studio/static/studio.css); the others are Quasar's."""
    for classes in (
        "mls-card-title",
        "mls-card-caption",
        "text-body2",
        "text-body2 text-weight-medium",
        "text-h6",
        "mls-mono",
        "text-warning text-caption",
        "text-negative text-body2",
    ):
        ui.label(classes).classes(classes)


def key_values_demo() -> None:
    """key_values
    Label and value pairs: the Summary page's settings cards."""
    key_values(
        {"Network": "1-LV-rural1--0-sw", "Participants": 13, "Day": "2016-06-15"}
    )


def stat_demo() -> None:
    """stat and stat_grid
    Number tiles in a grid that wraps (the Day profiles tab)."""
    with stat_grid():
        stat("Participants", "13", "21 elements taken over", "groups")
        stat("Demand", "184 kWh", "over the day", "bolt", "info")
        stat("Generation", "96 kWh", icon="solar_power", tone="warning")


def labels_demo() -> None:
    """labels: display names of choices
    One place for the words, shared by the page that sets a choice and the page
    that shows it."""
    ui.select(STEP_LENGTHS, value=1.0, label="Market step").classes("w-72")
    key_values(
        {
            "MECHANISMS": ", ".join(MECHANISMS.values()),
            "BACKGROUNDS": ", ".join(BACKGROUNDS.values()),
        }
    )


def _text() -> None:
    cards(text_demo, key_values_demo, stat_demo, labels_demo)


# --------------------------------------------------------------------------------------
# Colours (studio/theme.py)
# --------------------------------------------------------------------------------------
def _swatches(colors: dict[str, str]) -> None:
    """One chip per colour: a square of it, its name and its code."""
    with ui.row().classes("gap-3"):
        for name, color in colors.items():
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.element("div").style(
                    f"background: {color}; width: 28px; height: 28px; "
                    "border-radius: 6px"
                )

                with ui.column().classes("gap-0"):
                    ui.label(name).classes("text-body2")
                    ui.label(color).classes("mls-mono mls-card-caption")


def series_colours_demo() -> None:
    """SERIES: the categorical palette
    Runs, paradigms, agents: anything without a colour of its own. A chart's line
    without a colour takes the next one."""
    _swatches({f"SERIES[{i}]": c for i, c in enumerate(SERIES)})


def meaning_colours_demo() -> None:
    """Colours with a meaning
    The same thing has the same colour on every page; change it in theme.py and it
    changes everywhere."""
    signals = {"MUTED": MUTED, "LIMIT": LIMIT, "HIGHLIGHT": HIGHLIGHT}

    for name, colors in (
        ("MUTED, LIMIT, HIGHLIGHT", signals),
        ("ENERGY: element types of a day", ENERGY),
        ("MARKET: sides and counterparts", MARKET),
        ("BUS: bus kinds of the network plot", BUS),
    ):
        ui.label(name).classes("mls-card-caption")
        _swatches(colors)


def quasar_colours_demo() -> None:
    """PALETTE: Quasar's named colours
    Set by apply_theme(); the names work in props (color=...) and classes
    (text-..., bg-...)."""
    _swatches(PALETTE)


def _colours() -> None:
    cards(series_colours_demo, meaning_colours_demo, quasar_colours_demo)


# --------------------------------------------------------------------------------------
# States: nothing yet, loading, failed, filled
# --------------------------------------------------------------------------------------
def placeholder_demo() -> None:
    """placeholder
    Where content will appear once there is something to show."""
    placeholder("Tick runs in the table to compare them.", "checklist")


def busy_failed_demo() -> None:
    """busy and failed
    Both replace a box's content; fill (below) uses them."""
    box = ui.column().classes("w-full")
    busy(box, "Building topology …")

    with ui.row().classes("gap-2"):
        ui.button("busy", on_click=lambda: busy(box, "Building topology …"))
        ui.button("failed", on_click=lambda: failed(box, ValueError("not found")))


def fill_demo() -> None:
    """fill: read in the background, then draw
    The usual way a page shows data: spinner, read in a thread, then the drawing or
    the error. Here the read waits a second."""
    box = ui.column().classes("w-full")

    def read(fails: bool) -> DayProfiles:
        time.sleep(1.0)

        if fails:
            raise ValueError("the read failed")

        return DAY

    def draw(day: DayProfiles) -> None:
        DayChart(day=day, elements=day.owned()).show()

    with ui.row().classes("gap-2"):
        ui.button("fill", on_click=lambda: fill(box, lambda: read(False), draw))
        ui.button(
            "fill, and the read fails",
            on_click=lambda: fill(box, lambda: read(True), draw),
        )


def _states() -> None:
    cards(placeholder_demo, busy_failed_demo, fill_demo)


# --------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------
def table_demo() -> None:
    """data_table
    The standard table: sortable columns, (field, header) pairs, rows per page."""
    data_table(ROWS, [("id", "Participant"), ("bus", "Bus"), ("battery", "Battery")])


def badge_demo() -> None:
    """data_table with a badge column
    A value as a coloured chip; the colour comes from another field of the row."""
    data_table(ROWS, [("id", "Run"), ("state", "State")], badge_columns={"state": "c"})


def selection_demo() -> None:
    """data_table with single selection
    The Grid page's participant table opens the battery editor this way."""
    table = data_table(ROWS, [("id", "Participant"), ("bus", "Bus")])
    table.props("selection=single")
    table.on_select(lambda e: ui.notify([r["id"] for r in e.selection]))


def trades_demo() -> None:
    """trades_table
    A market step's trades, with fees=True their distance, fee and who pays it."""
    trades_table(TRADES, fees=True)


def _tables() -> None:
    cards(table_demo, badge_demo, selection_demo, trades_demo)


# --------------------------------------------------------------------------------------
# Series charts: a chart class says what to draw; show() places it
# --------------------------------------------------------------------------------------
def chart_demo() -> None:
    """A SeriesChart of your own
    A page's chart is a small class: draw() reads the options in self.o and calls
    line, bars and level. show() places it."""

    class SunChart(SeriesChart):
        y_title = "kW"

        def draw(self) -> None:
            self.line(HOURS, self.o.demand, "Demand")
            self.line(HOURS, self.o.sun, "PV", shape="hv")
            self.level(2.5, "A limit", color=LIMIT)

    SunChart(demand=DEMAND, sun=SUN).show()


def controls_demo() -> None:
    """Controls that change a chart
    chart.switch, chart.select and chart.slider each change one option, and the
    chart redraws itself: a page writes no redraw code."""

    class ScaledChart(SeriesChart):
        y_title = "kW"

        def draw(self) -> None:
            y = [v * self.o.scale for v in SUN]
            self.line(HOURS, y, "PV", shape=self.o.shape, markers=self.o.markers)

    chart = ScaledChart(scale=1.0, shape="hv", markers=False).show()

    with ui.row().classes("w-full items-center gap-4"):
        chart.switch("markers", "Markers")
        chart.select("shape", ["linear", "hv"], "Shape").classes("w-32")

        with ui.column().classes("grow"):
            chart.slider("scale", 0.5, 3.0, 0.5, "Scale")


def looks_demo() -> None:
    """line: how a line looks
    Each line is the same values, moved up by one."""
    looks = {
        "solid": {},
        "dash": dict(dash="dash"),
        "hv": dict(shape="hv"),
        "markers": dict(markers=True),
        "faint": dict(width=1, opacity=0.45),
    }

    class LooksChart(SeriesChart):
        height = 320

        def draw(self) -> None:
            for i, (name, look) in enumerate(looks.items()):
                self.line(HOURS, [v + i for v in SUN], name, **look)

    LooksChart().show()


def bars_demo() -> None:
    """bars, stacked, a second unit on the right
    The Market page's day: stacked bars, and a line on its own axis."""

    class TradedChart(SeriesChart):
        y_title, right_title, stacked = "kWh", "price per kWh", True

        def draw(self) -> None:
            p2p = [min(s, d) for s, d in zip(SUN, DEMAND)]
            dso = [max(d - s, 0.0) for s, d in zip(SUN, DEMAND)]
            price = [0.12 if v > 0 else None for v in p2p]
            self.bars(HOURS, p2p, "Peer to peer", color=MARKET["p2p"])
            self.bars(HOURS, dso, "With the DSO", color=MARKET["dso"])
            self.line(HOURS, price, "Price", MARKET["sell"], markers=True, right=True)

    TradedChart().show()


def band_demo() -> None:
    """A band, and panels
    band=(low, high) shades around a line (the RL probes' mean ± σ); panels(...)
    splits the chart into rows on one x axis, and row= picks one."""
    steps = list(range(0, 50_000, 5_000))
    mean = [0.8 * (1 - 0.9**i) for i in range(len(steps))]
    sigma = [0.5 * 0.8**i for i in range(len(steps))]

    class PanelChart(SeriesChart):
        height = 420

        def draw(self) -> None:
            low = [m - s for m, s in zip(mean, sigma)]
            high = [m + s for m, s in zip(mean, sigma)]
            self.panels(["mean ± σ", "σ"])
            self.line(steps, mean, "mean", band=(low, high), row=1)
            self.level(1.0, row=1)
            self.line(steps, sigma, "σ", row=2)

    PanelChart().show()


def day_demo() -> None:
    """DayChart and ElementsChart
    Demand, generation and storage summed per step (DayProfiles from
    s.profiles.day_profiles), and one line per element."""
    DayChart(day=DAY, elements=DAY.owned()).show()
    ElementsChart(day=DAY, lines={e.id: e.kw for e in DAY.owned()}).show()


def series_model_demo() -> None:
    """SeriesModelChart
    A Series (the profile service's) as lines or bars."""
    series = Series(x=list(range(24)), y={"A": DEMAND, "B": SUN}, y_label="kW")
    SeriesModelChart(260, series=series).show()


def other_chart_demo() -> None:
    """Chart: any other figure
    A box plot or a heatmap: draw() adds to self.fig with Plotly's own calls; the
    Studio's look and set() come with Chart."""

    class BoxChart(Chart):
        y_title = "team return"

        def draw(self) -> None:
            for name, values in self.o.returns.items():
                self.fig.add_box(y=values, name=name, boxpoints="all")

    BoxChart(returns={"CTCE": [0.6, 0.5, 0.7], "CTDE": [0.4, 0.3, 0.5]}).show()


def _series() -> None:
    cards(
        chart_demo,
        controls_demo,
        looks_demo,
        bars_demo,
        band_demo,
        day_demo,
        series_model_demo,
        other_chart_demo,
    )


# --------------------------------------------------------------------------------------
# Network charts
# --------------------------------------------------------------------------------------
def network_demo() -> None:
    """NetworkChart
    Buses coloured by kind (BUS in theme.py), highlighted ones ringed in amber; a
    click on a bus calls on_bus with its ID (the Grid page places participants
    so)."""
    NetworkChart(
        320, on_bus=ui.notify, topology=TOPOLOGY, highlight={"B2", "B4"}
    ).show()


def voltages_demo() -> None:
    """NetworkChart with voltages
    After a power flow: buses coloured by voltage, those outside the limits ringed
    in red. The switch sets the voltages option."""
    chart = NetworkChart(320, topology=TOPOLOGY, voltages=VOLTAGES, violating={"B5"})
    chart.show()
    ui.switch(
        "Voltages",
        value=True,
        on_change=lambda e: chart.set(voltages=VOLTAGES if e.value else None),
    )


def overlay_demo() -> None:
    """links and rings: drawing on the network
    A subclass's draw() adds links (a line's width follows its amount) and rings;
    the Market page draws trades and orders so."""
    peer = [("B3", "B2", 1.5, "P1 → P2"), ("B3", "B4", 0.8, "P1 → P3")]

    class TradesChart(NetworkChart):
        def draw(self) -> None:
            self.links(peer, MARKET["p2p"], "Peer trade")
            self.links([("B0", "B4", 0.4, "DSO → P3")], MARKET["dso"], "DSO", "dash")
            self.rings([("B3", "P1 sells")], MARKET["sell"], "Seller")
            self.rings([("B2", "P2 buys"), ("B4", "P3 buys")], MARKET["buy"], "Buyer")

    TradesChart(360, topology=TOPOLOGY).show()


def _network() -> None:
    cards(network_demo, voltages_demo, overlay_demo)

    with section(
        "Blocks that need the services",
        "Self-contained: they read through the services themselves, so they are "
        "shown live on their pages",
        "extension",
    ):
        key_values(
            {
                "NetworkPicker (network.py)": "Grid & Participants, Inspect",
                "ElementsTable, ProfileInspector (network.py)": "Inspect",
                "ProfileOverview (profiles.py)": "Inspect → Profiles",
                "show_day_profiles (day_profiles.py)": "Summary → Day profiles",
                "RunTable (run_table.py)": "Results, RL probes",
            }
        )


# --------------------------------------------------------------------------------------
# Style lab: every option of a line as a control
# --------------------------------------------------------------------------------------
class LabChart(SeriesChart):
    """Demand with every look a line can have, PV on the right axis, levels."""

    y_title = "kW"
    right_title = "kW (PV)"

    def draw(self) -> None:
        o = self.o
        self.height = int(o.pixels)
        band = ([v - 0.5 for v in DEMAND], [v + 0.5 for v in DEMAND])
        look = dict(shape=o.shape, dash=o.dash, width=o.width, opacity=o.opacity)

        if o.bars:
            self.bars(HOURS, DEMAND, "Demand", o.color or None)
        else:
            self.line(
                HOURS,
                DEMAND,
                "Demand",
                o.color or None,
                markers=o.markers,
                band=band if o.band else None,
                **look,
            )

        if o.right:
            self.line(HOURS, SUN, "PV", ENERGY["sgen"], right=True)

        if o.levels:
            self.level(2.5, "A limit", color=LIMIT)
            self.level(0.0)


def _lab() -> None:
    """Controls on the left, the chart and its class on the right."""
    with section(
        "Style lab",
        "Try a look for a line: every control is one of the chart's helpers "
        "(chart.select, chart.switch, chart.slider) changing one option",
        "science",
    ):
        # One row: the controls (left, fixed width) | chart and code (right)
        with ui.row().classes("w-full gap-6 items-start no-wrap"):
            controls = ui.column().classes("w-72 shrink-0 gap-2")

            with ui.column().classes("grow basis-0 min-w-0 gap-2"):
                chart = LabChart(
                    shape="hv",
                    dash="solid",
                    width=2,
                    opacity=1.0,
                    color="",
                    markers=False,
                    band=False,
                    bars=False,
                    right=False,
                    levels=True,
                    pixels=300,
                ).show()
                code = inspect.getsource(LabChart)
                ui.code(code, language="python").classes("w-full")

        with controls:
            colours = {"": "palette (default)"} | {c: f"SERIES · {c}" for c in SERIES}
            chart.select("shape", ["linear", "hv"], "shape").classes("w-full")
            chart.select("dash", ["solid", "dot", "dash", "dashdot"], "dash")
            chart.select("color", colours, "color").classes("w-full")
            chart.slider("width", 0.5, 6, 0.5, "width")
            chart.slider("opacity", 0.1, 1, 0.05, "opacity")
            chart.slider("pixels", 200, 500, 20, "height (pixels)")

            for option, label in (
                ("markers", "markers"),
                ("band", "band (±0.5)"),
                ("bars", "bars instead of a line"),
                ("right", "PV on the right axis"),
                ("levels", "levels (a limit and zero)"),
            ):
                chart.switch(option, label)
