"""Day profiles: what every element of the network does on the scenario's day.

Shows the participants (they trade in the market) apart from the background
(everything else on the network: it only loads the grid in the power flow). Built
into the Summary page's second tab.
"""

from __future__ import annotations

from nicegui import ui

from core.config.scenario import ParticipantSetup, Scenario
from studio.adapters.models import DayElement, DayProfiles
from studio.components.cards import section, stat, stat_grid
from studio.components.charts import DayChart, ElementsChart
from studio.components.tables import data_table


# --------------------------------------------------------------------------------------
# Content
# --------------------------------------------------------------------------------------
def show_day_profiles(day: DayProfiles, scenario: Scenario) -> None:
    """Totals, then the participants and the background, each with its summed
    curves and a table to pick single curves from."""
    people = scenario.participants
    date = scenario.grid.day
    background_off = scenario.grid.background == "off"
    owned, rest = day.owned(), day.background()
    loads = [e for e in owned if e.element_type == "load"]
    gens = [e for e in owned if e.element_type == "sgen"]
    bg_load = [e for e in rest if e.element_type == "load"]
    bg_gen = [e for e in rest if e.element_type == "sgen"]

    # A row of number tiles, then the Participants and Background cards
    with stat_grid():
        stat(
            "Participants",
            str(len(people)),
            f"{len(owned)} elements taken over",
            "groups",
        )
        stat(
            "Their demand",
            f"{day.kwh(loads):,.0f} kWh",
            f"peak {max(day.total_kw(loads), default=0):.1f} kW",
            "bolt",
            "info",
        )
        stat(
            "Their generation",
            f"{day.kwh(gens):,.0f} kWh",
            f"peak {max(day.total_kw(gens), default=0):.1f} kW",
            "solar_power",
            "warning",
        )
        stat(
            "Background",
            f"{len(rest)} elements",
            (
                "switched off in the power flow"
                if background_off
                else f"{day.kwh(bg_load):,.0f} kWh load, "
                f"{day.kwh(bg_gen):,.0f} kWh generation"
            ),
            "settings_input_component",
            "secondary",
        )

    with section(
        "Participants",
        f"They trade in the market. {date}. Demand and generation per step; "
        "storage follows each participant's battery. Select rows to compare "
        "participants (one row: its demand and generation).",
        "groups",
    ):
        _participants(day, people)

    with section(
        "Background",
        "The elements no participant took over. They do not trade; in the power "
        "flow they follow their profiles"
        + (
            " (switched off here: the Grid & Participants page)."
            if background_off
            else "."
        ),
        "settings_input_component",
    ):
        _background(day, background_off)


def _participants(day: DayProfiles, people: list[ParticipantSetup]) -> None:
    """Summed curves and one table row per participant."""
    rows = []

    for p in people:
        mine = day.owned(p.id)
        loads = [e for e in mine if e.element_type == "load"]
        gens = [e for e in mine if e.element_type == "sgen"]
        demand, gen = day.kwh(loads), day.kwh(gens)
        rows.append(
            {
                "id": p.id,
                "bus": p.bus,
                "profiles": ", ".join(sorted({e.profile_type for e in mine} - {""})),
                "demand": round(demand, 1),
                "generation": round(gen, 1),
                "net": round(gen - demand, 1),
                "peak_demand": round(max(day.total_kw(loads), default=0), 2),
                "peak_generation": round(max(day.total_kw(gens), default=0), 2),
                "battery": f"{p.battery.capacity_kwh:g} kWh" if p.battery else "—",
            }
        )

    plot_box = ui.column().classes("w-full")
    table = data_table(
        rows,
        [
            ("id", "Participant"),
            ("bus", "Bus"),
            ("profiles", "Profiles"),
            ("demand", "Demand (kWh)"),
            ("generation", "Generation (kWh)"),
            ("net", "Net (kWh)"),
            ("peak_demand", "Peak demand (kW)"),
            ("peak_generation", "Peak gen. (kW)"),
            ("battery", "Battery"),
        ],
        pagination=8,
    )
    table.props("selection=multiple")

    def draw(selected: list[str]) -> None:
        plot_box.clear()
        with plot_box:
            if len(selected) == 1:
                DayChart(day=day, elements=day.owned(selected[0])).show()
            elif selected:
                lines = {pid: _net(day, pid) for pid in selected}
                ElementsChart(day=day, lines=lines, y_title="net kW (+ surplus)").show()
            else:
                DayChart(day=day, elements=day.owned()).show()

    table.on_select(lambda e: draw([r["id"] for r in e.selection]))
    draw([])


def _background(day: DayProfiles, off: bool) -> None:
    """Summed curves and one table row per background element."""
    rest = day.background()

    if not rest:
        ui.label("Every element of the network belongs to a participant.").classes(
            "mls-card-caption"
        )
        return

    plot_box = ui.column().classes("w-full")
    rows = [_element_row(day, e) for e in rest]
    table = data_table(
        rows,
        [
            ("id", "Element"),
            ("type", "Type"),
            ("bus", "Bus"),
            ("profile", "Profile"),
            ("energy", "Energy (kWh)"),
            ("peak", "Peak (kW)"),
        ],
        pagination=8,
    )
    table.props("selection=multiple")

    def draw(selected: list[str]) -> None:
        plot_box.clear()
        with plot_box:
            if selected:
                lines = {e.id: e.kw for e in rest if e.id in selected}
                ElementsChart(day=day, lines=lines).show()
            else:
                DayChart(day=day, elements=rest, faint=off).show()

    table.on_select(lambda e: draw([r["id"] for r in e.selection]))
    draw([])


def _element_row(day: DayProfiles, e: DayElement) -> dict:
    return {
        "id": e.id,
        "type": {"load": "load", "sgen": "generator", "storage": "storage"}[
            e.element_type
        ],
        "bus": e.bus,
        "profile": e.profile_type or "—",
        "energy": round(day.kwh([e]), 1),
        "peak": round(max(e.kw, default=0), 2),
    }


def _net(day: DayProfiles, participant: str) -> list[float]:
    """A participant's generation minus its demand per step, in kW."""
    mine = day.owned(participant)
    gen = day.total_kw([e for e in mine if e.element_type == "sgen"])
    dem = day.total_kw([e for e in mine if e.element_type == "load"])

    return [g - d for g, d in zip(gen, dem)]
