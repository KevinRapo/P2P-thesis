"""Components: every base building block of the Studio, drawn with made-up values.

A reference for writing pages: each card shows one component as it looks, with
the call that made it under it, and the Style lab tries a line's look live.
Nothing here reads the scenario, a network or a run; the values are invented. The
self-contained blocks that need the services (network picker, profile inspector,
run table) are listed with the pages that show them live.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Generator

import plotly.graph_objects as go
from nicegui import ui
from plotly.subplots import make_subplots

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
    Level,
    Line,
    Link,
    Ring,
    add_levels,
    add_links,
    add_rings,
    add_series,
    clock,
    day_figure,
    element_figure,
    line_figure,
    series_figure,
    styled,
    topology_figure,
)
from studio.components.labels import BACKGROUNDS, MECHANISMS, STEP_LENGTHS
from studio.components.tables import data_table, trades_table
from studio.layout import shell
from studio.theme import (
    BUS,
    ENERGY,
    HIGHLIGHT,
    LIMIT,
    MARKET,
    MUTED,
    PALETTE,
    SERIES,
)


# --------------------------------------------------------------------------------------
# Made-up data: a day of four elements, a six-bus network, three trades
# --------------------------------------------------------------------------------------
HOURS = [f"2016-06-15 {h:02d}:00" for h in range(24)]
SUN = [max(0.0, 4.0 * (1 - abs(h - 13) / 6)) for h in range(24)]

DAY = DayProfiles(
    x=HOURS,
    step_hours=1.0,
    elements=[
        DayElement(
            id="load 1",
            element_type="load",
            bus="B2",
            owner="P1",
            kw=[0.6 + (1.2 if 17 <= h <= 21 else 0.0) for h in range(24)],
        ),
        DayElement(
            id="load 2",
            element_type="load",
            bus="B4",
            owner="P2",
            kw=[0.8 + (0.6 if 7 <= h <= 9 else 0.0) for h in range(24)],
        ),
        DayElement(id="pv 1", element_type="sgen", bus="B3", owner="P1", kw=SUN),
        DayElement(
            id="load 3", element_type="load", bus="B5", kw=[1.0] * 24
        ),  # background: no owner
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

TRADES = [
    Trade("P2", "P1", price=0.12, quantity=1.5, timestamp=0, distance=0.3, stage=1),
    Trade("P3", "P1", price=0.11, quantity=0.8, timestamp=0, distance=0.5, stage=2),
    Trade("P3", "DSO", price=0.25, quantity=0.4, timestamp=0, distance=0.9, stage=3),
]


# --------------------------------------------------------------------------------------
# One demo: the component, then the call that made it
# --------------------------------------------------------------------------------------
@contextmanager
def demo(title: str, code: str, caption: str = "") -> Generator[None, None, None]:
    """A card: the component (built in the ``with`` block), then its code."""
    with section(title, caption, "widgets"):
        yield
        ui.code(code.strip(), language="python").classes("w-full")


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """One tab per kind of component, and the Style lab."""
    with shell(
        "components",
        "Components",
        "The Studio's base building blocks with made-up values, each with the call "
        "that draws it. Imports: studio/components/.",
    ):
        # Tab bar: one tab per kind of component
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            ui.tab("layout", label="Layout", icon="dashboard")
            ui.tab("text", label="Text and tiles", icon="text_fields")
            ui.tab("colours", label="Colours", icon="palette")
            ui.tab("states", label="States", icon="hourglass_empty")
            ui.tab("tables", label="Tables", icon="table_chart")
            ui.tab("series", label="Series charts", icon="show_chart")
            ui.tab("network", label="Network charts", icon="hub")
            ui.tab("lab", label="Style lab", icon="science")

        # keep_alive=False: a hidden tab is drawn again when opened, so its Plotly
        # charts get the right width
        with ui.tab_panels(tabs, value="layout", keep_alive=False).classes(
            "w-full bg-transparent"
        ):
            with ui.tab_panel("layout").classes("p-0 gap-4"):
                _layout()

            with ui.tab_panel("text").classes("p-0 gap-4"):
                _text()

            with ui.tab_panel("colours").classes("p-0 gap-4"):
                _colours()

            with ui.tab_panel("states").classes("p-0 gap-4"):
                _states()

            with ui.tab_panel("tables").classes("p-0 gap-4"):
                _tables()

            with ui.tab_panel("series").classes("p-0 gap-4"):
                _series()

            with ui.tab_panel("network").classes("p-0 gap-4"):
                _network()

            with ui.tab_panel("lab").classes("p-0 gap-4"):
                _lab()


# --------------------------------------------------------------------------------------
# Layout: cards, rows, columns, tabs, expansions, dialogs
# --------------------------------------------------------------------------------------
def _layout() -> None:
    with demo(
        "section: the card",
        """
