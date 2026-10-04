"""The dialog that adds or edits one participant (01-simbench-grid.md §3).

A participant is one agent: the bus it sits on, the network elements it owns
(and so replaces), where its demand and generation come from, how they are
scaled, and its battery. The dialog builds the participant's entry of the
experiment file and checks what can be checked here: a unique, file-safe ID, a
bus, no element owned twice, and a feasible battery.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nicegui import ui

from src_thesis.application.models import ElementInfo

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
SOURCE_HINTS = {
    "native": "The owned elements' own SimBench profiles: demand = sum of the owned "
    "loads, generation = sum of the owned generators. Consistent with the network.",
    "catalog": "Any SimBench profile, independent of the network: for the paper's "
    "roles and for networks without profiles. Needs a scaling, or owned elements "
    "whose rated power scales it.",
    "csv": "The original MARLEM data (data/demand, data/generation) or your own "
    "CSV: one column per profile.",
}
SCALING_HINTS = {
    "none": "Keep the values: native profiles in the elements' own kW; catalogue "
    "profiles times the owned elements' rated power.",
    "peak_kw": "The year's highest value becomes the target (kW).",
    "energy_kwh": "The year's total energy becomes the target (kWh per year).",
}


@dataclass
class EditorContext:
    """What the dialog offers to choose from.

    Attributes:
        buses: Bus IDs of the draft's network.
        elements: The network's loads, generators and storage.
        demand_types: Catalogue profiles for demand, code -> label.
        generation_types: Catalogue profiles for generation, code -> label.
        csv_files: Data CSVs, path -> columns.
        owners: Element ID -> the participant that owns it.
        ids: IDs of all participants.
    """

    buses: list[str]
    elements: list[ElementInfo]
    demand_types: dict[str, str]
    generation_types: dict[str, str]
    csv_files: dict[str, list[str]]
    owners: dict[str, str] = field(default_factory=dict)
    ids: set[str] = field(default_factory=set)


def new_participant(n: int) -> dict[str, Any]:
    """An empty participant entry with a free default ID."""
    return {
        "id": f"agent_{n:02d}",
        "role": "",
        "bus": "",
        "owns": {"loads": [], "sgens": []},
        "profile": {"source": "native"},
        "scaling": {"mode": "none"},
        "battery": None,
    }


def edit_participant(
    participant: dict[str, Any],
    ctx: EditorContext,
    on_save: Callable[[dict[str, Any]], None],
    title: str = "Edit participant",
) -> None:
    """Open the dialog for ``participant``; ``on_save`` gets the new entry."""
    p = copy.deepcopy(participant)
    original_id = participant.get("id")
    owns, profile = p.get("owns") or {}, p.get("profile") or {}
    scaling, battery = p.get("scaling") or {}, p.get("battery") or {}

    with ui.dialog() as dialog, ui.card().classes("mls-card w-[56rem] max-w-[95vw]"):
        ui.label(title).classes("mls-card-title")
        with ui.row().classes("w-full no-wrap gap-3"):
            pid = ui.input("ID", value=p.get("id", "")).classes("grow")
            role = ui.input("Role", value=p.get("role", "")).classes("grow")
            bus = ui.select(
                ctx.buses,
                value=p.get("bus") if p.get("bus") in ctx.buses else None,
                label="Bus",
                with_input=True,
            ).classes("grow")
        ui.label(
            "The ID names the agent everywhere (results, run IDs); the order of the "
            "list is the agents' order."
        ).classes("mls-card-caption")

        ui.label("Owned elements").classes("text-weight-medium q-mt-sm")
        with ui.row().classes("w-full no-wrap gap-3"):
            loads = ui.select(
                [], value=list(owns.get("loads", [])), label="Loads", multiple=True
            ).classes("grow basis-0")
            sgens = ui.select(
                [],
                value=list(owns.get("sgens", [])),
                label="Generators",
                multiple=True,
            ).classes("grow basis-0")
            storage = ui.select(
                [], value=list(owns.get("storage", [])), label="Storage", multiple=True
            ).classes("grow basis-0")
        owns_hint = ui.label().classes("mls-card-caption")

        ui.label("Profiles").classes("text-weight-medium q-mt-sm")
        source = ui.toggle(
            {"native": "Own elements", "catalog": "SimBench catalogue", "csv": "CSV"},
            value=profile.get("source", "native"),
        ).props("no-caps dense")
        source_hint = ui.label().classes("mls-card-caption")
        with ui.row().classes("w-full no-wrap gap-3") as catalog_box:
            demand_type = ui.select(
                ctx.demand_types,
                value=_known(
                    (profile.get("demand") or {}).get("type"), ctx.demand_types
                ),
                label="Demand profile",
                with_input=True,
                clearable=True,
            ).classes("grow basis-0")
            generation_type = ui.select(
                ctx.generation_types,
                value=_known(
                    (profile.get("generation") or {}).get("type"), ctx.generation_types
                ),
                label="Generation profile",
                with_input=True,
                clearable=True,
            ).classes("grow basis-0")
        with ui.column().classes("w-full gap-1") as csv_box:
            csv_controls = {
                side: _csv_picker(side, profile.get(side) or {}, ctx.csv_files)
                for side in ("demand", "generation")
            }

        ui.label("Scaling").classes("text-weight-medium q-mt-sm")
        with ui.row().classes("w-full no-wrap gap-3 items-center"):
            mode = ui.toggle(
                {"none": "None", "peak_kw": "Peak kW", "energy_kwh": "Energy kWh/year"},
                value=scaling.get("mode", "none"),
            ).props("no-caps dense")
            demand_target = ui.number(
                "Demand target", value=scaling.get("demand")
            ).classes("grow")
            generation_target = ui.number(
                "Generation target", value=scaling.get("generation")
            ).classes("grow")
        scaling_hint = ui.label().classes("mls-card-caption")

        with ui.row().classes("w-full items-center gap-3 q-mt-sm"):
            ui.label("Battery").classes("text-weight-medium")
            has_battery = ui.switch(value=bool(p.get("battery")))
        with ui.row().classes("w-full no-wrap gap-3") as battery_box:
            capacity = ui.number(
                "Capacity (kWh)", value=battery.get("nominal_capacity_kwh"), min=0
            ).classes("grow")
            soc_min = ui.number(
                "SoC min", value=battery.get("min_soc", 0.0), step=0.05, min=0, max=1
            ).classes("grow")
            soc_max = ui.number(
                "SoC max", value=battery.get("max_soc", 1.0), step=0.05, min=0, max=1
            ).classes("grow")
            eta_in = ui.number(
                "η charge",
                value=battery.get("charge_efficiency", 1.0),
                step=0.01,
                min=0,
                max=1,
            ).classes("grow")
            eta_out = ui.number(
                "η discharge",
                value=battery.get("discharge_efficiency", 1.0),
                step=0.01,
                min=0,
                max=1,
            ).classes("grow")
            max_power = ui.number(
                "Max power (kW)", value=battery.get("max_power_kw"), min=0
            ).classes("grow")
            initial = ui.input(
                "Initial SoC", value=str(battery.get("initial_soc", "random"))
            ).classes("grow")
        battery_hint = ui.label(
            "Empty max power: no limit (I-71). Initial SoC: a number, or 'random' "
            "(uniform between min and max at each reset, as in the original)."
        ).classes("mls-card-caption")

        error = ui.label().classes("text-negative text-body2")
        with ui.row().classes("justify-end w-full gap-2"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            save_button = ui.button("Save to draft", icon="save").props("unelevated")

    def at_bus(kind: str) -> list[str]:
        return [
            e.id for e in ctx.elements if e.element_type == kind and e.bus == bus.value
        ]

    def refresh() -> None:
        """Offer the elements of the chosen bus; show the fields that apply."""
        for control, kind in ((loads, "load"), (sgens, "sgen"), (storage, "storage")):
            options = at_bus(kind)
            control.set_options(
                options, value=[v for v in control.value if v in options]
            )
        taken = [
            f"{e} (owned by {ctx.owners[e]})"
            for e in loads.value + sgens.value + storage.value
            if ctx.owners.get(e, original_id) != original_id
        ]
        owns_hint.set_text(
            "Already owned elsewhere: " + ", ".join(taken)
            if taken
            else "Only elements at the chosen bus are offered. Owned elements are "
            "replaced by the agent; the rest stays as background."
        )
        owns_hint.classes(
            replace="text-negative text-caption" if taken else "mls-card-caption"
        )
        source_hint.set_text(SOURCE_HINTS[source.value])
        catalog_box.set_visibility(source.value == "catalog")
        csv_box.set_visibility(source.value == "csv")
        scaling_hint.set_text(SCALING_HINTS[mode.value])
        unit = "kWh/year" if mode.value == "energy_kwh" else "kW"
        for target, side in (
            (demand_target, "Demand"),
            (generation_target, "Generation"),
        ):
            target.props["label"] = f"{side} target ({unit})"
            target.update()
        for target in (demand_target, generation_target):
            target.set_visibility(mode.value != "none")
        battery_box.set_visibility(has_battery.value)
        battery_hint.set_visibility(has_battery.value)

    def entry() -> dict[str, Any]:
        """The participant as the controls describe it."""
        out = copy.deepcopy(p)
        out.update(id=(pid.value or "").strip(), role=(role.value or "").strip())
        out["bus"] = bus.value or ""
        out["owns"] = {"loads": list(loads.value), "sgens": list(sgens.value)}
        if storage.value:
            out["owns"]["storage"] = list(storage.value)
        new_profile: dict[str, Any] = {"source": source.value}
        if source.value == "catalog":
            for side, control in (
                ("demand", demand_type),
                ("generation", generation_type),
            ):
                if control.value:
                    new_profile[side] = {"type": control.value}
        elif source.value == "csv":
            for side, (path, column) in csv_controls.items():
                if path.value:
                    new_profile[side] = {"path": path.value, "column": column.value}
        out["profile"] = new_profile
        new_scaling: dict[str, Any] = {"mode": mode.value}
        if mode.value != "none":
            for side, control in (
                ("demand", demand_target),
                ("generation", generation_target),
            ):
                if control.value is not None:
                    new_scaling[side] = float(control.value)
        out["scaling"] = new_scaling
        out["battery"] = _battery(
            has_battery.value,
            capacity,
            soc_min,
            soc_max,
            eta_in,
            eta_out,
            max_power,
            initial,
        )
        return out

    def save() -> None:
        """Check the entry; hand it over if it is consistent."""
        try:
            new = entry()
            problem = _problem(new, ctx, original_id)
        except ValueError as e:
            problem = str(e)
        if problem:
            error.set_text(problem)
            return
        dialog.close()
        on_save(new)

    for control in (bus, loads, sgens, storage, source, mode, has_battery):
        control.on_value_change(refresh)
    save_button.on_click(save)
    refresh()
    dialog.open()


def _known(value: str | None, options: dict[str, str]) -> str | None:
    """``value`` if the select offers it, else ``None`` (no stale choice)."""
    return value if value in options else None


def _csv_picker(
    side: str, spec: dict[str, Any], files: dict[str, list[str]]
) -> tuple[ui.select, ui.select]:
    """File and column selects for one side of a CSV profile."""
    with ui.row().classes("w-full no-wrap gap-3"):
        path = ui.select(
            list(files)
            + (
                [spec["path"]]
                if spec.get("path") not in files and spec.get("path")
                else []
            ),
            value=spec.get("path"),
            label=f"{side.capitalize()} CSV",
            clearable=True,
        ).classes("grow basis-0")
        column = ui.select(
            files.get(spec.get("path") or "", []),
            value=spec.get("column"),
            label="Column",
        ).classes("grow basis-0")

    def columns() -> None:
        options = files.get(path.value or "", [])
        column.set_options(
            options, value=column.value if column.value in options else None
        )

    path.on_value_change(columns)
    return path, column


def _battery(
    enabled: bool,
    capacity: ui.number,
    soc_min: ui.number,
    soc_max: ui.number,
    eta_in: ui.number,
    eta_out: ui.number,
    max_power: ui.number,
    initial: ui.input,
) -> dict[str, Any] | None:
    """The battery entry, or ``None`` without a battery."""
    if not enabled:
        return None
    text = (initial.value or "random").strip()
    try:
        initial_soc: float | str = "random" if text == "random" else float(text)
    except ValueError:
        raise ValueError("Initial SoC must be a number or 'random'") from None
    out: dict[str, Any] = {
        "nominal_capacity_kwh": capacity.value,
        "min_soc": soc_min.value,
        "max_soc": soc_max.value,
        "charge_efficiency": eta_in.value,
        "discharge_efficiency": eta_out.value,
    }
    if max_power.value is not None:
        out["max_power_kw"] = max_power.value
    if initial_soc != "random":
        out["initial_soc"] = initial_soc
    return out


def _problem(p: dict[str, Any], ctx: EditorContext, original_id: str | None) -> str:
    """What makes ``p`` unusable, or ``""``."""
    if not SAFE_ID.match(p["id"]) or "__" in p["id"]:
        return "ID: letters, digits, '.', '-' and '_' only (no '__')"
    if p["id"] != original_id and p["id"] in ctx.ids:
        return f"Another participant already has the ID {p['id']!r}"
    if not p["bus"]:
        return "Choose a bus"
    owned = [e for side in p["owns"].values() for e in side]
    taken = [e for e in owned if ctx.owners.get(e, original_id) != original_id]
    if taken:
        return "Owned by another participant: " + ", ".join(taken)
    profile = p["profile"]
    if profile["source"] == "catalog" and not (
        profile.get("demand") or profile.get("generation")
    ):
        return "Choose a demand or a generation profile from the catalogue"
    if profile["source"] == "native" and not owned:
        return "Native profiles come from owned elements: own at least one"
    if p["scaling"]["mode"] != "none" and len(p["scaling"]) == 1:
        return "Give a demand or generation target for the scaling"
    battery = p["battery"]
    if battery:
        if not battery["nominal_capacity_kwh"] or battery["nominal_capacity_kwh"] <= 0:
            return "Battery capacity must be above 0 kWh"
        if not 0 <= battery["min_soc"] < battery["max_soc"] <= 1:
            return "Battery SoC: 0 ≤ min < max ≤ 1"
        for key in ("charge_efficiency", "discharge_efficiency"):
            if not 0 < (battery[key] or 0) <= 1:
                return "Battery efficiencies must be in (0, 1]"
    return ""
