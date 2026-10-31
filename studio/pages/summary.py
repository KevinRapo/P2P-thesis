"""Summary: the scenario and the experiment selected, in one look, before they run.

Two tabs. Settings: every setting of the Scenario page once, the experiment selected
on the Experiments page, the day's curves and the network with its participants. Day
profiles: what every element does on the day, participants apart from the background.
Read only: change things on the Scenario and Experiments pages.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from nicegui import run, ui

from core.config.scenario import Scenario, load_prices
from core.grid.contract import NetworkRef
from studio.adapters.models import DayProfiles
from studio.components.cards import (
    busy,
    failed,
    fill,
    key_values,
    placeholder,
    section,
)
from studio.components.charts import DayChart, NetworkChart
from studio.components.day_profiles import show_day_profiles
from studio.components.run_check import experiment_facts
from studio.components.labels import (
    BACKGROUNDS,
    GRAPH_CAPACITIES,
    GRID_METHODS,
    MECHANISMS,
    STEP_LENGTHS,
    VOLTAGE_DROPS,
)
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import services


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """The ready banner on top, then two tabs: the settings with the day and the
    network, and the day profiles."""
    s = services()
    scenario = s.scenario.current()

    with shell(
        "summary",
        "Summary",
        "The scenario and the experiment selected: every setting once, the day's "
        "curves and the network. Change them on the Scenario and Experiments pages, "
        "then play the market on Step or start the experiment.",
    ):
        # Ready banner at the top (filled by _checks)
        check_box = ui.column().classes("w-full")

        # Tab bar: Settings | Day profiles
        with ui.tabs().classes("w-full").props("align=left no-caps") as tabs:
            settings_tab = ui.tab("Settings", icon="fact_check")
            profiles_tab = ui.tab("Day profiles", icon="show_chart")

        # The tabs' contents, one panel per tab
        with ui.tab_panels(tabs, value=settings_tab).classes("w-full bg-transparent"):
            # Settings tab
            with ui.tab_panel(settings_tab).classes("p-0 gap-4"):
                # Row 1: three cards side by side (network, market, DSO)
                with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
                    with section("Network and day", icon="hub", classes="grow basis-0"):
                        _grid(scenario)
                    with section("Market", icon="gavel", classes="grow basis-0"):
                        _market(scenario)
                    with section("DSO", icon="account_balance", classes="grow basis-0"):
                        _dso(scenario)

                # Row 2: the experiment selected, full width
                with section("Experiment", icon="science"):
                    _experiment()

                # Row 3: the participants card, full width
                with section("Participants", icon="groups"):
                    _participants(scenario)

                # Row 4: day curves (left) and network plot (right), filled by load()
                with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
                    with section(
                        "Participants over the day",
                        "Their summed demand and generation per step; every "
                        "curve is in the Day profiles tab",
                        "show_chart",
                        classes="grow basis-0",
                    ):
                        day_box = ui.column().classes("w-full")
                    with section(
                        "Network",
                        "Red rings: the participants",
                        "hub",
                        classes="grow basis-0",
                    ):
                        network_box = ui.column().classes("w-full")

            # Day profiles tab: every element's curve, filled by load()
            with ui.tab_panel(profiles_tab).classes("p-0 gap-4"):
                profiles_box = ui.column().classes("w-full gap-4")

    async def load() -> None:
        _checks(check_box, scenario, None)

        if not scenario.participants:
            for box in (day_box, network_box):
                box.clear()
            with profiles_box:
                placeholder(
                    "No participants yet. Place them on the Scenario page to see "
                    "their day.",
                    "groups",
                )
            return

        for box in (day_box, profiles_box):
            busy(box, "Reading the profiles …")

        busy(network_box, "Building topology …")

        try:
            day = await run.io_bound(s.profiles.day_profiles, scenario)
        except Exception as e:  # noqa: BLE001  show the error on the page
            for box in (day_box, profiles_box, network_box):
                failed(box, e)
            return

        day_box.clear()

        with day_box:
            DayChart(day=day, elements=day.owned()).show()

        profiles_box.clear()

        with profiles_box:
            show_day_profiles(day, scenario)

        _checks(check_box, scenario, day)

        marked = {p.bus: p.id for p in scenario.participants}
        await fill(
            network_box,
            lambda: s.grid.topology(NetworkRef("simbench", scenario.grid.code)),
            lambda topology: NetworkChart(
                300, topology=topology, participants=marked
            ).show(),
            "Building topology …",
        )

    ui.timer(0.05, load, once=True)


# --------------------------------------------------------------------------------------
# Is it ready?
# --------------------------------------------------------------------------------------
def _problems(scenario: Scenario, day: DayProfiles | None) -> list[str]:
    """The scenario's own problems (``Scenario.problems``), with the element types
    of the loaded day when there is one."""
    types = {e.id: e.element_type for e in day.elements} if day else None
    return scenario.problems(types) + _experiment_problems()


def _experiment_problems() -> list[str]:
    """What is wrong with the experiment selected."""
    s = services()
    selected = s.runs.selected(s.scenario.played())

    if selected is None or not selected["error"]:
        return []

    return [f"The experiment cannot start: {selected['error']}"]


def _checks(box: ui.element, scenario: Scenario, day: DayProfiles | None) -> None:
    """The ready banner, or the list of problems, with the way to Step."""
    box.clear()
    problems = _problems(scenario, day)

    # The banner: icon | text (grows) | Open Step button, in one row
    with box, ui.row().classes("mls-card w-full items-center gap-3 no-wrap"):
        ui.icon(
            "warning" if problems else "check_circle",
            size="24px",
        ).classes("text-warning" if problems else "text-positive")

        # Middle: "Ready to run" or one line per problem
        with ui.column().classes("gap-0 grow"):
            if not problems:
                ui.label("Ready to run").classes("text-body1 text-weight-medium")
            for text in problems:
                ui.label(text).classes("text-body2")
        ui.button(
            "Open Experiments",
            icon="science",
            on_click=lambda: ui.navigate.to("/experiments"),
        ).props("outline no-caps")
        ui.button(
            "Open Step", icon="skip_next", on_click=lambda: ui.navigate.to("/market")
        ).props("unelevated no-caps")


# --------------------------------------------------------------------------------------
# Settings, one card each
# --------------------------------------------------------------------------------------
def _grid(scenario: Scenario) -> None:
    g = scenario.grid
    key_values(
        {
            "Network": g.code,
            "Day": g.day,
            "Market step": STEP_LENGTHS.get(g.step_hours, f"{g.step_hours} h"),
            "Rest of the network": BACKGROUNDS.get(g.background, g.background),
            "Voltage limits": f"{g.v_min_pu:g} – {g.v_max_pu:g} pu",
            "Line limit": f"{g.line_max_percent:g} %",
            "Line loading for the fees": GRID_METHODS.get(g.method, g.method),
            **(
                {
                    "Graph capacity": GRAPH_CAPACITIES.get(
                        g.graph_capacity, g.graph_capacity
                    ),
                    "Graph total": (
                        f"{g.graph_total_kw:g} kW"
                        if g.graph_total_kw is not None
                        else "the line ratings' sum"
                    ),
                }
                if g.method == "graph"
                else {}
            ),
        }
    )


def _market(scenario: Scenario) -> None:
    m = scenario.market
    key_values(
        {
            "Peer price": MECHANISMS.get(m.mechanism, m.mechanism),
            "Price bounds": f"{m.min_price:g} – {m.max_price:g} per kWh",
            "Quantity bounds": f"{m.min_quantity:g} – {m.max_quantity:g} kWh",
            "Price decimals": m.price_decimals,
            "Preferred partners": "on" if m.partner_preference else "off",
            "Partner: reputation weight": f"{m.partner_reputation_weight:g}",
            "Bid margin": f"{m.bid_margin:g}",
            "Bid jitter": f"{m.bid_jitter:g}",
            "Seed": m.seed,
            "Reputation weights": (
                f"{m.reliability_weight:g} / {m.fairness_weight:g} / "
                f"{m.grid_weight:g}"
            ),
            "Reputation decay": f"{m.reputation_decay:g} per hour",
        }
    )


def _dso(scenario: Scenario) -> None:
    d = scenario.dso
    key_values(
        _tariffs(scenario)
        | {
            "Grid fees": "paid" if d.fees_charged else "recorded, not paid",
            "Buyer's share of a fee": f"{d.fee_buyer_share:g}",
            "Loss factor": f"{d.loss_factor:g} per km",
            "Congestion": f"{d.congestion_factor:g} over {d.congestion_threshold:g}",
            "Voltage": f"{d.voltage_factor:g} per km, over {d.voltage_threshold:g}",
            "Voltage drop": VOLTAGE_DROPS.get(d.voltage_drop, d.voltage_drop),
            "Thermal": f"over {d.thermal_threshold:g}, capped at {d.thermal_cap:g}",
            "Imbalance factor": f"{d.imbalance_factor:g}",
            "Same-zone bonus": f"{d.zone_factor:g}",
        }
    )


def _tariffs(scenario: Scenario) -> dict:
    """The tariffs the market really uses: the series' range, or the flat prices."""
    d = scenario.dso

    if d.prices is None:
        return {
            "Prices": "flat",
            "Feed-in tariff": f"{d.feed_in_tariff:g} per kWh",
            "Utility price": f"{d.utility_price:g} per kWh",
        }

    name = d.prices if isinstance(d.prices, str) else "in the scenario"

    try:
        prices = load_prices(d.prices, scenario.grid.step_hours)
    except (OSError, ValueError, KeyError):
        return {"Prices": f"{name} (does not fit, see the checks above)"}

    feed_in, utility = prices["feed_in"], prices["utility"]

    return {
        "Prices": name,
        "Feed-in tariff": f"{min(feed_in):g} – {max(feed_in):g} per kWh",
        "Utility price": f"{min(utility):g} – {max(utility):g} per kWh",
    }


