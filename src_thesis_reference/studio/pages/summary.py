"""Summary (05 §4.5): read-only view of the draft experiment file."""

from nicegui import ui

from ..components import not_implemented, section, stat, stat_grid
from ..layout import shell
from ..state import current_draft, services


@ui.page("/build/summary")
def summary_page() -> None:
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
                ui.input("File id", value=draft.meta.id).classes("w-full")
                ui.input("Name", value=draft.meta.name).classes("w-full")
                ui.button(
                    "Save",
                    icon="save",
                    on_click=lambda: ui.notify(f"Saved to {s.config.save(draft)}"),
                ).props("unelevated").classes("w-full")
                ui.button(
                    "Save as…",
                    icon="save_as",
                    on_click=lambda: not_implemented("Save as"),
                ).props("outline").classes("w-full")
                ui.button(
                    "Export bundle",
                    icon="archive",
                    on_click=lambda: ui.notify(
                        f"Bundle: {s.config.export_bundle(draft)}"
                    ),
                ).props("outline").classes("w-full")
                ui.button(
                    "Diff against preset",
                    icon="difference",
                    on_click=lambda: not_implemented("Diff against preset"),
                ).props("outline").classes("w-full")
                ui.separator()
                ui.label(f"Hash {s.config.hash(draft)[:16]}…").classes(
                    "mls-card-caption mls-mono"
                )
