"""Inspect (05 §6): get to know networks in depth and compare two of them.

Read-only: nothing here changes the experiment file. Built from the network
blocks in ``components/network.py`` (shared with the Grid page) plus a
comparison of network A with a second network B.
"""

from nicegui import run, ui

from src_thesis.application.models import NetworkSource, Series
from src_thesis.studio.components.cards import section
from src_thesis.studio.components.charts import line_figure
from src_thesis.studio.components.network import (
    DEFAULT_SOURCE,
    ElementsTable,
    NetworkPicker,
    ProfileInspector,
    busy,
    clicked_bus,
    failed,
    show_summary,
    show_topology,
    summary_facts,
)
from src_thesis.studio.components.tables import data_table
from src_thesis.studio.layout import shell
from src_thesis.studio.state import services

COMPARE_DEFAULT = {"type": "simbench", "code": "1-LV-rural1--0-sw"}
CATEGORIES = [
    "household",
    "commercial",
    "agricultural",
    "pv",
    "wind",
    "biomass",
    "storage",
    "other",
]


@ui.page("/build/inspect")
def inspect_page() -> None:
    """Inspect (05 §6): one network in depth (topology, elements, SimBench
    profiles) and a side-by-side comparison with a second network.
    """
    s = services()
    # Page state: per side ("a", "b") the network shown, its summary, topology and
    # profile list, so the comparison can be redrawn without reloading.
    state: dict = {"a": {}, "b": {}, "bus": None}

    with shell(
        "inspect",
        "Inspect",
        "Explore networks and their data in depth; compare two networks. "
        "Nothing here changes the experiment file.",
    ):
        # Row 1: network A picker and facts | its topology.
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Network",
                "Any network; the experiment's network is chosen on the Grid page",
                "hub",
                classes="basis-1/3 min-w-[360px]",
            ):
                picker_a = NetworkPicker(
                    s,
                    NetworkSource(**DEFAULT_SOURCE),
                    on_pick=lambda source: load_side("a", source),
                    allow_file=False,
                )
                summary_box = ui.column().classes("w-full gap-1")
            with section(
                "Topology",
                "Colour = element type. Click a bus to list its elements.",
                "account_tree",
                classes="grow",
            ):
                plot_box = ui.column().classes("w-full")

        # Row 2: elements; Row 3: profiles.
        with section(
            "Elements",
            "Loads, generators and storage, with the profile each one follows",
            "list",
        ):
            elements = ElementsTable(s)
        with section(
            "Profiles",
            "The network's SimBench time series as factors of rated power "
            "(1.0 = rated power); select one or more to plot",
            "show_chart",
        ):
            profiles = ProfileInspector(s)

        # Row 4: comparison with network B.
        with section(
            "Compare with another network",
            "Facts, element mix by profile category, topologies and profiles side "
            "by side",
            "compare_arrows",
        ):
            with ui.row().classes("w-full gap-4 items-start no-wrap"):
                with ui.column().classes("basis-1/4 min-w-[300px]"):
                    ui.label("Network B").classes("text-body2 text-weight-medium")
                    picker_b = NetworkPicker(
                        s,
                        NetworkSource(**COMPARE_DEFAULT),
                        on_pick=lambda source: load_side("b", source),
                        allow_file=False,
                    )
                compare_box = ui.column().classes("grow basis-0 min-w-0 gap-4")

        # ------------------------------------------------------------ handlers
        async def load_side(side: str, source: NetworkSource) -> None:
            """Load one side's network; side A also fills rows 1-3."""
            state[side] = {"source": source}
            if side == "a":
                state["bus"] = None
                busy(summary_box, "Loading network …")
                busy(plot_box, "Building topology …")
            busy(compare_box, "Loading network …")
            try:
                summary = await run.io_bound(s.grid.summary, source)
                topology = await run.io_bound(s.grid.topology, source)
                types = await run.io_bound(s.profiles.profile_types, source)
            except Exception as e:  # noqa: BLE001  show the error on the page
                failed(summary_box if side == "a" else compare_box, e)
                return
            if state[side].get("source") != source:  # picked again meanwhile
                return
            state[side].update(summary=summary, topology=topology, types=types)
            if side == "a":
                show_summary(summary_box, summary)
                show_topology(plot_box, topology, on_click=on_bus_click)
                await elements.show(source)
                await profiles.show(source)
            show_comparison()

        async def on_bus_click(e) -> None:
            """A bus was clicked: list its elements and outline it."""
            state["bus"] = clicked_bus(e)
            show_topology(
                plot_box,
                state["a"]["topology"],
                bus=state["bus"],
                on_click=on_bus_click,
            )
            await elements.show(picker_a.source, state["bus"])

        def show_comparison() -> None:
            """Redraw the comparison once both networks are loaded."""
            a, b = state["a"], state["b"]
            if "summary" not in a or "summary" not in b:
                return
            compare_box.clear()
            with compare_box:
                name_a, name_b = a["summary"].info.label, b["summary"].info.label
                facts_b = dict(summary_facts(b["summary"]))
                data_table(
                    [
                        {"fact": label, "a": value, "b": facts_b.get(label, "—")}
                        for label, value in summary_facts(a["summary"])
                    ],
                    [("fact", ""), ("a", f"A · {name_a}"), ("b", f"B · {name_b}")],
                    row_key="fact",
                    pagination=0,
                )
                ui.label("Elements per profile category").classes(
                    "text-body2 text-weight-medium"
                )
                ui.plotly(
                    line_figure(
                        Series(
                            x=CATEGORIES,
                            y={"A": _mix(a["types"]), "B": _mix(b["types"])},
                            y_label="elements",
                        ),
                        height=260,
                        kind="bar",
                    )
                ).classes("w-full")
                with ui.row().classes("w-full gap-4 no-wrap"):
                    for label, side in ((f"A · {name_a}", a), (f"B · {name_b}", b)):
                        with ui.column().classes("grow basis-0 min-w-0 gap-1"):
                            ui.label(label).classes("mls-card-caption")
                            box = ui.column().classes("w-full")
                            show_topology(box, side["topology"], height=320)
                ui.label("Profiles in A and B").classes("text-body2 text-weight-medium")
                in_a = {t.code: t for t in a["types"]}
                in_b = {t.code: t for t in b["types"]}
                codes = sorted(in_a.keys() | in_b.keys())
                if not codes:
                    ui.label("Neither network ships profiles.").classes(
                        "mls-card-caption"
                    )
                    return
                data_table(
                    [
                        {
                            "code": c,
                            "category": (in_a.get(c) or in_b.get(c)).category,
                            "a": in_a[c].elements if c in in_a else "—",
                            "b": in_b[c].elements if c in in_b else "—",
                        }
                        for c in codes
                    ],
                    [
                        ("code", "Profile"),
                        ("category", "Category"),
                        ("a", "Elements in A"),
                        ("b", "Elements in B"),
                    ],
                    row_key="code",
                    pagination=10,
                )

        picker_a.start()
        picker_b.start()


def _mix(types) -> list[int]:
    """Number of elements per profile category, in ``CATEGORIES`` order."""
    counts = dict.fromkeys(CATEGORIES, 0)
    for t in types:
        counts[t.category] = counts.get(t.category, 0) + t.elements
    return [counts[c] for c in CATEGORIES]