from studio.components.cards import section

with section("Title", "A caption under the title", "hub"):
    ui.label("Anything built here goes inside the card.")
""",
        "Every card on every page; title, caption and icon are optional",
    ):
        with section("Title", "A caption under the title", "hub"):
            ui.label("Anything built here goes inside the card.")

    with demo(
        "Cards side by side: ui.row",
        """
with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
    with section("Left", icon="west", classes="grow basis-0"):
        ui.label("grow basis-0: equal widths")
    with section("Right", icon="east", classes="grow basis-0"):
        ui.label("items-stretch: equal heights")

# A fixed share instead: classes="basis-1/3 min-w-[360px]" on one card and
# classes="grow" on the other (the Grid page)
""",
        "A row puts its children next to each other; a column (the default inside "
        "a card) stacks them",
    ):
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section("Left", icon="west", classes="grow basis-0"):
                ui.label("grow basis-0: equal widths")
            with section("Right", icon="east", classes="grow basis-0"):
                ui.label("items-stretch: equal heights")

    with demo(
        "An empty box, filled later",
        """
box = ui.column().classes("w-full")   # in the layout: empty

def fill() -> None:                   # later, e.g. after a click or a read
    box.clear()
    with box:
        ui.label("Drawn into the box")
""",
        "The pattern of every page: the layout builds empty boxes, a function "
        "fills them once the data is there",
    ):
        box = ui.column().classes("w-full")
        count = {"n": 0}

        def fill() -> None:
            count["n"] += 1
            box.clear()

            with box:
                ui.label(f"Drawn into the box ({count['n']} times)")

        ui.button("Fill the box", on_click=fill).props("outline no-caps")

    with demo(
        "Tabs",
        """
with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
    ui.tab("a", label="First", icon="looks_one")
    ui.tab("b", label="Second", icon="looks_two")

with ui.tab_panels(tabs, value="a").classes("w-full bg-transparent"):
    with ui.tab_panel("a"):
        ui.label("First tab")
    with ui.tab_panel("b"):
        ui.label("Second tab")
""",
        "The tab bar and the panels are two elements, joined by the tab names",
    ):
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            ui.tab("a", label="First", icon="looks_one")
            ui.tab("b", label="Second", icon="looks_two")

        with ui.tab_panels(tabs, value="a").classes("w-full bg-transparent"):
            with ui.tab_panel("a"):
                ui.label("First tab")
            with ui.tab_panel("b"):
                ui.label("Second tab")

    with demo(
        "Expansion and dialog",
        """
with ui.expansion("More settings", icon="tune").classes("w-full"):
    ui.label("Hidden until opened")

with ui.dialog() as dialog, ui.card().classes("w-[420px] gap-3"):
    ui.label("A pop-up window").classes("text-h6")
    with ui.row().classes("w-full justify-end"):
        ui.button("Close", on_click=dialog.close).props("flat no-caps")

ui.button("Open the dialog", on_click=dialog.open)
""",
    ):
        with ui.expansion("More settings", icon="tune").classes("w-full"):
            ui.label("Hidden until opened")

        with ui.dialog() as dialog, ui.card().classes("w-[420px] gap-3"):
            ui.label("A pop-up window").classes("text-h6")

            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dialog.close).props("flat no-caps")

        ui.button("Open the dialog", on_click=dialog.open).props("outline no-caps")

    with demo(
        "Buttons",
        """
