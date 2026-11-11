"""Market: the market played and checked, in three tabs.

Step (``step.py``): play the scenario's market one clearing stage at a time and
watch the network. Baseline (``baseline.py``): the scenario played with the bidding
rule over a window of days, before learning, with an optional sweep of a scaling
factor. Probes (``probes.py``): tiny scripted cases whose outcome is known by hand,
played on both grid methods. Each tab's content is in its own file
in this folder; this file only puts them side by side.
"""

from __future__ import annotations

from nicegui import ui

from studio.components.memory import remember
from studio.layout import shell
from studio.pages.market import baseline
from studio.pages.market import probes as probes_tab
from studio.pages.market import step


def page(tab: str = "") -> None:
    """The three tabs; ``/market?tab=baseline`` or ``?tab=probes`` opens that tab, else
    the one open last. The probes play only when their tab is first opened."""
    with shell(
        "market",
        "Market",
        "Play the market one clearing stage at a time, play the scenario's baseline "
        "over days, or check the market on scripted cases with known outcomes. All "
        "three play the scenario of the Scenario page.",
    ):
        # Tab bar: Step | Baseline | Probes
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            ui.tab("step", label="Step", icon="skip_next")
            ui.tab("baseline", label="Baseline", icon="timeline")
            ui.tab("probes", label="Probes", icon="rule")

        remember(tabs, "market_tab", ("step", "baseline", "probes"))

        if tab in ("step", "baseline", "probes"):  # a link says which
            tabs.value = tab

        # keep_alive=False: a hidden tab is drawn again when opened, so its Plotly
        # charts get the right width
        shown = tabs.value or "step"

        with ui.tab_panels(tabs, value=shown, keep_alive=False).classes(
            "w-full bg-transparent"
        ):
            # Step tab
            with ui.tab_panel("step").classes("p-0 gap-4"):
                step.tab()

            # Baseline tab
            with ui.tab_panel("baseline").classes("p-0 gap-4"):
                baseline.tab()

            # Probes tab
            with ui.tab_panel("probes").classes("p-0 gap-4"):
                probes = probes_tab.tab()

    loaded = {"probes": False}

    async def opened(name: str) -> None:
        """Play the probes the first time their tab is shown."""
        if name == "probes" and not loaded["probes"]:
            loaded["probes"] = True
            await probes.load()

    tabs.on_value_change(lambda e: opened(e.value))

    if shown == "probes":
        ui.timer(0.05, lambda: opened("probes"), once=True)