# --------------------------------------------------------------------------------------
# The experiment selected
# --------------------------------------------------------------------------------------
def _experiment() -> None:
    s = services()
    selected = s.runs.selected(s.scenario.played())

    if selected is None:
        ui.label("None selected yet: choose one on the Experiments page.").classes(
            "mls-card-caption"
        )
        return

    if selected["error"]:
        ui.label(selected["error"]).classes("text-body2 text-negative")
        return

    e = selected["experiment"]
    key_values(
        experiment_facts(selected)
        | {
            "Template": Path(selected["template"] or "none").stem,
            "Scenario": (
                f"the active one, {s.scenario.shown_name()}"
                + (" (unsaved)" if s.scenario.unsaved() else "")
                if selected["active"]
                else "the one in the experiment"
            ),
            "Paradigms": ", ".join(e.paradigms),
            "Seeds": ", ".join(str(seed) for seed in e.seeds),
            "Arms": ", ".join(e.variants) or "one",
            "Training days": _days(e.train_days),
            "Test periods": ", ".join(
                f"{name} ({_days(days)})" for name, days in e.test_periods.items()
            )
            or "none",
            "Evaluations during training": e.eval_points or "only at the end",
        }
    )


def _days(days: list[str]) -> str:
    """How many days, and from when to when."""
    if not days:
        return "none"

    return f"{len(days)} days, {days[0]} to {days[-1]}"