ui.button("Unelevated", icon="play_arrow").props("unelevated no-caps")  # main action
ui.button("Outline", icon="refresh").props("outline no-caps")           # other actions
ui.button("Flat", icon="close").props("flat no-caps")                   # cancel, minor
ui.button("Danger", icon="stop_circle").props("outline no-caps color=negative")
ui.button("Not wired", on_click=lambda: not_implemented("Not wired"))
""",
        "The props the pages use, by importance",
    ):
        with ui.row().classes("gap-2"):
            ui.button("Unelevated", icon="play_arrow").props("unelevated no-caps")
            ui.button("Outline", icon="refresh").props("outline no-caps")
            ui.button("Flat", icon="close").props("flat no-caps")
            ui.button("Danger", icon="stop_circle").props(
                "outline no-caps color=negative"
            )
            ui.button("Not wired", on_click=lambda: not_implemented("Not wired")).props(
                "flat no-caps"
            )


# --------------------------------------------------------------------------------------
# Text and tiles: the text classes, key_values, stat tiles, labels
# --------------------------------------------------------------------------------------
def _text() -> None:
    with demo(
        "Text classes",
        """
ui.label("mls-card-title").classes("mls-card-title")
ui.label("mls-card-caption").classes("mls-card-caption")
ui.label("text-body2").classes("text-body2")
ui.label("text-body2 text-weight-medium").classes("text-body2 text-weight-medium")
ui.label("text-h6").classes("text-h6")
ui.label("mls-mono").classes("mls-mono")
ui.label("text-warning text-caption").classes("text-warning text-caption")
ui.label("text-negative text-body2").classes("text-negative text-body2")
""",
        "mls-* are ours (studio/static/studio.css); the others are Quasar's",
    ):
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

    with demo(
        "key_values",
        """
from studio.components.cards import key_values

key_values({"Network": "1-LV-rural1--0-sw", "Participants": 13, "Day": "2016-06-15"})
""",
        "Label and value pairs: the Summary page's settings cards",
    ):
        key_values(
            {"Network": "1-LV-rural1--0-sw", "Participants": 13, "Day": "2016-06-15"}
        )

    with demo(
        "stat and stat_grid",
        """
from studio.components.cards import stat, stat_grid

with stat_grid():
    stat("Participants", "13", "21 elements taken over", "groups")
    stat("Demand", "184 kWh", "over the day", "bolt", "info")
    stat("Generation", "96 kWh", icon="solar_power", tone="warning")
""",
        "Number tiles in a grid that wraps (the Day profiles tab)",
    ):
        with stat_grid():
            stat("Participants", "13", "21 elements taken over", "groups")
            stat("Demand", "184 kWh", "over the day", "bolt", "info")
            stat("Generation", "96 kWh", icon="solar_power", tone="warning")

    with demo(
        "labels: display names of choices",
        """
from studio.components.labels import BACKGROUNDS, MECHANISMS, STEP_LENGTHS

ui.select(STEP_LENGTHS, label="Market step")   # a choice, as the Grid page offers it
STEP_LENGTHS.get(1.0)                          # its name, as the Summary page shows it
""",
        "One place for the words, shared by the page that sets a choice and the "
        "page that shows it",
    ):
        ui.select(STEP_LENGTHS, value=1.0, label="Market step").classes("w-72")
        key_values(
            {
                "MECHANISMS": ", ".join(MECHANISMS.values()),
                "BACKGROUNDS": ", ".join(BACKGROUNDS.values()),
                "STEP_LENGTHS": ", ".join(STEP_LENGTHS.values()),
            }
        )


# --------------------------------------------------------------------------------------
# States: nothing yet, loading, failed, filled
# --------------------------------------------------------------------------------------
def _states() -> None:
    with demo(
        "placeholder",
        """
from studio.components.cards import placeholder

placeholder("Tick runs in the table to compare them.", "checklist")
""",
        "Where content will appear once there is something to show",
    ):
        placeholder("Tick runs in the table to compare them.", "checklist")

    with demo(
        "busy and failed",
        """
from studio.components.cards import busy, failed

