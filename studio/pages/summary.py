"""Summary: the scenario in one look, before the market is run.

Two tabs. Settings: every setting of the Grid & Participants and Market & DSO pages
once, next to the day's curves and the network with its participants. Day profiles:
what every element does on the day, participants apart from the background. Read
only: change things on their own pages.
"""

from __future__ import annotations

from collections import defaultdict

from nicegui import run, ui

from core.config.scenario import Scenario
from core.grid.contract import NetworkRef
from studio.adapters.models import DayProfiles
from studio.components.cards import key_values, placeholder, section
from studio.components.charts import day_figure, topology_figure
from studio.components.day_profiles import show_day_profiles
from studio.components.labels import BACKGROUNDS, MECHANISMS, STEP_LENGTHS
from studio.components.network import busy, failed
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
        "The market as configured: every setting once, the day's curves and the "
        "network. Change settings on their own pages, then run it on Step.",
    ):
        check_box = ui.column().classes("w-full")
        with ui.tabs().classes("w-full").props("align=left no-caps") as tabs:
            settings_tab = ui.tab("Settings", icon="fact_check")
            profiles_tab = ui.tab("Day profiles", icon="show_chart")
        with ui.tab_panels(tabs, value=settings_tab).classes("w-full bg-transparent"):
            with ui.tab_panel(settings_tab).classes("p-0 gap-4"):
                with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
                    with section("Network and day", icon="hub", classes="grow basis-0"):
                        _grid(scenario)
                    with section("Market", icon="gavel", classes="grow basis-0"):
                        _market(scenario)
                    with section("DSO", icon="account_balance", classes="grow basis-0"):
                        _dso(scenario)
                with section("Participants", icon="groups"):
                    _participants(scenario)
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
                        "Rings: the participants",
                        "hub",
                        classes="grow basis-0",
                    ):
                        network_box = ui.column().classes("w-full")
            with ui.tab_panel(profiles_tab).classes("p-0 gap-4"):
                profiles_box = ui.column().classes("w-full gap-4")

    async def load() -> None:
        _checks(check_box, scenario, None)
        if not scenario.participants:
            for box in (day_box, network_box):
                box.clear()
            with profiles_box:
                placeholder(
                    "No participants yet. Place them on the Grid & Participants "
                    "page to see their day.",
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
            ui.plotly(day_figure(day, day.owned())).classes("w-full")
        profiles_box.clear()
        with profiles_box:
            show_day_profiles(day, scenario)
        _checks(check_box, scenario, day)
        try:
            topology = await run.io_bound(
                s.grid.topology, NetworkRef("simbench", scenario.grid.code)
            )
        except Exception as e:  # noqa: BLE001  show the error on the page
            failed(network_box, e)
            return
        network_box.clear()
        with network_box:
            marked = {p.bus for p in scenario.participants}
            ui.plotly(topology_figure(topology, highlight=marked, height=300)).classes(
                "w-full"
            )

    ui.timer(0.05, load, once=True)


# --------------------------------------------------------------------------------------
# Is it ready?
# --------------------------------------------------------------------------------------
def _problems(scenario: Scenario, day: DayProfiles | None) -> list[str]:
    """The scenario's own problems (``Scenario.problems``), with the element types
    of the loaded day when there is one."""
    types = {e.id: e.element_type for e in day.elements} if day else None
    return scenario.problems(types)


def _checks(box: ui.element, scenario: Scenario, day: DayProfiles | None) -> None:
    """The ready banner, or the list of problems, with the way to Step."""
    box.clear()
    problems = _problems(scenario, day)
    with box, ui.row().classes("mls-card w-full items-center gap-3 no-wrap"):
        ui.icon(
            "warning" if problems else "check_circle",
            size="24px",
        ).classes("text-warning" if problems else "text-positive")
        with ui.column().classes("gap-0 grow"):
            if not problems:
                ui.label("Ready to run").classes("text-body1 text-weight-medium")
            for text in problems:
                ui.label(text).classes("text-body2")
        ui.button(
            "Open Step", icon="skip_next", on_click=lambda: ui.navigate.to("/step")
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
        }
    )


def _market(scenario: Scenario) -> None:
    m = scenario.market
    key_values(
        {
            "Peer price": MECHANISMS.get(m.mechanism, m.mechanism),
            "Price bounds": f"{m.min_price:g} – {m.max_price:g} per kWh",
            "Quantity bounds": f"{m.min_quantity:g} – {m.max_quantity:g} kWh",
            "Preferred partners": "on" if m.partner_preference else "off",
            "Bid margin": f"{m.bid_margin:g}",
            "Bid jitter": f"{m.bid_jitter:g}",
            "Seed": m.seed,
            "Ledger difficulty": m.ledger_difficulty or "off",
        }
    )


def _dso(scenario: Scenario) -> None:
    d = scenario.dso
    key_values(
        {
            "Feed-in tariff": f"{d.feed_in_tariff:g} per kWh",
            "Utility price": f"{d.utility_price:g} per kWh",
            "Spread": f"{d.utility_price - d.feed_in_tariff:g} per kWh",
            "Grid fees": "not charged yet",
        }
    )


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
