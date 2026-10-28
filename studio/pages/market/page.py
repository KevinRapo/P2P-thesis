"""Market: the market played and checked, in two tabs.

Step (``step.py``): play the scenario's market one clearing stage at a time and
watch the network. Probes (``probes.py``): tiny scripted cases whose outcome is
known by hand, played on both grid methods. Each tab's content is in its own file
in this folder; this file only puts them side by side.
"""

from __future__ import annotations

from nicegui import ui

from studio.layout import shell
from studio.pages.market import probes as probes_tab
from studio.pages.market import step


def page(tab: str = "step") -> None:
    """The two tabs; ``/market?tab=probes`` opens the Probes tab. The probes play
    only when their tab is first opened."""
    with shell(
        "market",
        "Market",
        "Play the market one clearing stage at a time, or check it on scripted cases "
        "with known outcomes. Reset builds the market from the Grid & Participants "
        "page.",
    ):
        # Tab bar: Step | Probes
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            ui.tab("step", label="Step", icon="skip_next")
            ui.tab("probes", label="Probes", icon="rule")

        # keep_alive=False: a hidden tab is drawn again when opened, so its Plotly
        # charts get the right width
        shown = tab if tab in ("step", "probes") else "step"

        with ui.tab_panels(tabs, value=shown, keep_alive=False).classes(
            "w-full bg-transparent"
        ):
            # Step tab
            with ui.tab_panel("step").classes("p-0 gap-4"):
                step.tab()

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
