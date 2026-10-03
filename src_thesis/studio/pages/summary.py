"""Summary (04 §4.5): the draft experiment file, saving, sharing and its diff."""

from nicegui import ui

from ..components import data_table, section, stat, stat_grid
from ..layout import shell
from ..state import current_draft, flash, open_draft, services


def _save_as_dialog(draft) -> None:
    """Dialog that saves the draft under a new file ID and name."""
    config = services().config
    with ui.dialog() as dialog, ui.card().classes("min-w-[28rem]"):
        ui.label("Save as a new experiment file").classes("text-h6")
        new_id = ui.input("File id", value=f"{draft.meta.id}-copy").classes("w-full")
        name = ui.input("Name", value=draft.meta.name).classes("w-full")
        ui.label(
            "Letters, digits, '.', '-' and '_'. The new file records this one as "
            "its origin."
        ).classes("mls-card-caption")

        def save() -> None:
            """Clone the draft under the new ID, set its name, open it and reload."""
            try:
                clone = config.clone(draft.meta.id, new_id.value.strip())
                clone = config.update(clone, {"meta.name": name.value.strip()})
                open_draft(clone)
            except (ValueError, OSError) as error:
                ui.notify(str(error), type="negative", multi_line=True)
                return
            dialog.close()
            flash(f"Saved as {clone.meta.id}")
            ui.navigate.reload()

        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Save", icon="save_as", on_click=save).props("unelevated")
    dialog.open()


def _diff_dialog(draft) -> None:
    """Dialog listing every field that differs from the draft's origin (preset or
    file).
    """
    config = services().config
    origin = config.origin(draft)
    with ui.dialog() as dialog, ui.card().classes("min-w-[48rem] max-w-[90vw]"):
        if origin is None:
            ui.label("No origin to compare with").classes("text-h6")
            ui.label(
                f"derived_from = {draft.meta.derived_from!r} does not point to an "
                "existing preset or file."
            ).classes("mls-card-caption")
        else:
            changes = [c for c in config.diff(origin, draft) if c.path != "meta.id"]
            ui.label(f"Changes against {origin.meta.id}").classes("text-h6")
            if not changes:
                ui.label("Identical apart from the file id.").classes(
                    "mls-card-caption"
                )
            else:
                data_table(
                    [
                        {
                            "path": c.path,
                            "before": "unset" if c.before is None else str(c.before),
                            "after": "unset" if c.after is None else str(c.after),
                        }
                        for c in changes
                    ],
                    [("path", "Field"), ("before", "Origin"), ("after", "This file")],
                    pagination=15,
                )
        with ui.row().classes("justify-end w-full"):
            ui.button("Close", on_click=dialog.close).props("flat")
    dialog.open()


@ui.page("/build/summary")
def summary_page() -> None:
    """Summary (04 §4.5): the draft as JSON; save, save as, export a bundle, diff
    against its origin.
    """
    s = services()
    draft = current_draft()
    with shell("summary", "Summary", f"Draft experiment file · {draft.meta.id}"):
        batteries = sum(1 for p in draft.participants if p.get("battery"))
        runs = s.config.expand(draft)
        with stat_grid():
            stat(
                "Participants",
                str(len(draft.participants)),
                f"{batteries} with battery",
                "groups",
            )
            stat(
                "Network",
                draft.grid.get("source", {}).get("code", "—"),
                draft.grid.get("source", {}).get("type", ""),
                "hub",
            )
            stat(
                "Horizon",
                f"{draft.time.get('horizon_steps', '—')} steps",
                draft.time.get("resolution", ""),
                "schedule",
            )
            stat(
                "Runs",
                str(len(runs)),
                "sweep × paradigms × algorithms × seeds",
                "play_circle",
            )
            stat("Data status", draft.meta.data_status, "", "verified")

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Experiment file (JSON)",
                "Exactly what the CLI would run",
                "data_object",
                classes="grow basis-0",
            ):
                ui.code(s.config.to_json(draft), language="json").classes(
                    "w-full"
                ).style("max-height: 560px; overflow: auto")
            with section("Actions", icon="bolt", classes="basis-1/4 min-w-0"):
                ui.input("File id", value=draft.meta.id).props("readonly").classes(
                    "w-full"
                ).tooltip("Use Save as to store the file under another id")
                name = ui.input("Name", value=draft.meta.name).classes("w-full")
                description = ui.textarea(
                    "Description", value=draft.meta.description
                ).classes("w-full")

                def save() -> None:
                    """Write name and description into the draft file and reload."""
                    try:
                        updated = s.config.update(
                            draft,
                            {
                                "meta.name": name.value.strip(),
                                "meta.description": description.value.strip(),
                            },
                        )
                        path = s.config.save(updated)
                    except (ValueError, OSError) as error:
                        ui.notify(str(error), type="negative", multi_line=True)
                        return
                    flash(f"Saved to {path}")
                    ui.navigate.reload()

                ui.button("Save", icon="save", on_click=save).props(
                    "unelevated"
                ).classes("w-full")
                ui.button(
                    "Save as…", icon="save_as", on_click=lambda: _save_as_dialog(draft)
                ).props("outline").classes("w-full")
                ui.button(
                    "Export bundle",
                    icon="archive",
                    on_click=lambda: ui.notify(
                        f"Bundle: {s.config.export_bundle(draft)}"
                    ),
                ).props("outline").classes("w-full")
                ui.button(
                    "Diff against origin",
                    icon="difference",
                    on_click=lambda: _diff_dialog(draft),
                ).props("outline").classes("w-full")
                ui.separator()
                ui.label(f"Derived from {draft.meta.derived_from or '—'}").classes(
                    "mls-card-caption"
                )
                ui.label(f"Hash {s.config.hash(draft)[:16]}…").classes(
                    "mls-card-caption mls-mono"
                )