busy(box, "Building topology …")              # a spinner while a slow call runs
failed(box, ValueError("network not found"))  # the error in its place
""",
        "Both replace a box's content; fill (below) uses them",
    ):
        box = ui.column().classes("w-full")
        busy(box, "Building topology …")

        with ui.row().classes("gap-2"):
            ui.button(
                "busy", on_click=lambda: busy(box, "Building topology …")
            ).props("outline no-caps")
            ui.button(
                "failed",
                on_click=lambda: failed(box, ValueError("network not found")),
            ).props("outline no-caps")

    with demo(
        "fill: read in the background, then draw",
        """
from studio.components.cards import fill

await fill(
    box,
    lambda: s.profiles.day_profiles(scenario),       # slow: runs in a thread
    lambda day: ui.plotly(day_figure(day, day.owned())),   # then drawn into box
    "Reading the profiles …",
)
""",
        "The usual way a page shows data: spinner, read, then the drawing or the "
        "error. Here the read waits a second",
    ):
        box = ui.column().classes("w-full")

        with box:
            placeholder("Press a button to fill this box.", "download")

        def slow(fails: bool) -> list[float]:
            time.sleep(1.0)

            if fails:
                raise ValueError("the read failed")

            return SUN

        def draw(values: list[float]) -> None:
            fig = series_figure(clock(HOURS), [Line("PV", values)], height=220)
            ui.plotly(fig).classes("w-full")

        with ui.row().classes("gap-2"):
            ui.button(
                "fill", on_click=lambda: fill(box, lambda: slow(False), draw)
            ).props("outline no-caps")
            ui.button(
                "fill, and the read fails",
                on_click=lambda: fill(box, lambda: slow(True), draw),
            ).props("outline no-caps")


# --------------------------------------------------------------------------------------
# Tables: data_table, badges, trades
# --------------------------------------------------------------------------------------
def _tables() -> None:
    rows = [
        {"id": "P1", "bus": "B2", "battery": "10 kWh", "state": "done"},
        {"id": "P2", "bus": "B4", "battery": "—", "state": "running"},
        {"id": "P3", "bus": "B5", "battery": "5 kWh", "state": "failed"},
    ]
    colors = {"done": "positive", "running": "info", "failed": "negative"}

    for row in rows:
        row["c"] = colors[row["state"]]

    with demo(
        "data_table",
        """
from studio.components.tables import data_table

data_table(
    rows,                                   # a list of dicts, one per row
    [("id", "Participant"), ("bus", "Bus"), ("battery", "Battery")],
    pagination=10,                          # rows per page; 0 = all
)
""",
        "The standard table: sortable columns, (field, header) pairs",
    ):
        data_table(
            rows, [("id", "Participant"), ("bus", "Bus"), ("battery", "Battery")]
        )

    with demo(
        "data_table with a badge column",
        """
data_table(
    rows,
    [("id", "Run"), ("state", "State")],
    badge_columns={"state": "c"},           # the colour comes from the row's "c"
)
""",
        "A value as a coloured chip (the RL probes' PASS / FAIL)",
    ):
        data_table(
            rows, [("id", "Run"), ("state", "State")], badge_columns={"state": "c"}
        )

    with demo(
        "data_table with single selection",
        """
table = data_table(rows, [("id", "Participant"), ("bus", "Bus")])
table.props("selection=single")
table.on_select(lambda e: ui.notify(e.selection))
""",
        "The Grid page's participant table opens the battery editor this way",
    ):
        table = data_table(rows, [("id", "Participant"), ("bus", "Bus")])
        table.props("selection=single")
        table.on_select(
            lambda e: ui.notify(
                f"Selected: {e.selection[0]['id']}" if e.selection else "None"
            )
        )

    with demo(
        "trades_table",
        """
from studio.components.tables import trades_table

