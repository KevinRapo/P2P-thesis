"""Grid & Participants: pick the network and the day, place the participants, and
set the market and the DSO.

Writes ``scenario.grid``, ``scenario.participants``, ``scenario.market`` and
``scenario.dso`` (saved at once). A participant sits on one bus and takes over the
loads and generators there: their SimBench profiles become its demand and
generation. Grid fees are not offered as settings.
"""

from __future__ import annotations

from dataclasses import replace

from nicegui import background_tasks, run, ui

from core.config.scenario import BatterySetup
from core.grid.contract import NetworkRef
from core.market.clearing_price import DESCRIPTIONS
from studio.components.cards import busy, failed, fill, section
from studio.components.charts import day_figure, topology_figure
from studio.components.labels import BACKGROUNDS, MECHANISMS, STEP_LENGTHS
from studio.components.network import NetworkPicker, clicked_bus
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """Network and day on the left, the network with its participants on the right;
    below them the participants' day, the participant list and the market panel."""
    s = services()
    scenario = s.scenario.current()

    with shell(
        "grid",
        "Grid & Participants",
        "Pick the network and the day, place the participants on its buses, and set "
        "the market and the DSO. Changes are saved at once; the Step page builds the "
        "market from them (press Reset there to play with new settings).",
    ):
        # Top row: settings card (left, a third) | network plot card (right)
        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            # Left card: network picker, "Use this network", then the grid settings
            with section(
                "Network and day",
                "The network the market runs on, and the day of its profiles",
                "hub",
                classes="basis-1/3 min-w-[360px]",
            ):
                picker_box = ui.column().classes("w-full gap-2")
                apply_box = ui.column().classes("w-full gap-1")
                _grid_settings(on_change=lambda: show_day_later())

            # Right card: the clickable network plot, the placement buttons under it
            with section(
                "Participants on the network",
                "Click a bus to add a participant there (or remove it). Amber rings "
                "are participants.",
                "groups",
                classes="grow",
            ):
                plot_box = ui.column().classes("w-full")
                placement_box = ui.column().classes("w-full gap-1")

        # Card, full width: the participants' summed demand and generation over the
        # day (filled by show_day)
        with section(
            "Participants over the day",
            "Their summed demand and generation per step, on the scenario's day",
            "show_chart",
        ):
            day_box = ui.column().classes("w-full")

        # Bottom card, full width: the participant table with its battery editor
        with section(
            "Participants",
            "Each takes over the loads and generators on its bus. Select one to "
            "give it a battery.",
            "list",
        ):
            table_box = ui.column().classes("w-full")

        # Market panel, full width: three cards side by side, Clearing | Bidding |
        # DSO (moved here from the former Market & DSO page)
        with section(
            "Market and DSO",
            "How orders are matched and priced, how participants bid, and what the "
            "DSO pays and charges",
            "storefront",
        ):
            with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
                with section(
                    "Clearing",
                    "Three stages: preferences, double auction, DSO",
                    "gavel",
                    classes="grow basis-0",
                ):
                    _clearing()
                with section(
                    "Bidding",
                    "The rule that writes each participant's order",
                    "sell",
                    classes="grow basis-0",
                ):
                    _bidding()
                with section(
                    "DSO",
                    "Buys what is left over, sells what is missing",
                    "account_balance",
                    classes="grow basis-0",
                ):
                    _dso()

    state: dict = {"topology": None, "shown": scenario.grid.code, "kinds_of": None}

    async def load(source: NetworkRef) -> None:
        """Show the picked network; offer to use it if it is not the scenario's."""
        state["shown"] = source.code
        apply_box.clear()

        if source.code != s.scenario.current().grid.code:
            count = len(s.scenario.current().participants)

            # Under the picker: "Use this network", with a warning if it removes
            # participants
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
            # The network plot in the right card; a click on a bus calls on_click
            with plot_box:
                marked = {p.bus for p in current.participants} if own else set()
                plot = ui.plotly(
                    topology_figure(topology, highlight=marked, height=480)
                ).classes("w-full")
                plot.on("plotly_click", on_click)

        if state["kinds_of"] != current.grid.code:  # the bus kinds of this network
            state["kinds_of"] = current.grid.code
            _placement_buttons(placement_box, redraw)

        _participant_table(table_box, redraw)
        show_day_later()

    async def show_day() -> None:
        """The participants' summed demand and generation on the scenario's day."""
        current = s.scenario.current()

        if not current.participants:
            day_box.clear()

            with day_box:
                ui.label("No participants yet.").classes("mls-card-caption")

            return

        await fill(
            day_box,
            lambda: s.profiles.day_profiles(current),
            lambda day: ui.plotly(day_figure(day, day.owned())).classes("w-full"),
            "Reading the profiles …",
        )

    def show_day_later() -> None:
        """Start ``show_day`` from code that cannot wait for it (``redraw`` and the
        settings' handlers are plain functions)."""
        background_tasks.create(show_day())

    # The network picker at the top of the left card; picking one calls load()
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
def _grid_settings(on_change=None) -> None:
    """Day, step length, background and limits, saved on every change; then
    ``on_change()``, if given."""
    s = services()
    g = s.scenario.current().grid

    def save(field: str, value) -> None:
        setattr(s.scenario.current().grid, field, value)
        s.scenario.save()

        if on_change is not None:
            on_change()

    ui.separator()

    # Day field; the calendar icon at its right end opens a date picker
    with ui.input("Day (2016)", value=g.day).classes("w-full") as day:
        # The pop-up calendar (opened by the icon only, not by clicking the field)
        with ui.menu().props("no-parent-event") as menu:
            with ui.date(value=g.day).props(
                'minimal default-year-month="2016/06"'
            ).bind_value(day):
                # Close button under the calendar
                with ui.row().classes("justify-end"):
                    ui.button("Close", on_click=menu.close).props("flat")

        # The calendar icon, inside the field on the right
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

    # Limits, three number fields in one row: V min | V max | Line max
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
def _placement_buttons(box: ui.element, redraw) -> None:
    """Place one participant on every bus of the chosen kinds, or clear them."""
    s = services()
    counts = s.scenario.kind_counts()
    box.clear()

    # One row under the plot: bus kinds | battery size | its power | Place | Clear
    with box, ui.row().classes("w-full items-end gap-2"):
        kinds = (
            ui.select(
                {k: f"{k} ({n})" for k, n in counts.items()},
                value=[k for k in counts if "load" in k],
                multiple=True,
                label="Bus kinds",
            )
            .props("use-chips")
            .classes("min-w-[280px] grow")
        )
        battery = ui.number(
            "Battery for generator buses (kWh)", value=10, min=0, step=5
        ).classes("w-60")
        power = ui.number("Its max power (kW, empty: none)", min=0).classes("w-56")

        async def place() -> None:
            if not kinds.value:
                ui.notify("Pick at least one bus kind", type="warning")
                return

            n = await run.io_bound(
                s.scenario.place_all,
                list(kinds.value),
                float(battery.value or 0),
                float(power.value) if power.value else None,
            )
            ui.notify(f"{n} participants placed")
            redraw()

        ui.button("Place", icon="groups", on_click=place).props("outline no-caps")
        ui.button(
            "Clear",
            icon="delete",
            on_click=lambda: (s.scenario.clear(), redraw()),
        ).props("flat no-caps color=negative")

    # Explanation under the row
    with box:
        ui.label(
            "A bus kind is what the bus carries (load, pv, gen = other generator, "
            "storage), with how many buses have it. Placing replaces the current "
            "participants. A bus with storage keeps it as its battery; other buses "
            "with a generator get the battery above (0: none)."
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
                    "battery": (
                        f"{p.battery.capacity_kwh:g} kWh"
                        + (
                            f", {p.battery.max_power_kw:g} kW"
                            if p.battery.max_power_kw
                            else ""
                        )
                        if p.battery
                        else "—"
                    ),
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

        # Battery editor under the table, filled when a row is selected (edit)
        editor = ui.column().classes("w-full")

        def edit(e) -> None:
            editor.clear()

            if not e.selection:
                return

            pid = e.selection[0]["id"]
            p = next(x for x in current.participants if x.id == pid)
            storage = s.scenario.storage_of(pid)
            battery = p.battery or storage
            presets = s.scenario.battery_presets()

            # One row: title | size preset | capacity | power | start SoC | Save
            with editor, ui.row().classes("w-full items-end gap-2"):
                ui.label(f"{pid} battery").classes("text-body2 text-weight-medium")
                size = ui.select(
                    {"": "Custom"}
                    | {
                        name: f"SimBench {name}: {b.capacity_kwh:g} kWh, "
                        f"{b.max_power_kw:g} kW"
                        for name, b in presets.items()
                    },
                    value="",
                    label="Size",
                ).classes("w-64")
                cap = ui.number(
                    "Capacity (kWh, 0: none)",
                    value=battery.capacity_kwh if battery else 0,
                    min=0,
                ).classes("w-44")
                power = ui.number(
                    "Max power (kW, empty: none)",
                    value=battery.max_power_kw if battery else None,
                    min=0,
                ).classes("w-52")
                soc = ui.number(
                    "Start SoC (0–1)",
                    value=battery.initial_soc if battery else 0.5,
                    min=0,
                    max=1,
                    step=0.1,
                ).classes("w-36")

                def use_preset(e) -> None:
                    if e.value:
                        cap.value = presets[e.value].capacity_kwh
                        power.value = presets[e.value].max_power_kw

                size.on_value_change(use_preset)

                if storage is not None:  # the storage unit's size is fixed
                    for field in (size, cap, power):
                        field.disable()

                def apply() -> None:
                    if (cap.value or 0) <= 0:
                        new = None
                    else:
                        values = dict(
                            capacity_kwh=float(cap.value),
                            initial_soc=float(soc.value or 0.5),
                            max_power_kw=float(power.value) if power.value else None,
                        )
                        new = (
                            replace(battery, **values)
                            if battery
                            else BatterySetup(**values)
                        )
                    try:
                        ui.notify(s.scenario.set_battery(pid, new))
                    except ValueError as err:
                        ui.notify(str(err), type="negative")
                        return
                    redraw()

                ui.button("Save", icon="check", on_click=apply).props(
                    "unelevated no-caps"
                )

            # Explanation under the row
            with editor:
                ui.label(
                    f"{pid} took over SimBench storage: its capacity and power are "
                    "fixed; only the start SoC can change."
                    if storage is not None
                    else "Size: a SimBench-sized battery (energy = 2 h of its power, "
                    "as every SimBench storage unit), or Custom."
                ).classes("mls-card-caption")

        table.on_select(edit)


# --------------------------------------------------------------------------------------
# Market and DSO: clearing, bidding, the DSO's tariffs
# --------------------------------------------------------------------------------------
def _saver(section_name: str):
    """A function that sets one field of ``scenario.<section_name>`` and saves."""
    s = services()

    def save(field: str, value) -> None:
        if value is None:
            return
        setattr(getattr(s.scenario.current(), section_name), field, value)
        s.scenario.save()

    return save


# --------------------------------------------------------------------------------------
# Clearing
# --------------------------------------------------------------------------------------
def _clearing() -> None:
    m = services().scenario.current().market
    save = _saver("market")

    def mechanism(e) -> None:
        save("mechanism", e.value)
        caption.set_text(DESCRIPTIONS[e.value])

    ui.select(
        MECHANISMS,
        value=m.mechanism,
        label="Price of a peer-to-peer trade",
        on_change=mechanism,
    ).classes("w-full")
    caption = ui.label(DESCRIPTIONS[m.mechanism]).classes("mls-card-caption")

    for pair in (
        (("min_price", "Min price", 0.01), ("max_price", "Max price", 0.01)),
        (
            ("min_quantity", "Min quantity (kWh)", 0.1),
            ("max_quantity", "Max quantity (kWh)", 1),
        ),
    ):
        # Two number fields side by side: min | max
        with ui.row().classes("w-full gap-2 no-wrap"):
            for field, label, step in pair:
                ui.number(
                    label,
                    value=getattr(m, field),
                    step=step,
                    on_change=lambda e, f=field: save(f, float(e.value or 0)),
                ).classes("grow basis-0")

    ui.label(
        "Orders are clipped to these bounds, and to what each participant can "
        "physically deliver or take (its surplus or deficit plus its battery)."
    ).classes("mls-card-caption")
    ui.switch(
        "Preferred partners",
        value=m.partner_preference,
        on_change=lambda e: save("partner_preference", bool(e.value)),
    )
    ui.label(
        "On: every participant names the electrically nearest participant on the "
        "other side as its partner; pairs that name each other trade in stage 1, "
        "before the auction. Off: stage 1 stays empty."
    ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# Bidding
# --------------------------------------------------------------------------------------
def _bidding() -> None:
    m = services().scenario.current().market
    save = _saver("market")
    ui.label(
        "Each participant first charges or discharges its own battery, then sells "
        "what is left over or buys what is missing."
    ).classes("text-body2")

    def explain(margin: float) -> None:
        if margin < 0.5:
            text = "Bids lie above asks: peers trade with each other first."
        elif margin == 0.5:
            text = "Everyone bids the midpoint: trades happen only with jitter."
        else:
            text = "Asks lie above bids: no peer trades, everything goes to the DSO."
        hint.set_text(
            f"Sellers ask FiT + {margin:.2f} × spread, buyers bid utility − "
            f"{margin:.2f} × spread. {text}"
        )

    def margin(e) -> None:
        save("bid_margin", float(e.value))
        explain(float(e.value))

    ui.label("Margin").classes("text-caption")
    ui.slider(min=0, max=1, step=0.05, value=m.bid_margin, on_change=margin).props(
        "label"
    )
    hint = ui.label().classes("mls-card-caption")
    explain(m.bid_margin)
    ui.label("Jitter").classes("text-caption")
    ui.slider(
        min=0,
        max=0.5,
        step=0.05,
        value=m.bid_jitter,
        on_change=lambda e: save("bid_jitter", float(e.value)),
    ).props("label")
    ui.label(
        "Random spread of each price, as a share of the tariff spread, so the order "
        "book shows a range of prices."
    ).classes("mls-card-caption")
    ui.number(
        "Seed",
        value=m.seed,
        step=1,
        on_change=lambda e: save("seed", int(e.value or 0)),
    ).classes("w-full")


# --------------------------------------------------------------------------------------
# DSO
# --------------------------------------------------------------------------------------
def _dso() -> None:
    d = services().scenario.current().dso
    save = _saver("dso")
    ui.number(
        "Feed-in tariff (per kWh)",
        value=d.feed_in_tariff,
        step=0.01,
        on_change=lambda e: save("feed_in_tariff", float(e.value or 0)),
    ).classes("w-full")
    ui.label("What the DSO pays for every kWh it buys (stage 3).").classes(
        "mls-card-caption"
    )
    ui.number(
        "Utility price (per kWh)",
        value=d.utility_price,
        step=0.01,
        on_change=lambda e: save("utility_price", float(e.value or 0)),
    ).classes("w-full")
    ui.label("What the DSO charges for every kWh it sells (stage 3).").classes(
        "mls-card-caption"
    )
    ui.label(
        "Both are constant over the day for now. Local trading pays off between "
        "them: sellers get more than the feed-in tariff, buyers pay less than the "
        "utility price. Grid fees (paper eq. 8) are not charged yet."
    ).classes("mls-card-caption")
