"""Scenario: build the scenario in the UI, every setting of a scenario file.

Pick the network and the day, place the participants, and set the market and the
DSO, or open a scenario file and change it. Writes ``scenario.grid``,
``scenario.participants``, ``scenario.market`` and ``scenario.dso`` (saved at once),
and can save the result as a file for an experiment to name. A participant sits on
one bus and takes over the loads and generators there: their SimBench profiles become
its demand and generation.
"""

from __future__ import annotations

from dataclasses import replace

from nicegui import background_tasks, run, ui

from core.config.scenario import BatterySetup
from core.grid.contract import NetworkRef
from core.market.clearing_price import DESCRIPTIONS
from studio.components.cards import busy, failed, fill, section
from studio.components.charts import DayChart, NetworkChart, PriceChart
from studio.components.labels import (
    BACKGROUNDS,
    GRAPH_CAPACITIES,
    GRID_METHODS,
    MECHANISMS,
    STEP_LENGTHS,
    VOLTAGE_DROPS,
)
from studio.components.network import NetworkPicker
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """The scenario's file on top; network and day on the left, the network with its
    participants on the right; below them the participants' day, the participant list
    and the market and DSO panels."""
    s = services()
    scenario = s.scenario.current()

    with shell(
        "scenario",
        "Scenario",
        "Build the scenario here, or open a file and change it: the network and the "
        "day, the participants, the market and the DSO. Changes are saved at once; the "
        "Step page builds the market from them (press Reset there to play with new "
        "settings).",
    ):
        # Top card, full width: the scenario's name and saving it as a file
        with section(
            "Scenario file",
            "Saving is optional: the active scenario plays and starts as it is. Saved "
            "here, an experiment file can name it too",
            "save",
        ):
            _save_as()

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
                _grid_settings(on_change=lambda: step_changed())

            # Right card: the clickable network plot, the placement buttons under it
            with section(
                "Participants on the network",
                "Click a bus to add a participant there (or remove it). Red rings "
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
        # Reputation
        with section(
            "Market",
            "How orders are matched and priced, how participants bid, and how "
            "reputation is scored",
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
                    "Reputation",
                    "What a participant's behaviour earns it (eq. 12)",
                    "verified",
                    classes="grow basis-0",
                ):
                    _reputation()

        # DSO panel, full width: two cards side by side, Tariffs | Grid fees
        with section(
            "DSO",
            "Buys what is left over, sells what is missing, and charges for the grid",
            "account_balance",
        ):
            with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
                with section(
                    "Tariffs",
                    "What the DSO pays and charges per kWh",
                    "payments",
                    classes="grow basis-0",
                ):
                    show_tariffs = _tariffs()
                with section(
                    "Grid fees",
                    "What each trade pays for the grid (eq. 8) and loses on the way",
                    "receipt_long",
                    classes="grow basis-0",
                ):
                    _fees()

    state: dict = {"topology": None, "shown": scenario.grid.code, "kinds_of": None}

    def step_changed() -> None:
        """A grid setting changed: the day, and whether the prices fit the step."""
        show_day_later()
        show_tariffs()

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

    async def on_bus(bus: str) -> None:
        """A bus was clicked: add a participant there, or remove it."""
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
            # The network plot in the right card; a click on a bus calls on_bus
            with plot_box:
                marked = {p.bus: p.id for p in current.participants} if own else {}
                NetworkChart(
                    480, on_bus=on_bus, topology=topology, participants=marked
                ).show()

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
            lambda day: DayChart(day=day, elements=day.owned()).show(),
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
# The scenario's file
# --------------------------------------------------------------------------------------
def _save_as() -> None:
    """A file name, following the scenario's until it is typed over, and the button
    that writes the scenario under it."""
    s = services()
    shown = {"name": s.scenario.shown_name()}

    def save() -> None:
        try:
            path = s.scenario.save_as((name.value or "").strip())
        except ValueError as err:
            ui.notify(str(err), type="negative")
            return

        ui.notify(f"Saved as config/scenarios/{path.name}")

    # One row: file name | Save
    with ui.row().classes("w-full items-end gap-2"):
        name = ui.input("File name", value=shown["name"]).classes("w-80")
        ui.button("Save as a scenario file", icon="save", on_click=save).props(
            "outline no-caps"
        )

    def follow() -> None:
        now = s.scenario.shown_name()

        if now != shown["name"]:
            shown["name"] = now
            name.set_value(now)

    ui.timer(1.0, follow)


# --------------------------------------------------------------------------------------
# Grid settings: day, step length, background, limits, grid method
# --------------------------------------------------------------------------------------
def _grid_settings(on_change=None) -> None:
    """Day, step length, background, limits and grid method, saved on every change;
    then ``on_change()``, if given."""
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

    def method(e) -> None:
        save("method", e.value)
        capacity.set_enabled(e.value == "graph")
        total.set_enabled(e.value == "graph")

    ui.select(
        GRID_METHODS,
        value=g.method,
        label="Where the fees read the line loading",
        on_change=method,
    ).classes("w-full")
    capacity = ui.select(
        GRAPH_CAPACITIES,
        value=g.graph_capacity,
        label="Graph model: capacity per line",
        on_change=lambda e: save("graph_capacity", e.value),
    ).classes("w-full")
    total = ui.number(
        "Graph model: total capacity (kW, empty: the line ratings' sum)",
        value=g.graph_total_kw,
        min=0,
        on_change=lambda e: save(
            "graph_total_kw", None if e.value is None else float(e.value)
        ),
    ).classes("w-full")
    capacity.set_enabled(g.method == "graph")
    total.set_enabled(g.method == "graph")
    ui.label(
        "The power flow runs and is recorded with either. With the graph model the "
        "fees read the step's trades along their paths instead."
    ).classes("mls-card-caption")


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

            # Two rows: title | size preset | capacity | power | start SoC, then
            # SoC window | efficiencies | Save
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

            with editor, ui.row().classes("w-full items-end gap-2"):
                numbers = {
                    field: ui.number(
                        label,
                        value=getattr(battery or BatterySetup(0.0), field),
                        min=0,
                        max=1,
                        step=0.01,
                    ).classes("w-36")
                    for field, label in (
                        ("min_soc", "Min SoC (0–1)"),
                        ("max_soc", "Max SoC (0–1)"),
                        ("charge_efficiency", "Charge efficiency"),
                        ("discharge_efficiency", "Discharge efficiency"),
                    )
                }

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
                            initial_soc=float(soc.value or 0.0),
                            max_power_kw=float(power.value) if power.value else None,
                        ) | {k: float(n.value or 0.0) for k, n in numbers.items()}
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
                    "fixed; its other settings can change."
                    if storage is not None
                    else "Size: a SimBench-sized battery (energy = 2 h of its power, "
                    "as every SimBench storage unit), or Custom."
                ).classes("mls-card-caption")

        table.on_select(edit)