trades_table(trades)              # list of core Trade records
trades_table(trades, fees=True)   # with distance, fee and who pays it
""",
        "A market step's trades (the Market page's Step and Probes tabs)",
    ):
        trades_table(TRADES, fees=True)


# --------------------------------------------------------------------------------------
# Colours: the palette and the colours with a meaning (studio/theme.py)
# --------------------------------------------------------------------------------------
def _swatches(colors: dict[str, str]) -> None:
    """One chip per colour: a square of it, its name and its code."""
    with ui.row().classes("gap-3"):
        for name, color in colors.items():
            # One chip: the colour square | name over code
            with ui.row().classes("items-center gap-2 no-wrap"):
                ui.element("div").style(
                    f"background: {color}; width: 28px; height: 28px; "
                    "border-radius: 6px"
                )

                with ui.column().classes("gap-0"):
                    ui.label(name).classes("text-body2")
                    ui.label(color).classes("mls-mono mls-card-caption")


def _colours() -> None:
    with demo(
        "SERIES: the categorical palette",
        """
from studio.components.charts import palette
from studio.theme import SERIES

colors = palette(["run a", "run b", "run c"])   # a colour per key, in order
""",
        "Runs, paradigms, agents: anything without a colour of its own. A Line "
        "without a colour takes the next one",
    ):
        _swatches({f"SERIES[{i}]": c for i, c in enumerate(SERIES)})

    with demo(
        "Colours with a meaning",
        """
from studio.theme import BUS, ENERGY, HIGHLIGHT, LIMIT, MARKET, MUTED

Level(0.95, color=LIMIT)                     # a voltage limit
Line("Demand", kw, color=ENERGY["load"])     # the same blue on every page
""",
        "The same thing has the same colour on every page; change it here, it "
        "changes everywhere",
    ):
        ui.label("MUTED, LIMIT, HIGHLIGHT").classes("mls-card-caption")
        _swatches({"MUTED": MUTED, "LIMIT": LIMIT, "HIGHLIGHT": HIGHLIGHT})
        ui.label("ENERGY: element types of a day").classes("mls-card-caption")
        _swatches(ENERGY)
        ui.label("MARKET: sides and counterparts").classes("mls-card-caption")
        _swatches(MARKET)
        ui.label("BUS: bus kinds of the network plot").classes("mls-card-caption")
        _swatches(BUS)

    with demo(
        "PALETTE: Quasar's named colours",
        """
ui.button("Save").props("color=primary")
ui.label("Failed").classes("text-negative")
ui.badge("done", color="positive")
""",
        "Set by apply_theme(); the names work in props (color=...) and classes "
        "(text-..., bg-...)",
    ):
        _swatches(PALETTE)


# --------------------------------------------------------------------------------------
# Series: Line, Level, series_figure, and the figures built from them
# --------------------------------------------------------------------------------------
def _series() -> None:
    hours = clock(HOURS)
    demand = DAY.elements[0].kw

    with demo(
        "series_figure: lines and levels",
        """
from studio.components.charts import Level, Line, series_figure

fig = series_figure(
    hours,                                          # the shared x
    [Line("Demand", demand), Line("PV", sun)],      # what to draw
    [Level(2.5, "A limit", color=LIMIT)],           # reference lines
    y_title="kW",
    height=280,
)
ui.plotly(fig).classes("w-full")
""",
        "The general figure: every series chart of the Studio is a list of Lines "
        "and Levels",
    ):
        fig = series_figure(
            hours,
            [Line("Demand", demand), Line("PV", SUN)],
            [Level(2.5, "A limit", color=LIMIT)],
            y_title="kW",
            height=280,
        )
        ui.plotly(fig).classes("w-full")

    with demo(
        "Line: how a line looks",
        """
Line("solid", y)                                 # the defaults
Line("dash", y, dash="dash")                     # or "dot", "dashdot"
Line("hv", y, shape="hv")                        # holds over the step (energy)
Line("markers", y, kind="lines+markers")         # or "markers"
Line("faint", y, width=1, opacity=0.45)
""",
        "Each line below is the same values, moved up by one",
    ):
        looks = {
            "solid": {},
            "dash": dict(dash="dash"),
            "hv": dict(shape="hv"),
            "markers": dict(kind="lines+markers"),
            "faint": dict(width=1, opacity=0.45),
        }
        lines = [
            Line(name, [v + i for v in SUN], **look)
            for i, (name, look) in enumerate(looks.items())
        ]
        ui.plotly(series_figure(hours, lines, height=300)).classes("w-full")

    with demo(
        "Bars, stacked, with a second unit on the right",
        """
