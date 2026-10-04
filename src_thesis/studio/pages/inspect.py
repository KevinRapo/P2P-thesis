"""Inspect (05 §6): get to know networks in depth and compare two of them.

Read-only: nothing here changes the experiment file. Three tabs, each built by
its own function: "Network" (one network in depth), "Compare" (two networks side
by side) and "Profiles" (SimBench's complete profile catalogue). Built from the network blocks in ``components/network.py``, shared with
the Grid page.
"""

from nicegui import run, ui

from src_thesis.application.container import Services
from src_thesis.application.models import (
    NetworkSource,
    ProfileClass,
    ProfileType,
    Series,
)
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


@ui.page("/build/inspect")
def inspect_page() -> None:
    """Inspect (05 §6): the "Network" tab shows one network in depth, the
    "Compare" tab two networks side by side, the "Profiles" tab SimBench's complete
    profile catalogue.
    """
    s = services()
    with shell(
        "inspect",
        "Inspect",
        "Explore networks and their data in depth; compare two networks; browse "
        "all SimBench profiles. "
        "Nothing here changes the experiment file.",
    ):
        # ui.tabs is the tab bar; ui.tab_panels holds one panel per tab and shows
        # the selected one. Both panels are built when the page opens.
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            network_tab = ui.tab("Network", icon="travel_explore")
            compare_tab = ui.tab("Compare", icon="compare_arrows")
            profiles_tab = ui.tab("Profiles", icon="show_chart")
        # keep_alive=False: a hidden panel is removed from the browser and drawn
        # again when its tab is opened, so its Plotly charts are never resized
        # while invisible. The Python side (state, handlers) stays as it is.
        with ui.tab_panels(tabs, value=network_tab, keep_alive=False).classes(
            "w-full bg-transparent"
        ):
            with ui.tab_panel(network_tab).classes("p-0 gap-4"):
                _network_tab(s)
            with ui.tab_panel(compare_tab).classes("p-0 gap-4"):
                _compare_tab(s)
            with ui.tab_panel(profiles_tab).classes("p-0 gap-4"):
                catalogue = _profiles_tab(s)
        # The catalogue (about 460 profiles) is read only when its tab is opened.
        tabs.on_value_change(
            lambda e: (
                catalogue.show()
                if e.value == "Profiles" and not catalogue.loaded
                else None
            )
        )


def _network_tab(s: Services) -> None:
    """One network in depth: picker and facts | topology; elements; profiles."""
    # The topology shown and the bus selected in it.
    state: dict = {"topology": None}

    with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
        with section(
            "Network",
            "Any network; the experiment's network is chosen on the Grid page",
            "hub",
            classes="basis-1/3 min-w-[360px]",
        ):
            picker = NetworkPicker(
                s,
                NetworkSource(**DEFAULT_SOURCE),
                on_pick=lambda source: load(source),
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

    async def load(source: NetworkSource) -> None:
        """Show the picked network's facts, topology, elements and profiles."""
        state["topology"] = None
        busy(summary_box, "Loading network …")
        busy(plot_box, "Building topology …")
        try:
            summary = await run.io_bound(s.grid.summary, source)
            topology = await run.io_bound(s.grid.topology, source)
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(summary_box, e)
            return
        if picker.source != source:  # another network was picked meanwhile
            return
        state["topology"] = topology
        show_summary(summary_box, summary)
        show_topology(plot_box, topology, on_click=on_bus_click)
        await elements.show(source)
        await profiles.show(source)

    async def on_bus_click(e) -> None:
        """A bus was clicked: outline it and list its elements."""
        bus = clicked_bus(e)
        show_topology(plot_box, state["topology"], bus=bus, on_click=on_bus_click)
        await elements.show(picker.source, bus)

    picker.start()


def _compare_tab(s: Services) -> None:
    """Two networks side by side: facts, element mix, topologies, profiles."""
    # Per side ("a", "b"): the network with its summary, topology and profile list,
    # so the comparison can be redrawn when either side changes.
    state: dict = {"a": {}, "b": {}}
    all_classes = s.profiles.profile_classes()

    with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
        for side, label, initial in (
            ("a", "Network A", DEFAULT_SOURCE),
            ("b", "Network B", COMPARE_DEFAULT),
        ):
            with section(label, icon="hub", classes="grow basis-0"):
                NetworkPicker(
                    s,
                    NetworkSource(**initial),
                    on_pick=lambda source, side=side: load(side, source),
                    allow_file=False,
                ).start()
    with section(
        "Comparison",
        "Facts, element mix by profile category, topologies and profiles side by side",
        "compare_arrows",
    ):
        compare_box = ui.column().classes("w-full gap-4")

    async def load(side: str, source: NetworkSource) -> None:
        """Load one side's network, then redraw the comparison."""
        state[side] = {"source": source}
        busy(compare_box, "Loading network …")
        try:
            summary = await run.io_bound(s.grid.summary, source)
            topology = await run.io_bound(s.grid.topology, source)
            types = await run.io_bound(s.profiles.profile_types, source)
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(compare_box, e)
            return
        if state[side].get("source") != source:  # picked again meanwhile
            return
        state[side].update(summary=summary, topology=topology, types=types)
        show()

    def show() -> None:
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
            # Only the classes either network uses, so the bars stay readable.
            classes = [
                c
                for c in all_classes
                if any(t.category == c.key for t in a["types"] + b["types"])
            ]
            ui.label("Elements per profile category").classes(
                "text-body2 text-weight-medium"
            )
            ui.plotly(
                line_figure(
                    Series(
                        x=[c.label for c in classes],
                        y={
                            "A": _mix(a["types"], classes),
                            "B": _mix(b["types"], classes),
                        },
                        y_label="elements",
                    ),
                    height=260,
                    kind="bar",
                )
            ).classes("w-full")
            with ui.row().classes("w-full gap-4 no-wrap"):
                for label, net in ((f"A · {name_a}", a), (f"B · {name_b}", b)):
                    with ui.column().classes("grow basis-0 min-w-0 gap-1"):
                        ui.label(label).classes("mls-card-caption")
                        box = ui.column().classes("w-full")
                        show_topology(box, net["topology"], height=320)
            ui.label("Profiles in A and B").classes("text-body2 text-weight-medium")
            in_a = {t.code: t for t in a["types"]}
            in_b = {t.code: t for t in b["types"]}
            codes = sorted(in_a.keys() | in_b.keys())
            if not codes:
                ui.label("Neither network ships profiles.").classes("mls-card-caption")
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


def _profiles_tab(s: Services) -> ProfileInspector:
    """SimBench's complete profile catalogue, independent of any network.

    Returns:
        The inspector; the page calls its ``show`` when the tab is first opened.
    """
    with section(
        "All SimBench profiles",
        "Every profile SimBench ships (scenario 0, year 2016), as factors of rated "
        "power; a network ships only the ones its elements use",
        "show_chart",
    ):
        return ProfileInspector(s, catalogue=True)


def _mix(types: list[ProfileType], classes: list[ProfileClass]) -> list[int]:
    """Number of elements per profile class, in the order of ``classes``."""
    counts: dict[str, int] = {}
    for t in types:
        counts[t.category] = counts.get(t.category, 0) + t.elements
    return [counts.get(c.key, 0) for c in classes]
