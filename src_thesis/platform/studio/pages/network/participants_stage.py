"""Stage 2 of the network page: the agents, where they sit, what drives them; the
time window.

Writes the draft's ``participants`` list and ``time`` section (01 §3, 02 §3.2 and
§3.4). Participants are added and edited one at a time in a dialog, placed in
bulk by a rule, imported from a mapping file or given the [P2] Table 6 roles;
every such action saves the whole list at once. The time window has its own
"Apply" and shows how many training and evaluation days it selects.

They are drawn on the page's shared plot (``view.py``): rings for participant
buses, squares for flexible ones, a filled mark for the selected participant. The
participants belong to the network saved in the draft, so every action waits until
the network picked in stage 1 has been applied.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from nicegui import events, run, ui

from src_thesis.platform.services.models import ExperimentFile
from src_thesis.platform.studio.components.cards import section
from src_thesis.platform.studio.components.charts import line_figure
from src_thesis.platform.studio.components.network import busy, failed
from src_thesis.platform.studio.components.participant_editor import (
    EditorContext,
    edit_participant,
    new_participant,
)
from src_thesis.platform.studio.forms import DraftForm, date_input, save_changes
from src_thesis.platform.studio.state import services

if TYPE_CHECKING:
    from src_thesis.platform.studio.pages.network.page import Context

DAY_MODE_HINTS = {
    "fixed": "One day, every episode (the papers' setting).",
    "range": "Every day between start and end, in order.",
    "sampler": "Days drawn from the range that pass the filter; a share is held "
    "out for evaluation and never trained on.",
}
MONTHS = {
    i + 1: m
    for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())
}
COLUMNS = [
    ("id", "ID"),
    ("role", "Role"),
    ("bus", "Bus"),
    ("owns", "Owns"),
    ("profile", "Profiles"),
    ("scaling", "Scaling"),
    ("battery", "Battery"),
    ("check", "Check"),
]


def build_participants_stage(ctx: Context, side: ui.element, below: ui.element) -> None:
    """Build stage 2: the assignment tools beside the plot, the participant table,
    profile preview and time window below it.

    Args:
        ctx: What the stages share (services, draft, the plot).
        side: Slot beside the plot.
        below: Slot below it.
    """
    s, draft, view, source = ctx.s, ctx.draft, ctx.view, ctx.draft_source
    # The participants as editable data (what the dialog and the tools change);
    # every save goes through the typed file, which rejects unknown fields.
    members = [
        p.model_dump(mode="json", exclude_unset=True) for p in draft.participants
    ]
    # Network data for the checks and the editor, taken from the shared view once
    # it has loaded.
    net: dict[str, Any] = {
        "topology": None,
        "elements": [],
        "buses": [],
        "candidates": [],  # flexible buses: a generator or storage
    }
    selected: dict[str, str | None] = {"id": members[0]["id"] if members else None}
    catalogue: dict[str, Any] = {"demand": {}, "generation": {}, "csv": {}}

    def saved() -> bool:
        """Whether the network shown is the draft's; only then can participants be
        edited."""
        if ctx.picked() == source:
            return True
        ui.notify(
            "Apply the network in stage 1 first: participants belong to the "
            "network saved in the draft.",
            type="warning",
        )
        return False

    def save(participants: list[dict]) -> None:
        """Write the whole participant list to the draft and reload."""
        if saved():
            save_changes(draft, {"participants": participants})

    with side:
        gate = ui.label().classes("text-warning text-body2")
        with section(
            "Assignment tools",
            f"Network {source.code}. Every action saves the participant list to "
            "the draft.",
            "auto_fix_high",
        ):
            with ui.row().classes("gap-2"):
                ui.button(
                    "Add participant", icon="person_add", on_click=lambda: add()
                ).props("unelevated")
                ui.button(
                    "Import mapping",
                    icon="upload_file",
                    on_click=lambda: import_dialog(),
                ).props("outline")
                ui.button(
                    "Apply [P2] Table 6 roles",
                    icon="menu_book",
                    on_click=lambda: roles_dialog(),
                ).props("outline")
                ui.button(
                    "Remove all",
                    icon="delete_sweep",
                    on_click=lambda: confirm(
                        "Remove all participants?",
                        "The draft keeps its other settings; place or add new "
                        "participants afterwards.",
                        lambda: save([]),
                    ),
                ).props("flat color=negative")

        with section(
            "Flexible buses",
            "A bus with a generator or storage can be a participant; a bus with "
            "only regular load stays background",
            "bolt",
        ):
            rule_hint = ui.label("Loading the network …").classes("mls-card-caption")
            rule_replace = (
                ui.toggle(
                    {True: "Replace all participants", False: "Add to them"},
                    value=True,
                )
                .props("no-caps dense no-wrap")
                .classes("shrink-0")
            )
            rule_apply = ui.button(
                "Make flexible buses participants",
                icon="bolt",
                on_click=lambda: place(),
            ).props("unelevated")
            rule_apply.set_enabled(False)

    with below:
        with section(
            "Participants",
            f"{len(members)} agents; their order is the agents' order everywhere. "
            "Click a row, or a ringed bus on the plot, to select one.",
            "groups",
        ):
            table = (
                ui.table(
                    columns=[
                        {"name": f, "label": label, "field": f, "align": "left"}
                        for f, label in COLUMNS
                    ],
                    rows=_rows(members, None),
                    row_key="id",
                    pagination=10,
                )
                .classes("w-full")
                .props("flat dense")
            )
            table.add_slot(
                "body-cell-check",
                '<q-td :props="props"><span :class="props.value ? '
                "'text-negative' : 'text-positive'\">"
                "{{ props.value || 'ok' }}</span></q-td>",
            )
            with ui.row().classes("gap-1"):
                for icon, tip, action in (
                    ("edit", "Edit", lambda: edit()),
                    ("content_copy", "Duplicate", lambda: duplicate()),
                    ("arrow_upward", "Move up", lambda: move(-1)),
                    ("arrow_downward", "Move down", lambda: move(1)),
                    ("delete", "Remove", lambda: remove()),
                ):
                    ui.button(icon=icon, on_click=action).props(
                        "flat dense round"
                    ).tooltip(f"{tip} the selected participant")
                selected_label = ui.label().classes("mls-card-caption self-center")

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Profile preview",
                "Selected agent, scaled, for a week from the start of the time window",
                "show_chart",
                classes="grow basis-0 min-w-0",
            ):
                preview_box = ui.column().classes("w-full")
            _time_window(draft)

        with ui.row().classes("justify-start w-full"):
            ui.button(
                "Back: grid",
                icon="arrow_back",
                on_click=lambda: ctx.switch("grid"),
            ).props("outline")

    # ------------------------------------------------------------ handlers
    def refresh_gate(stage: str) -> None:
        """Warn when the plot shows a network the draft does not use yet."""
        gate.set_text(
            ""
            if ctx.picked() == source
            else f"The network picked in stage 1 is not saved yet; the draft uses "
            f"{source.code}. Apply it in stage 1 before editing participants."
        )

    ctx.hooks.append(refresh_gate)

    def by_id(pid: str | None) -> dict | None:
        return next((p for p in members if p["id"] == pid), None)

    def context(exclude: str | None = None) -> EditorContext:
        """What the editor may offer: the network, the profiles, the owners."""
        owners = {
            e: p["id"]
            for p in members
            if p["id"] != exclude
            for side_ in (p.get("owns") or {}).values()
            for e in side_
        }
        return EditorContext(
            buses=net["buses"],
            elements=net["elements"],
            demand_types=catalogue["demand"],
            generation_types=catalogue["generation"],
            csv_files=catalogue["csv"],
            owners=owners,
            ids={p["id"] for p in members},
        )

    def ready() -> bool:
        if not saved():
            return False
        if net["topology"] is None:
            ui.notify("The network is still loading")
            return False
        return True

    def add() -> None:
        if ready():
            edit_participant(
                new_participant(_free_number(members)),
                context(),
                lambda p: save(members + [p]),
                title="Add participant",
            )

    def edit() -> None:
        p = by_id(selected["id"])
        if p is None:
            ui.notify("Select a participant first")
        elif ready():
            edit_participant(
                p,
                context(exclude=p["id"]),
                lambda new: save([new if x["id"] == p["id"] else x for x in members]),
            )

    def duplicate() -> None:
        p = by_id(selected["id"])
        if p is None:
            ui.notify("Select a participant first")
        elif ready():
            copy_ = copy.deepcopy(p)
            copy_["id"] = f"{p['id']}_copy"
            copy_["owns"] = {"loads": [], "sgens": []}
            edit_participant(
                copy_,
                context(),
                lambda new: save(members + [new]),
                title="Duplicate participant (choose its own elements)",
            )

    def move(step: int) -> None:
        ids = [p["id"] for p in members]
        if selected["id"] not in ids:
            ui.notify("Select a participant first")
            return
        i = ids.index(selected["id"])
        j = i + step
        if 0 <= j < len(ids):
            order = list(members)
            order[i], order[j] = order[j], order[i]
            save(order)

    def remove() -> None:
        p = by_id(selected["id"])
        if p is None:
            ui.notify("Select a participant first")
            return
        confirm(
            f"Remove {p['id']}?",
            "Its owned elements go back to the background.",
            lambda: save([x for x in members if x["id"] != p["id"]]),
        )

    async def explain_rule() -> None:
        """Count the flexible buses and mark them on the plot."""
        if net["topology"] is None:
            return
        try:
            found = await run.io_bound(s.participants.placement_candidates, source)
        except ValueError as e:
            rule_hint.set_text(str(e))
            return
        net["candidates"] = found
        flexible = set(found)
        load_only = {
            e.bus
            for e in net["elements"]
            if e.element_type == "load" and e.bus not in flexible
        }
        rule_hint.set_text(
            f"{len(found)} flexible buses (a generator or storage), each becoming a "
            "participant that owns everything at its bus, with the elements' own "
            f"SimBench profiles. The {len(load_only)} other buses with load stay "
            "background."
            if found
            else "This network has no generator or storage: nothing can be a "
            "participant yet. Add one by hand, or choose another network."
        )
        rule_apply.set_enabled(bool(found))
        sync_plot()

    async def place() -> None:
        """Make the flexible buses participants and save them."""
        if not saved():
            return
        try:
            placed = await run.io_bound(s.participants.suggest_mapping, source)
        except Exception as e:  # noqa: BLE001  shown under the controls
            rule_hint.set_text(str(e))
            return
        if not rule_replace.value:
            placed = _merge(members, placed)
        save(placed)

    def import_dialog() -> None:
        if not saved():
            return
        with ui.dialog() as dialog, ui.card().classes("mls-card w-[38rem]"):
            ui.label("Import a participant mapping").classes("mls-card-title")
            ui.label(
                "JSON: a participant list in the experiment file's format (or an "
                "object with 'participants'). CSV: columns id, role, bus, loads, "
                "sgens, profile_source, demand, generation, scaling_mode, "
                "demand_target, generation_target, battery_kwh; lists separated by "
                "';'. The import replaces the current participants."
            ).classes("mls-card-caption")
            message = ui.label().classes("text-negative text-body2")

            async def received(e: events.UploadEventArguments) -> None:
                try:
                    rows = s.participants.import_mapping(
                        await e.file.read(), e.file.name
                    )
                except (ValueError, UnicodeDecodeError) as error:
                    message.set_text(str(error))
                    return
                dialog.close()
                save(rows)

            ui.upload(on_upload=received, auto_upload=True).props(
                'accept=".json,.csv"'
            ).classes("w-full")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
        dialog.open()

    def roles_dialog() -> None:
        def apply() -> None:
            try:
                save(s.participants.paper_roles(draft.participants))
            except ValueError as e:
                ui.notify(str(e), type="warning")

        confirm(
            "Apply the [P2] Table 6 roles?",
            "The first eight participants become small industry, community hospital, "
            "university campus, shopping mall, residential complex, apartment "
            "building, community solar farm and parking lot: ID and role, capacity "
            "(as peak kW), battery (95 % efficiency, SoC 5–95 %) and catalogue "
            "profiles. Buses and owned elements stay. The profile types are a "
            "reconstruction: the paper does not publish its mapping (I-51).",
            apply,
        )

    def show_selected() -> None:
        """Mark the selected row, redraw the plot and the preview."""
        table.rows = _rows(members, net)
        table.selected = [r for r in table.rows if r["id"] == selected["id"]]
        table.update()
        selected_label.set_text(
            f"Selected: {selected['id']}" if selected["id"] else "No selection"
        )
        sync_plot()

    def sync_plot() -> None:
        """Give the shared plot the participants, flexible buses and selection."""
        view.participants = {p["id"]: p["bus"] for p in members if p.get("bus")}
        view.flexible = net.get("candidates", [])
        view.selected = selected["id"]
        view.redraw()

    async def preview() -> None:
        if not selected["id"]:
            preview_box.clear()
            with preview_box:
                ui.label("Add or place participants to preview them.").classes(
                    "mls-card-caption"
                )
            return
        busy(preview_box, "Reading profiles …")
        try:
            series = await run.io_bound(s.participants.preview, draft, selected["id"])
        except Exception as e:  # noqa: BLE001
            failed(preview_box, e)
            return
        preview_box.clear()
        with preview_box:
            if not series.y:
                ui.label("This participant has no demand or generation.").classes(
                    "mls-card-caption"
                )
                return
            ui.plotly(line_figure(series, height=300)).classes("w-full")

    async def select_id(pid: str) -> None:
        selected["id"] = pid
        show_selected()
        await preview()

    async def select(e: Any) -> None:
        await select_id(e.args[1]["id"])

    async def on_bus_click(bus: str) -> None:
        """A bus was clicked on the plot: select the participant that sits there."""
        owner = next((p for p in members if p.get("bus") == bus), None)
        if owner is None:
            ui.notify(f"No participant on bus {bus}")
        else:
            await select_id(owner["id"])

    view.handlers["participants"] = on_bus_click

    async def on_loaded() -> None:
        """The shared view loaded a network: take its data and show what fits."""
        net.update(
            topology=view.topology,
            elements=view.elements,
            buses=view.buses,
            candidates=[],
        )
        if view.source != source:  # a network the draft does not use yet
            sync_plot()
            return
        try:
            types = await run.io_bound(s.profiles.catalogue_types)
        except Exception as e:  # noqa: BLE001
            rule_hint.set_text(f"Profile catalogue not available: {e}")
            return
        catalogue["demand"] = {
            t.code: f"{t.code} · {t.description or t.category}"
            for t in types
            if t.table == "load"
        }
        catalogue["generation"] = {
            t.code: f"{t.code} · {t.description or t.category}"
            for t in types
            if t.table == "renewables"
        }
        catalogue["csv"] = {
            **s.profiles.data_files("data/demand"),
            **s.profiles.data_files("data/generation"),
        }
        await explain_rule()
        show_selected()
        await preview()

    view.on_loaded.append(on_loaded)

    def confirm(title: str, text: str, action: Any) -> None:
        with ui.dialog() as dialog, ui.card().classes("mls-card max-w-[34rem]"):
            ui.label(title).classes("mls-card-title")
            ui.label(text).classes("text-body2")
            with ui.row().classes("justify-end w-full"):
                ui.button("Cancel", on_click=dialog.close).props("flat")
                ui.button("Confirm", on_click=lambda: (dialog.close(), action())).props(
                    "unelevated"
                )
        dialog.open()

    table.on("rowClick", select)
    selected_label.set_text(
        f"Selected: {selected['id']}" if selected["id"] else "No selection"
    )


def _time_window(draft: ExperimentFile) -> None:
    """The ``time`` section: resolution, horizon and which days; with its own
    Apply and a live count of the training and evaluation days.
    """
    s = services()
    time = s.config.resolve(draft).to_data()["time"]
    days = time.get("days", {})
    flt = days.get("filter") or {}
    form = DraftForm(draft)
    bind = form.bind
    with section(
        "Time window",
        "Written to the draft's time section (02 §3.2)",
        "event",
        classes="basis-2/5 min-w-0",
    ):
        with ui.row().classes("w-full no-wrap gap-2 items-center"):
            bind(
                "time.resolution",
                ui.toggle(
                    {"hourly_aggregated": "Hourly", "native_15min": "15 min"},
                    value=time.get("resolution", "hourly_aggregated"),
                ).props("no-caps dense"),
            )
            bind(
                "time.horizon_steps",
                ui.number(
                    "Steps per episode", value=time.get("horizon_steps", 24), min=1
                ).classes("grow"),
                int,
            )
        ui.label(
            "Hourly: 24 steps make a day (the papers); 15 min: 96 steps make a day."
        ).classes("mls-card-caption")
        mode = bind(
            "time.days.mode",
            ui.select(
                {"fixed": "One fixed day", "range": "Date range", "sampler": "Sampler"},
                value=days.get("mode", "fixed"),
                label="Days",
            ).classes("w-full"),
        )
        mode_hint = ui.label().classes("mls-card-caption")
        fixed = bind("time.days.date", date_input("Date", days.get("date")))
        fixed.classes("w-full")
        with ui.row().classes("w-full no-wrap gap-2") as span:
            bind("time.days.start", date_input("Start", days.get("start"))).classes(
                "grow"
            )
            bind("time.days.end", date_input("End", days.get("end"))).classes("grow")
        with ui.row().classes("w-full no-wrap gap-2") as filters:
            day_type = ui.select(
                {"": "Any day", "workday": "Workdays", "weekend": "Weekends"},
                value=flt.get("day_type", ""),
                label="Day type",
            ).classes("grow")
            season = ui.select(
                {
                    "": "Any season",
                    "winter": "Winter",
                    "spring": "Spring",
                    "summer": "Summer",
                    "autumn": "Autumn",
                },
                value=flt.get("season", ""),
                label="Season",
            ).classes("grow")
            months = ui.select(
                MONTHS, value=list(flt.get("months", [])), label="Months", multiple=True
            ).classes("grow")
        form.track(
            "time.days.filter",
            lambda: {
                k: v
                for k, v in (
                    ("day_type", day_type.value),
                    ("season", season.value),
                    ("months", sorted(months.value or [])),
                )
                if v
            },
        )
        with ui.row().classes("w-full no-wrap gap-2"):
            bind(
                "time.days.eval_holdout",
                ui.number(
                    "Held out for evaluation",
                    value=days.get("eval_holdout", 0.2),
                    step=0.05,
                    min=0,
                    max=0.9,
                ).classes("grow"),
                float,
            )
            bind(
                "time.days.seed",
                ui.number("Split seed", value=days.get("seed", 42), step=1).classes(
                    "grow"
                ),
                int,
            )
        count = ui.label().classes("text-body2")
        with ui.row().classes("justify-end w-full"):
            ui.button("Apply to draft", icon="save", on_click=form.apply).props(
                "unelevated"
            )

    def refresh() -> None:
        """Show the fields of the chosen mode and count the days it selects."""
        mode_hint.set_text(DAY_MODE_HINTS.get(mode.value, ""))
        fixed.set_visibility(mode.value == "fixed")
        span.set_visibility(mode.value != "fixed")
        filters.set_visibility(mode.value == "sampler")
        try:
            preview_file = s.config.update(draft, form.changes())
            split = s.config.days(preview_file)
        except (ValueError, KeyError) as e:
            count.set_text(f"Selects no days yet: {e}")
            count.classes(replace="text-negative text-body2")
            return
        count.set_text(
            f"{len(split['train'])} training days · {len(split['eval'])} evaluation "
            "days" + ("" if form.changes() else " (as saved)")
        )
        count.classes(replace="text-body2")

    for control in form.elements:
        control.on_value_change(refresh)
    for control in (day_type, season, months):
        control.on_value_change(refresh)
    refresh()


def _rows(members: list[dict], net: dict[str, Any] | None) -> list[dict]:
    """Table rows, with what does not fit the network in "check"."""
    elements = {e.id: e for e in (net or {}).get("elements", [])}
    buses = set((net or {}).get("buses", []))
    rows = []
    for p in members:
        owns = p.get("owns") or {}
        owned = [e for side in owns.values() for e in side]
        profile, scaling = p.get("profile") or {}, p.get("scaling") or {}
        battery = p.get("battery")
        problems = []
        if net and net.get("topology") is not None:
            if p.get("bus") not in buses:
                problems.append("bus not in network")
            unknown = [e for e in owned if e not in elements]
            if unknown:
                problems.append(f"{len(unknown)} unknown elements")
            elsewhere = [
                e for e in owned if e in elements and elements[e].bus != p.get("bus")
            ]
            if elsewhere:
                problems.append(f"{len(elsewhere)} elements on another bus")
        rows.append(
            {
                "id": p["id"],
                "role": p.get("role", ""),
                "bus": p.get("bus", ""),
                "owns": ", ".join(owned) or "—",
                "profile": _profile_text(profile),
                "scaling": _scaling_text(scaling),
                "battery": (
                    f"{battery.get('nominal_capacity_kwh')} kWh" if battery else "—"
                ),
                "check": "; ".join(problems),
            }
        )
    return rows


def _profile_text(profile: dict) -> str:
    source = profile.get("source", "native")
    if source == "catalog":
        sides = [
            (profile.get(s) or {}).get("type") or "—" for s in ("demand", "generation")
        ]
        return f"catalog: {sides[0]} / {sides[1]}"
    return source


def _scaling_text(scaling: dict) -> str:
    mode = scaling.get("mode", "none")
    if mode == "none":
        return "—"
    unit = "kW" if mode == "peak_kw" else "kWh/a"
    return " / ".join(
        f"{scaling[s]:g} {unit}" for s in ("demand", "generation") if s in scaling
    )


def _free_number(members: list[dict]) -> int:
    """The next number for a default ``agent_NN`` ID."""
    ids = {p["id"] for p in members}
    n = len(ids) + 1
    while f"agent_{n:02d}" in ids:
        n += 1
    return n


def _merge(existing: list[dict], placed: list[dict]) -> list[dict]:
    """Placed participants added to the existing ones, skipping taken elements
    and renaming clashing IDs.
    """
    taken = {
        e for p in existing for side in (p.get("owns") or {}).values() for e in side
    }
    ids = {p["id"] for p in existing}
    out = list(existing)
    for p in placed:
        if any(e in taken for side in p["owns"].values() for e in side):
            continue
        base, n = p["id"], 2
        while p["id"] in ids:
            p = {**p, "id": f"{base}_{n}"}
            n += 1
        ids.add(p["id"])
        out.append(p)
    return out