# --------------------------------------------------------------------------------------
# Market and DSO: clearing, bidding, reputation, the DSO's tariffs and fees
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


def _numbers(section_name: str, rows: list[list[tuple]]) -> None:
    """Number fields of ``scenario.<section_name>``, each row of ``(field, label,
    step)`` side by side."""
    values = getattr(services().scenario.current(), section_name)
    save = _saver(section_name)

    for row in rows:
        with ui.row().classes("w-full gap-2 no-wrap"):
            for field, label, step in row:
                ui.number(
                    label,
                    value=getattr(values, field),
                    step=step,
                    on_change=lambda e, f=field: (
                        save(f, float(e.value)) if e.value is not None else None
                    ),
                ).classes("grow basis-0")


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

    _numbers(
        "market",
        [
            [("min_price", "Min price", 0.01), ("max_price", "Max price", 0.01)],
            [
                ("min_quantity", "Min quantity (kWh)", 0.1),
                ("max_quantity", "Max quantity (kWh)", 1),
            ],
        ],
    )
    ui.label(
        "Orders are clipped to these bounds, and to what each participant can "
        "physically deliver or take (its surplus or deficit plus its battery)."
    ).classes("mls-card-caption")
    ui.number(
        "Price decimals",
        value=m.price_decimals,
        min=0,
        step=1,
        on_change=lambda e: save("price_decimals", int(e.value or 0)),
    ).classes("w-full")
    ui.label(
        "Order prices are rounded to this, so equal prices occur and reputation can "
        "decide between them (2: whole cents)."
    ).classes("mls-card-caption")
    ui.switch(
        "Preferred partners",
        value=m.partner_preference,
        on_change=lambda e: save("partner_preference", bool(e.value)),
    )
    ui.label(
        "On: under the bidding rule every participant names a partner on the other "
        "side; pairs that name each other trade in stage 1, before the auction. Off: "
        "the rule names none. RL agents choose their partners themselves."
    ).classes("mls-card-caption")
    _numbers(
        "market",
        [[("partner_reputation_weight", "Partner choice: reputation weight", 0.1)]],
    )
    ui.label(
        "How the rule chooses a partner: 0 the nearest, 1 the most reputable."
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
# Reputation
# --------------------------------------------------------------------------------------
def _reputation() -> None:
    _numbers(
        "market",
        [
            [
                ("reliability_weight", "Reliability weight", 0.1),
                ("fairness_weight", "Fairness weight", 0.1),
                ("grid_weight", "Grid weight", 0.1),
            ],
        ],
    )
    ui.label("The three parts of a step's score. They add up to 1.").classes(
        "mls-card-caption"
    )
    _numbers("market", [[("reputation_decay", "Decay per hour", 0.05)]])
    ui.label(
        "The share of the old reputation kept per hour: 0.8 halves it in about 3 "
        "hours. Reputation breaks ties between equal prices in the auction."
    ).classes("mls-card-caption")


# --------------------------------------------------------------------------------------
# Tariffs
# --------------------------------------------------------------------------------------
INLINE_PRICES = "(in the scenario)"


def _tariffs():
    """The price series or the flat tariffs, the chosen series' chart and what is
    wrong with them. Returns the function that shows them again."""
    s = services()
    d = s.scenario.current().dso
    save = _saver("dso")
    choices = {"": "Flat tariffs"} | {f: f for f in s.profiles.price_files()}

    if isinstance(d.prices, dict):
        choices[INLINE_PRICES] = "The series held in the scenario"

    def chosen() -> str:
        return INLINE_PRICES if isinstance(d.prices, dict) else d.prices or ""

    def pick(e) -> None:
        if e.value != INLINE_PRICES:
            s.scenario.current().dso.prices = e.value or None
            s.scenario.save()

        show()

    ui.select(choices, value=chosen(), label="Prices", on_change=pick).classes(
        "w-full"
    )
    ui.label(
        "A price file from config/data/ (one price per market step; Inspect plots "
        "them all), or one flat price all day."
    ).classes("mls-card-caption")

    # Two number fields side by side: feed-in tariff | utility price
    with ui.row().classes("w-full gap-2 no-wrap"):
        feed_in = ui.number(
            "Flat feed-in tariff",
            value=d.feed_in_tariff,
            step=0.01,
            on_change=lambda e: save("feed_in_tariff", float(e.value or 0)),
        ).classes("grow basis-0")
        utility = ui.number(
            "Flat utility price",
            value=d.utility_price,
            step=0.01,
            on_change=lambda e: save("utility_price", float(e.value or 0)),
        ).classes("grow basis-0")

    note = ui.label().classes("mls-card-caption")
    chart_box = ui.column().classes("w-full")

    def show() -> None:
        current = s.scenario.current()
        flat = current.dso.prices is None
        feed_in.set_enabled(flat)
        utility.set_enabled(flat)
        problems = current.dso.problems(current.grid.step_hours)
        note.set_text(
            " ".join(problems)
            if problems
            else "The flat tariffs apply only without a price series. Local trading "
            "pays off between the two: sellers get more than the feed-in tariff, "
            "buyers pay less than the utility price."
        )
        chart_box.clear()

        if isinstance(current.dso.prices, str):
            try:
                with chart_box:
                    PriceChart(
                        220, name=current.dso.prices, read=s.profiles.price_series
                    ).show()
            except (OSError, ValueError, KeyError):
                pass  # ``problems`` said why, in the note above

    show()

    return show


# --------------------------------------------------------------------------------------
# Grid fees
# --------------------------------------------------------------------------------------
def _fees() -> None:
    d = services().scenario.current().dso
    save = _saver("dso")
    ui.switch(
        "Fees are paid",
        value=d.fees_charged,
        on_change=lambda e: save("fees_charged", bool(e.value)),
    )
    ui.label("Off: they are still calculated and recorded.").classes(
        "mls-card-caption"
    )
    _numbers(
        "dso",
        [
            [
                ("fee_buyer_share", "Buyer's share of a fee", 0.1),
                ("loss_factor", "Loss factor (per km)", 0.01),
            ],
            [
                ("congestion_factor", "Congestion factor", 0.05),
                ("congestion_threshold", "Congestion threshold", 0.05),
            ],
            [
                ("voltage_factor", "Voltage factor (per km)", 0.01),
                ("voltage_threshold", "Voltage threshold", 0.01),
            ],
            [
                ("thermal_threshold", "Thermal threshold", 0.05),
                ("thermal_cap", "Thermal cap", 0.05),
            ],
            [
                ("imbalance_factor", "Imbalance factor", 0.05),
                ("zone_factor", "Same-zone bonus", 0.05),
            ],
        ],
    )
    ui.select(
        VOLTAGE_DROPS,
        value=d.voltage_drop,
        label="Voltage drop",
        on_change=lambda e: save("voltage_drop", e.value),
    ).classes("w-full")
    ui.label(
        "The paper gives none of the factors; the defaults are the original code's."
    ).classes("mls-card-caption")
