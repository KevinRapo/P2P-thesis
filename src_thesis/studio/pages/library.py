"""Library (05 §4.11) and Settings."""

from nicegui import app, ui

from ..components import data_table, not_implemented, section
from ..layout import shell
from ..state import open_draft, services


@ui.page("/library")
def library_page() -> None:
    s = services()
    with shell("library", "Library", "Experiment files and presets"):
        with ui.row().classes("w-full gap-2"):
            ui.button(
                "Import bundle",
                icon="unarchive",
                on_click=lambda: not_implemented("Import bundle"),
            ).props("outline")
            ui.button(
                "Open file",
                icon="folder_open",
                on_click=lambda: not_implemented("Open file"),
            ).props("outline")
        with section("Files", "Click to open as draft", "folder"):
            rows = [
                {
                    "id": f.id,
                    "name": f.name,
                    "kind": f.kind,
                    "kind_color": "primary" if f.kind == "preset" else "accent",
                    "network": f.network,
                    "participants": f.participants,
                    "path": f.path,
                    "modified": f.modified.strftime("%Y-%m-%d"),
                }
                for f in s.config.list()
            ]
            table = data_table(
                rows,
                [
                    ("name", "Name"),
                    ("kind", "Kind"),
                    ("network", "Network"),
                    ("participants", "Agents"),
                    ("path", "Path"),
                    ("modified", "Modified"),
                ],
                badge_columns={"kind": "kind_color"},
                pagination=15,
            )

            def open_file(file_id: str, kind: str) -> None:
                file = (
                    s.config.new_from_preset(file_id)
                    if kind == "preset"
                    else s.config.load(file_id)
                )
                open_draft(file)
                ui.navigate.to("/build/summary")

            table.on(
                "rowClick", lambda e: open_file(e.args[1]["id"], e.args[1]["kind"])
            )
        with section("Provenance", icon="account_tree"):
            ui.label(
                "preset → experiment file → runs (shown per file once real services exist)"
            ).classes("mls-card-caption")


@ui.page("/settings")
def settings_page() -> None:
    s = services()
    with shell(
        "settings",
        "Settings",
        "Local preferences; research state lives in the experiment store",
    ):
        with section("Experiment store", icon="storage"):
            ui.input("Store path", value="C:/marlem-store").classes("w-full")
            ui.label("Keep heavy run data outside OneDrive.").classes(
                "mls-card-caption"
            )
        with section("Services", icon="lan"):
            ui.label(f"Mode: {s.mode}").classes("text-body2")
            ui.label(
                "Switch to real services once roadmap phases R6–R7 exist."
            ).classes("mls-card-caption")
        with section("Appearance", icon="palette"):
            ui.switch(
                "Dark mode",
                value=app.storage.user.get("dark", False),
                on_change=lambda e: app.storage.user.update(dark=e.value),
            )