lines = [
    Line("Peer to peer", p2p, kind="bar", color=MARKET["p2p"]),
    Line("With the DSO", dso, kind="bar", color=MARKET["dso"]),
    Line("Price", price, kind="lines+markers", right=True, color=MARKET["sell"]),
]
series_figure(hours, lines, y_title="kWh", right_title="price per kWh", stacked=True)
""",
        "The Step page's day: bars and a line with its own axis",
    ):
        p2p = [round(min(s, d), 2) for s, d in zip(SUN, demand)]
        dso = [round(max(d - s, 0.0), 2) for s, d in zip(SUN, demand)]
        price = [0.12 if v > 0 else None for v in p2p]
        lines = [
            Line("Peer to peer", p2p, kind="bar", color=MARKET["p2p"]),
            Line("With the DSO", dso, kind="bar", color=MARKET["dso"]),
            Line(
                "Price", price, kind="lines+markers", right=True, color=MARKET["sell"]
            ),
        ]
        fig = series_figure(
            hours,
            lines,
            y_title="kWh",
            right_title="price per kWh",
            stacked=True,
            height=300,
        )
        ui.plotly(fig).classes("w-full")

    with demo(
        "A band, and lines with their own x",
        """
Line("mean ± σ", mean, x=steps, band=(mean - sigma, mean + sigma))
Line("Supply", prices, x=cumulative_kwh, shape="hv")   # x of its own
series_figure(None, lines, ...)                         # no shared x
""",
        "The RL probes' action parts use the band; the Step page's order book, "
        "lines with their own x",
    ):
        steps = list(range(0, 50_000, 5_000))
        mean = [0.8 * (1 - 0.9**i) for i in range(len(steps))]
        sigma = [0.5 * 0.8**i for i in range(len(steps))]
        lines = [
            Line(
                "mean ± σ",
                mean,
                x=steps,
                band=(
                    [m - s for m, s in zip(mean, sigma)],
                    [m + s for m, s in zip(mean, sigma)],
                ),
            )
        ]
        levels = [Level(1.0), Level(-1.0)]
        fig = series_figure(
            None, lines, levels, x_title="environment steps", height=260
        )
        ui.plotly(fig).classes("w-full")

    with demo(
        "Panels: add_series and add_levels into make_subplots",
        """
from plotly.subplots import make_subplots
from studio.components.charts import add_levels, add_series, styled

fig = make_subplots(rows=2, cols=1, shared_xaxes=True)
add_series(fig, hours, [Line("Demand", demand)], row=1, col=1)
add_series(fig, hours, [Line("PV", sun, color=ENERGY["sgen"])], row=2, col=1)
add_levels(fig, [Level(2.0, "2 kW")], row=1, col=1)
ui.plotly(styled(fig, 380))
""",
        "For stacked panels on one x axis (the RL probes' action parts)",
    ):
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08)
        add_series(fig, hours, [Line("Demand", demand)], row=1, col=1)
        add_series(fig, hours, [Line("PV", SUN, color=ENERGY["sgen"])], row=2, col=1)
        add_levels(fig, [Level(2.0, "2 kW")], row=1, col=1)
        ui.plotly(styled(fig, 380)).classes("w-full")

    with demo(
        "line_figure",
        """
from studio.adapters.models import Series
from studio.components.charts import line_figure

series = Series(x=[...], y={"A": [...], "B": [...]}, y_label="kW")
ui.plotly(line_figure(series, height=260)).classes("w-full")
ui.plotly(line_figure(series, kind="bar", dashed=("B",)))
""",
        "A Series (the profile service's) as lines or bars; built on series_figure",
    ):
        series = Series(
            x=list(range(24)),
            y={"A": demand, "B": SUN},
            x_label="hour",
            y_label="kW",
        )
        ui.plotly(line_figure(series, height=260)).classes("w-full")

    with demo(
        "day_figure",
        """
from studio.components.charts import day_figure

