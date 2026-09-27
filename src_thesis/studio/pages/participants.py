"""Participants (04 §4.3): agents, placement, profiles, batteries, time window."""

from nicegui import ui

from src_thesis.application.models import NetworkSource

from ..components import (
    data_table,
    line_figure,
    not_implemented,
    section,
    topology_figure,
)
from ..layout import shell
from ..state import current_draft, services


@ui.page("/build/participants")
def participants_page() -> None:
    s = services()
    draft = current_draft()
    source = NetworkSource(
        **draft.grid.get("source", {"type": "simbench", "code": "1-LV-semiurb4--0-sw"})
    )
    with shell(
        "participants",
        "Participants",
        "Tie each agent to a bus, owned elements, profiles and a battery",
    ):
        with section("Assignment tools", icon="auto_fix_high"):
            with ui.row().classes("gap-2"):
                ui.button(
                    "Add participant",
                    icon="person_add",
                    on_click=lambda: not_implemented("Add participant"),
                ).props("unelevated")
                ui.button(
                    "Apply placement rule",
                    icon="rule",
                    on_click=lambda: rule_dialog.open(),
                ).props("outline")
                ui.button(
                    "Import mapping",
                    icon="upload_file",
                    on_click=lambda: not_implemented("Import mapping"),
                ).props("outline")
                ui.button(
                    "Load [P2] Table 6 roles",
                    icon="menu_book",
                    on_click=lambda: not_implemented("Load Table 6 roles"),
                ).props("outline")

        rows = []
        for p in draft.participants:
            battery = p.get("battery")
            rows.append(
                {
                    "id": p["id"],
                    "role": p.get("role", ""),
                    "bus": p.get("bus", ""),
                    "owns": ", ".join(
                        p.get("owns", {}).get("loads", [])
                        + p.get("owns", {}).get("sgens", [])
                    ),
                    "profile": f"{p['profile'].get('source')}: {p['profile'].get('demand', {}).get('type', '')}"
                    f" / {p['profile'].get('generation', {}).get('type', '')}",
                    "peak_kw": p.get("scaling", {}).get("generation", ""),
                    "battery": (
                        f"{battery['nominal_capacity_kwh']} kWh" if battery else "—"
                    ),
                }
            )
        selected = {"id": rows[0]["id"] if rows else None}

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Participants",
                f"{len(rows)} agents in the draft",
                "groups",
                classes="grow basis-0",
            ):
                table = data_table(
                    rows,
                    [
                        ("id", "ID"),
                        ("bus", "Bus"),
                        ("owns", "Owns"),
                        ("profile", "Profile"),
                        ("peak_kw", "Peak kW"),
                        ("battery", "Battery"),
                    ],
                    pagination=10,
                )
                table.props("selection=single")
            with section(
                "Map",
                "Participant buses highlighted",
                "map",
                classes="basis-2/5 min-w-0",
            ):
                topo = s.grid.topology(source)
                highlight = {b["id"] for i, b in enumerate(topo.buses) if i % 5 == 1}
                ui.plotly(
                    topology_figure(topo, highlight=highlight, height=360)
                ).classes("w-full")

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Profile preview",
                "Selected agent over the time window",
                "show_chart",
                classes="grow basis-0",
            ):
                chart_box = ui.column().classes("w-full")
            with section(
                "Time window",
                "Written to the draft's time section",
                "event",
                classes="basis-1/4 min-w-0",
            ):
                t = draft.time
                ui.toggle(
                    {"hourly_aggregated": "Hourly", "native_15min": "15 min"},
                    value=t.get("resolution", "hourly_aggregated"),
                ).props("no-caps dense")
                ui.select(
                    ["fixed", "range", "sampler"],
                    value=t.get("days", {}).get("mode", "sampler"),
                    label="Day mode",
                ).classes("w-full")
                with ui.row().classes("w-full no-wrap gap-2"):
                    ui.input("Start", value=t.get("days", {}).get("start", "")).classes(
                        "grow"
                    )
                    ui.input("End", value=t.get("days", {}).get("end", "")).classes(
                        "grow"
                    )
                ui.number(
                    "Evaluation hold-out",
                    value=t.get("days", {}).get("eval_holdout", 0.2),
                    step=0.05,
                ).classes("w-full")
                days = s.profiles.days(draft)
                ui.label(
                    f"{len(days['train'])} training days · {len(days['eval'])} evaluation days"
                ).classes("mls-card-caption")
            with section(
                "Battery",
                "Selected agent",
                "battery_charging_full",
                classes="basis-1/4 min-w-0",
            ):
                battery_box = ui.column().classes("w-full gap-1")

        def show(participant_id: str | None) -> None:
            if participant_id is None:
                return
            chart_box.clear()
            with chart_box:
                ui.plotly(
                    line_figure(s.profiles.preview(draft, participant_id), height=280)
                ).classes("w-full")
            battery_box.clear()
            battery = next(
                (
                    p.get("battery")
                    for p in draft.participants
                    if p["id"] == participant_id
                ),
                None,
            )
            with battery_box:
                if not battery:
                    ui.label("No battery").classes("mls-card-caption")
                    ui.button(
                        "Add battery",
                        icon="add",
                        on_click=lambda: not_implemented("Add battery"),
                    ).props("flat")
                    return
                ui.number(
                    "Capacity (kWh)", value=battery["nominal_capacity_kwh"]
                ).classes("w-full")
                with ui.row().classes("no-wrap gap-2 w-full"):
                    ui.number("SoC min", value=battery["min_soc"], step=0.05).classes(
                        "grow"
                    )
                    ui.number("SoC max", value=battery["max_soc"], step=0.05).classes(
                        "grow"
                    )
                with ui.row().classes("no-wrap gap-2 w-full"):
                    ui.number(
                        "η charge", value=battery["charge_efficiency"], step=0.01
                    ).classes("grow")
                    ui.number(
                        "η discharge", value=battery["discharge_efficiency"], step=0.01
                    ).classes("grow")
                ui.number("Max power (kW)", value=battery.get("max_power_kw")).classes(
                    "w-full"
                )

        table.on("rowClick", lambda e: show(e.args[1]["id"]))
        show(selected["id"])

        with ui.dialog() as rule_dialog, ui.card().classes("mls-card").style(
            "min-width: 380px"
        ):
            ui.label("Placement rule").classes("mls-card-title")
            ui.select(
                {
                    "household_with_pv": "N household buses with PV",
                    "feeder_ends": "Feeder ends",
                    "spread": "Spread across feeders",
                },
                value="household_with_pv",
                label="Rule",
            ).classes("w-full")
            ui.number("Number of agents", value=8).classes("w-full")
            ui.number("Seed", value=1).classes("w-full")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=rule_dialog.close).props("flat")
                ui.button(
                    "Apply",
                    on_click=lambda: (
                        rule_dialog.close(),
                        not_implemented("Apply rule"),
                    ),
                ).props("unelevated")