# --------------------------------------------------------------------------------------
# Participants
# --------------------------------------------------------------------------------------
def _participants(scenario: Scenario) -> None:
    """Counts, the battery types grouped, and the full list on demand."""
    people = scenario.participants

    if not people:
        ui.label("None placed yet.").classes("mls-card-caption")
        return

    batteries = [p for p in people if p.battery]
    key_values(
        {
            "Participants": len(people),
            "Elements taken over": sum(len(p.owns) for p in people),
            "With a battery": f"{len(batteries)} of {len(people)}",
            "Battery capacity": f"{sum(p.battery.capacity_kwh for p in batteries):g} kWh",
        }
    )
    groups: dict[tuple, list[str]] = defaultdict(list)

    for p in batteries:
        b = p.battery
        groups[
            (
                b.capacity_kwh,
                b.initial_soc,
                b.min_soc,
                b.max_soc,
                b.charge_efficiency,
                b.discharge_efficiency,
                b.max_power_kw,
            )
        ].append(p.id)

    if groups:
        rows = [
            {
                "id": i,
                "capacity": f"{c:g} kWh",
                "soc": f"start {init:g}, window {lo:g} – {hi:g}",
                "eff": f"{ci:g} in, {di:g} out",
                "power": f"{pw:g} kW" if pw else "no limit",
                "who": f"{len(ids)}: " + ", ".join(ids),
            }
            for i, ((c, init, lo, hi, ci, di, pw), ids) in enumerate(groups.items())
        ]
        data_table(
            rows,
            [
                ("capacity", "Battery"),
                ("soc", "State of charge"),
                ("eff", "Efficiency"),
                ("power", "Max power"),
                ("who", "Participants"),
            ],
            pagination=5,
        )

    # Collapsible list under the card: one row per participant
    with ui.expansion("All participants", icon="list").classes("w-full"):
        data_table(
            [
                {
                    "id": p.id,
                    "bus": p.bus,
                    "elements": len(p.owns),
                    "battery": f"{p.battery.capacity_kwh:g} kWh" if p.battery else "—",
                }
                for p in people
            ],
            [
                ("id", "Participant"),
                ("bus", "Bus"),
                ("elements", "Elements"),
                ("battery", "Battery"),
            ],
            pagination=10,
        )