ui.plotly(day_figure(day, day.owned())).classes("w-full")      # participants'
ui.plotly(day_figure(day, day.background(), faint=True))       # switched off
""",
        "Demand, generation and storage summed per step (DayProfiles from "
        "s.profiles.day_profiles); built on series_figure",
    ):
        ui.plotly(day_figure(DAY, DAY.owned())).classes("w-full")

    with demo(
        "element_figure",
        """
from studio.components.charts import element_figure

lines = {e.id: e.kw for e in day.owned()}
ui.plotly(element_figure(day, lines)).classes("w-full")
""",
        "One line per element or participant over the day; built on series_figure",
    ):
        ui.plotly(element_figure(DAY, {e.id: e.kw for e in DAY.owned()})).classes(
            "w-full"
        )

    with demo(
        "styled: the Studio's look on any figure",
        """
import plotly.graph_objects as go
from studio.components.charts import styled

fig = go.Figure()
fig.add_bar(x=["CTCE", "CTDE", "DTDE"], y=[0.6, 0.4, 0.3])
ui.plotly(styled(fig, 260, "team return")).classes("w-full")
""",
        "For a figure that is not a series (a box plot, a heatmap): height, "
        "transparent background, font, grid, legend below",
    ):
        fig = go.Figure()
        fig.add_bar(x=["CTCE", "CTDE", "DTDE"], y=[0.6, 0.4, 0.3])
        ui.plotly(styled(fig, 260, "team return")).classes("w-full")


# --------------------------------------------------------------------------------------
# Network: topology_figure, and links and rings on it
# --------------------------------------------------------------------------------------
VOLTAGES = {"B0": 1.0, "B1": 1.0, "B2": 0.97, "B3": 1.02, "B4": 0.99, "B5": 0.92}


def _network() -> None:
    with demo(
        "topology_figure",
        """
from studio.components.charts import topology_figure

fig = topology_figure(topology, highlight={"B2", "B4"}, height=320)
plot = ui.plotly(fig).classes("w-full")
plot.on("plotly_click", on_click)            # clicked_bus(e) gives the bus
""",
        "Buses coloured by kind (BUS in theme.py), amber rings for highlighted "
        "buses; a click gives the bus' ID (the Grid page places participants so)",
    ):
        fig = topology_figure(TOPOLOGY, highlight={"B2", "B4"}, height=320)
        ui.plotly(fig).classes("w-full")

    with demo(
        "topology_figure with voltages",
        """
fig = topology_figure(
    topology,
    voltages={"B1": 1.0, "B2": 0.97, ...},   # bus colour, 0.93 to 1.05 pu
    violating={"B5"},                        # red rings: outside the limits
    height=320,
)
""",
        "After a power flow (the Step page)",
    ):
        fig = topology_figure(
            TOPOLOGY, voltages=VOLTAGES, violating={"B5"}, height=320
        )
        ui.plotly(fig).classes("w-full")

    with demo(
        "add_links and add_rings: drawing on the network",
        """
from studio.components.charts import Link, Ring, add_links, add_rings

fig = topology_figure(topology, height=360)
add_links(fig, topology, [Link("B3", "B2", 1.5, "P1 → P2: 1.5 kWh")],
          MARKET["p2p"], "Peer trade")
add_links(fig, topology, [Link("B0", "B4", 0.4)], MARKET["dso"], "DSO trade",
          dash="dash")
