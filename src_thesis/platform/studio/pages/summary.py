"""Summary (05 §6): the draft experiment file, saving, sharing and its diff."""

from nicegui import ui

from src_thesis.platform.studio.components.tables import data_table
from src_thesis.platform.studio.components.cards import section, stat, stat_grid
from src_thesis.platform.studio.forms import DraftForm
from src_thesis.platform.studio.layout import shell
from src_thesis.platform.studio.state import current_draft, flash, open_draft, services

# Top-level sections of the file and the page that edits them.
SECTION_PAGES = [
    ("time", "/build/participants"),
    ("grid", "/build/grid"),
    ("participants", "/build/participants"),
    ("market", "/build/market"),
    ("dso", "/build/market"),
    ("environment", "/build/market"),
    ("learning", "/build/rl"),
    ("evaluation", "/build/rl"),
    ("baselines", "/build/rl"),
    ("sweep", "/build/rl"),
    ("resources", "/build/rl"),
    ("outputs", "/build/rl"),
]


def _count(node) -> int:
    """Number of values set in a section (leaves of its dicts; list items)."""
    if isinstance(node, dict):
        return sum(_count(v) for v in node.values())
    if isinstance(node, list):
        return len(node)
    return 0 if node is None else 1


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
    """Summary (05 §6): the draft as JSON; save, save as, export a bundle, diff
    against its origin.
    """
    s = services()
    draft = current_draft()
    with shell("summary", "Summary", f"Draft experiment file · {draft.meta.id}"):
        batteries = sum(1 for p in draft.participants if p.battery)
        source = draft.grid.source
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
                (source.code if source else None) or "—",
                (source.type if source else None) or "",
                "hub",
            )
            stat(
                "Horizon",
                f"{draft.time.horizon_steps or '—'} steps",
                draft.time.resolution or "",
                "schedule",
            )
            stat(
                "Runs",
                str(len(runs)),
                "sweep × paradigms × algorithms × seeds",
                "play_circle",
            )
            stat("Data status", draft.meta.data_status, "", "verified")

        with section(
            "Sections",
            "Values set in the file; everything else takes its default. Click to edit.",
            "list_alt",
        ):
            with ui.row().classes("w-full gap-2"):
                for name, route in SECTION_PAGES:
                    n = _count(draft.to_data()[name])
                    ui.button(
                        f"{name} · {n}",
                        on_click=lambda route=route: ui.navigate.to(route),
                    ).props("outline no-caps dense")

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
                form = DraftForm(draft)
                form.bind(
                    "meta.name",
                    ui.input("Name", value=draft.meta.name).classes("w-full"),
                )
                form.bind(
                    "meta.description",
                    ui.textarea("Description", value=draft.meta.description)
                    .classes("w-full")
                    .props("autogrow"),
                )
                form.bind(
                    "meta.author",
                    ui.input("Author", value=draft.meta.author).classes("w-full"),
                )
                tags = ui.input("Tags", value=", ".join(draft.meta.tags)).classes(
                    "w-full"
                )
                form.track(
                    "meta.tags",
                    lambda: [x.strip() for x in tags.value.split(",") if x.strip()],
                )
                form.bind(
                    "meta.data_status",
                    ui.select(
                        {
                            "synthetic": "Synthetic",
                            "measured": "Measured",
                            "reconstructed-unverified": "Reconstructed, unverified",
                        },
                        value=draft.meta.data_status,
                        label="Data status",
                    ).classes("w-full"),
                )
                ui.label(
                    "Data status keeps reconstructed data (e.g. the Case 6 mapping, "
                    "I-51) from being presented as measured."
                ).classes("mls-card-caption")
                ui.button("Save", icon="save", on_click=form.apply).props(
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
