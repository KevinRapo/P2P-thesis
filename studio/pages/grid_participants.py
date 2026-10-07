"""Grid & Participants: pick the network and the day, place the participants.

Writes ``scenario.grid`` and ``scenario.participants`` (saved at once). A
participant sits on one bus and takes over the loads and generators there: their
SimBench profiles become its demand and generation.
"""

from __future__ import annotations

from nicegui import run, ui

from config.scenario import BatterySetup
from grid.contract import NetworkRef
from studio.components.cards import section
from studio.components.charts import topology_figure
from studio.components.network import NetworkPicker, busy, clicked_bus, failed
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services

BACKGROUNDS = {
    "profiles": "SimBench profiles",
    "off": "Off: only the participants",
}
STEP_LENGTHS = {1.0: "1 hour (24 steps)", 0.25: "15 minutes (96 steps)"}


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """Network and day on the left, the network with its participants on the right,
    the participant list below."""
    s = services()
    scenario = s.scenario.current()
    with shell(
        "grid",
        "Grid & Participants",
        "Pick the network and the day, then place the participants on its buses. "
        "Changes are saved at once; the Step page builds the market from them.",
    ):
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Network and day",
                "The network the market runs on, and the day of its profiles",
                "hub",
                classes="basis-1/3 min-w-[360px]",
            ):
                picker_box = ui.column().classes("w-full gap-2")
                apply_box = ui.column().classes("w-full gap-1")
                _grid_settings()
            with section(
                "Participants on the network",
                "Click a bus to add a participant there (or remove it). Amber rings "
                "are participants.",
                "groups",
                classes="grow",
            ):
                plot_box = ui.column().classes("w-full")
                _placement_buttons(lambda: redraw())
        with section(
            "Participants",
            "Each takes over the loads and generators on its bus. Select one to "
            "give it a battery.",
            "list",
        ):
            table_box = ui.column().classes("w-full")

    state: dict = {"topology": None, "shown": scenario.grid.code}

    async def load(source: NetworkRef) -> None:
        """Show the picked network; offer to use it if it is not the scenario's."""
        state["shown"] = source.code
        apply_box.clear()
        if source.code != s.scenario.current().grid.code:
            count = len(s.scenario.current().participants)
            with apply_box:
                ui.button(
                    "Use this network",
                    icon="check",
                    on_click=lambda: use(source.code),
                ).props("unelevated no-caps")
                if count:
                    ui.label(
                        f"Removes the {count} participants placed on "
                        f"{s.scenario.current().grid.code}."
                    ).classes("mls-card-caption text-warning")
        busy(plot_box, "Building topology …")
        try:
            state["topology"] = await run.io_bound(s.grid.topology, source)
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(plot_box, e)
            return
        redraw()

    def use(code: str) -> None:
        s.scenario.set_network(code)
        apply_box.clear()
        ui.notify(f"Network: {code}")
        redraw()

    async def on_click(e) -> None:
        bus = clicked_bus(e)
        if not bus:
            return
        if state["shown"] != s.scenario.current().grid.code:
            ui.notify("Use this network first", type="warning")
            return
        message = await run.io_bound(s.scenario.toggle, bus)
        ui.notify(message)
        redraw()

    def redraw() -> None:
        """Plot with the participants marked, and the participant table."""
        topology = state["topology"]
        current = s.scenario.current()
        own = state["shown"] == current.grid.code
        plot_box.clear()
        if topology is not None:
            with plot_box:
                marked = {p.bus for p in current.participants} if own else set()
                plot = ui.plotly(
                    topology_figure(topology, highlight=marked, height=480)
                ).classes("w-full")
                plot.on("plotly_click", on_click)
        _participant_table(table_box, redraw)

    with picker_box:
        NetworkPicker(
            s,
            NetworkRef("simbench", scenario.grid.code),
            on_pick=load,
            allow_file=False,
        ).start()