add_rings(fig, topology, [Ring("B3", "P1 sells")], MARKET["sell"], "Seller")
add_rings(fig, topology, [Ring("B2"), Ring("B4")], MARKET["buy"], "Buyer")
""",
        "A link's width follows its amount; the Step page draws trades and orders "
        "this way",
    ):
        fig = topology_figure(TOPOLOGY, height=360)
        add_links(
            fig,
            TOPOLOGY,
            [
                Link("B3", "B2", 1.5, "P1 → P2: 1.5 kWh"),
                Link("B3", "B4", 0.8, "P1 → P3: 0.8 kWh"),
            ],
            MARKET["p2p"],
            "Peer trade",
        )
        add_links(
            fig,
            TOPOLOGY,
            [Link("B0", "B4", 0.4, "DSO → P3: 0.4 kWh")],
            MARKET["dso"],
            "DSO trade",
            dash="dash",
        )
        add_rings(fig, TOPOLOGY, [Ring("B3", "P1 sells")], MARKET["sell"], "Seller")
        add_rings(
            fig,
            TOPOLOGY,
            [Ring("B2", "P2 buys"), Ring("B4", "P3 buys")],
            MARKET["buy"],
            "Buyer",
        )
        ui.plotly(fig).classes("w-full")

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
# Style lab: change a Line's settings and see the figure follow
# --------------------------------------------------------------------------------------
def _lab() -> None:
    """Controls on the left, the figure and the call that draws it on the right."""
    hours = clock(HOURS)
    demand = DAY.elements[0].kw

    with section(
        "Style lab",
        "Try a look for a line: the figure and its code follow every change. "
        "Nothing is saved; copy the code into a page",
        "palette",
    ):
        # One row: the controls (left, fixed width) | figure and code (right)
        with ui.row().classes("w-full gap-6 items-start no-wrap"):
            # Left: one control per setting of Line and series_figure
            with ui.column().classes("w-72 shrink-0 gap-2"):
                kind = ui.select(
                    ["lines", "lines+markers", "markers", "bar"],
                    value="lines",
                    label="kind",
                ).classes("w-full")
                shape = ui.toggle(["linear", "hv"], value="hv").props("no-caps dense")
                dash = ui.select(
                    ["solid", "dot", "dash", "dashdot"], value="solid", label="dash"
                ).classes("w-full")
                color = ui.select(
                    {"": "palette (default)"}
                    | {c: f"SERIES · {c}" for c in SERIES}
                    | {c: f"ENERGY · {k}" for k, c in ENERGY.items()},
                    value="",
                    label="color",
                ).classes("w-full")
                ui.label("width").classes("mls-card-caption")
                width = ui.slider(min=0.5, max=6, step=0.5, value=2)
                ui.label("opacity").classes("mls-card-caption")
                opacity = ui.slider(min=0.1, max=1, step=0.05, value=1)
                ui.label("height").classes("mls-card-caption")
                height = ui.slider(min=200, max=500, step=20, value=300)
                band = ui.switch("band (±0.5 around the line)")
                right = ui.switch("second line on the right axis")
                levels = ui.switch("levels (a limit and zero)", value=True)
                stacked = ui.switch("stacked (bars)")

            # Right: the figure, then the code that draws it
            with ui.column().classes("grow basis-0 min-w-0 gap-2"):
                plot = ui.plotly(go.Figure()).classes("w-full")
                code = ui.code("", language="python").classes("w-full")

    def redraw() -> None:
        look = dict(
            kind=kind.value,
            shape=shape.value,
            dash=dash.value,
            width=width.value,
            opacity=opacity.value,
        )

        if color.value:
            look["color"] = color.value

        if band.value:
            look["band"] = ([v - 0.5 for v in demand], [v + 0.5 for v in demand])

        lines = [Line("Demand", demand, **look)]

        if right.value:
            lines.append(Line("PV", SUN, color=ENERGY["sgen"], right=True))

        shown = [Level(2.5, "A limit", color=LIMIT), Level(0.0)] if levels.value else []
        plot.update_figure(
            series_figure(
                hours,
                lines,
                shown,
                y_title="kW",
                right_title="kW (PV)" if right.value else "",
                stacked=stacked.value,
                height=int(height.value),
            )
        )
        settings = ", ".join(
            f"{k}={v!r}" for k, v in look.items() if k != "band"
        ) + (", band=(low, high)" if band.value else "")
        text = f'Line("Demand", demand, {settings})'

        if right.value:
            text += '\nLine("PV", sun, color=ENERGY["sgen"], right=True)'

        call = (
            f"series_figure(hours, lines, levels, y_title=\"kW\", "
            f"stacked={stacked.value}, height={int(height.value)})"
        )
        code.set_content(f"{text}\n\n{call}")

    for control in (
        kind,
        shape,
        dash,
        color,
        width,
        opacity,
        height,
        band,
        right,
        levels,
        stacked,
    ):
        control.on_value_change(lambda _: redraw())

    redraw()