# --------------------------------------------------------------------------------------
# Grid settings: day, step length, background, limits
# --------------------------------------------------------------------------------------
def _grid_settings() -> None:
    """Day, step length, background and limits, saved on every change."""
    s = services()
    g = s.scenario.current().grid

    def save(field: str, value) -> None:
        setattr(s.scenario.current().grid, field, value)
        s.scenario.save()

    ui.separator()
    with ui.input("Day (2016)", value=g.day).classes("w-full") as day:
        with ui.menu().props("no-parent-event") as menu:
            with ui.date(value=g.day).props(
                'minimal default-year-month="2016/06"'
            ).bind_value(day):
                with ui.row().classes("justify-end"):
                    ui.button("Close", on_click=menu.close).props("flat")
        with day.add_slot("append"):
            ui.icon("event").on("click", menu.open).classes("cursor-pointer")
    day.on_value_change(lambda e: save("day", e.value) if _is_2016(e.value) else None)
    ui.label(
        "SimBench's profiles cover 2016. A summer day has PV to trade; a winter "
        "evening has heat-pump load."
    ).classes("mls-card-caption")
    ui.select(
        STEP_LENGTHS,
        value=g.step_hours,
        label="Market step",
        on_change=lambda e: save("step_hours", e.value),
    ).classes("w-full")
    ui.select(
        BACKGROUNDS,
        value=g.background,
        label="Rest of the network",
        on_change=lambda e: save("background", e.value),
    ).classes("w-full")
    ui.label(
        "What the elements no participant owns do in the power flow: follow their "
        "profiles, or be switched off so only the market is seen."
    ).classes("mls-card-caption")
    with ui.row().classes("w-full gap-2 no-wrap"):
        for field, label in (
            ("v_min_pu", "V min (pu)"),
            ("v_max_pu", "V max (pu)"),
            ("line_max_percent", "Line max (%)"),
        ):
            ui.number(
                label,
                value=getattr(g, field),
                step=0.01 if field.startswith("v_") else 5,
                on_change=lambda e, f=field: (
                    save(f, float(e.value)) if e.value is not None else None
                ),
            ).classes("grow basis-0")


def _is_2016(value: str | None) -> bool:
    return bool(value) and str(value).startswith("2016-") and len(value) == 10


# --------------------------------------------------------------------------------------
# Placing participants
# --------------------------------------------------------------------------------------
def _placement_buttons(redraw) -> None:
    """Place one participant per load bus or per prosumer bus, or clear them."""
    s = services()
    with ui.row().classes("w-full items-end gap-2"):
        battery = ui.number(
            "Battery for PV buses (kWh)", value=10, min=0, step=5
        ).classes("w-56")

        async def place(which: str) -> None:
            n = await run.io_bound(
                s.scenario.place_all, which, float(battery.value or 0)
            )
            ui.notify(f"{n} participants placed")
            redraw()

        ui.button(
            "One per load bus", icon="home", on_click=lambda: place("loads")
        ).props("outline no-caps")
        ui.button(
            "One per prosumer bus",
            icon="solar_power",
            on_click=lambda: place("prosumers"),
        ).props("outline no-caps")
        ui.button(
            "Clear",
            icon="delete",
            on_click=lambda: (s.scenario.clear(), redraw()),
        ).props("flat no-caps color=negative")
    ui.label(
        "A prosumer bus has a load and a generator. Placing replaces the current "
        "participants; buses with PV get the battery size above (0: none)."
    ).classes("mls-card-caption")


def _participant_table(box: ui.element, redraw) -> None:
    """The participants with their elements and battery; selecting one opens its
    battery settings."""
    s = services()
    current = s.scenario.current()
    box.clear()
    with box:
        if not current.participants:
            ui.label(
                "No participants yet: click buses on the network or use the buttons."
            ).classes("mls-card-caption")
            return
        rows = []
        for p in current.participants:
            rows.append(
                {
                    "id": p.id,
                    "bus": p.bus,
                    "elements": len(p.owns),
                    "owns": ", ".join(p.owns),
                    "battery": f"{p.battery.capacity_kwh:g} kWh" if p.battery else "—",
                }
            )
        table = data_table(
            rows,
            [
                ("id", "Participant"),
                ("bus", "Bus"),
                ("elements", "Elements"),
                ("owns", "Takes over"),
                ("battery", "Battery"),
            ],
            pagination=10,
        )
        table.props("selection=single")
        editor = ui.column().classes("w-full")

        def edit(e) -> None:
            editor.clear()
            if not e.selection:
                return
            pid = e.selection[0]["id"]
            p = next(x for x in current.participants if x.id == pid)
            with editor, ui.row().classes("w-full items-end gap-2"):
                ui.label(f"{pid} battery").classes("text-body2 text-weight-medium")
                cap = ui.number(
                    "Capacity (kWh, 0: none)",
                    value=p.battery.capacity_kwh if p.battery else 0,
                    min=0,
                ).classes("w-44")
                soc = ui.number(
                    "Start SoC (0–1)",
                    value=p.battery.initial_soc if p.battery else 0.5,
                    min=0,
                    max=1,
                    step=0.1,
                ).classes("w-36")
                power = ui.number(
                    "Max power (kW, empty: none)",
                    value=p.battery.max_power_kw if p.battery else None,
                    min=0,
                ).classes("w-52")

                def apply() -> None:
                    if (cap.value or 0) <= 0:
                        p.battery = None
                    else:
                        p.battery = BatterySetup(
                            capacity_kwh=float(cap.value),
                            initial_soc=float(soc.value or 0.5),
                            max_power_kw=float(power.value) if power.value else None,
                        )
                    s.scenario.save()
                    ui.notify(f"{pid}: battery saved")
                    redraw()

                ui.button("Save", icon="check", on_click=apply).props(
                    "unelevated no-caps"
                )

        table.on_select(edit)
