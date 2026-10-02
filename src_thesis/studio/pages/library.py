"""Library (04 §4.11) and Settings."""

from nicegui import app, ui

from ..components import data_table, not_implemented, section
from ..layout import shell
from src_thesis.application import workspace

from ..state import flash, open_draft, reset_services, services


@ui.page("/library")
def library_page() -> None:
    """Library (04 §4.11): presets and your files; click one to open it as the draft."""
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
    """Settings: the workspace folder, which services are real, appearance."""
    s = services()
    with shell(
        "settings",
        "Settings",
        "Local preferences; research state lives in the experiment store",
    ):
        _workspace_section()
        with section("Services", icon="lan"):
            ui.label(
                f"Experiment files: {s.config_backend} · grid catalog: "
                f"{s.grid_backend} · everything else: {s.mode}"
            ).classes("text-body2")
            ui.label(
                "Profiles, validation, runs and results are demo data until "
                "roadmap phase R7 (see the implementation status document)."
            ).classes("mls-card-caption")
        with section("Appearance", icon="palette"):
            ui.switch(
                "Dark mode",
                value=app.storage.user.get("dark", False),
                on_change=lambda e: app.storage.user.update(dark=e.value),
            )


def _workspace_section() -> None:
    """The workspace folder: where experiment files, runs and exports are saved."""
    home = workspace.default_home()
    source = workspace.home_source()
    with section(
        "Workspace folder",
        "Where your experiment files, run folders and exports are saved",
        "storage",
    ):
        folder = ui.input("Folder", value=str(home)).classes("w-full mls-mono")
        rows = [
            ("library", "experiment files (*.marlem.json)"),
            ("store", "run folders"),
            ("exports", "bundles"),
        ]
        for name, what in rows:
            ui.label(f"{home / name}  ·  {what}").classes("mls-card-caption mls-mono")
        if source == "environment":
            folder.disable()
            ui.label(
                "Set by the MARLEM_HOME environment variable, which takes precedence; "
                "unset it to choose the folder here."
            ).classes("text-warning text-caption")
        elif source == "default":
            ui.label("Default folder (nothing chosen yet).").classes("mls-card-caption")
        if workspace.is_synced_folder(home):
            ui.label(
                "This folder is synced by OneDrive: runs write many small files, "
                "which sync clients lock and duplicate. Choose a local folder."
            ).classes("text-warning text-caption")
        ui.label(
            f"Remembered in {workspace.settings_path()}. Existing files are not "
            "moved: copy the library folder over to keep them."
        ).classes("mls-card-caption")

        def use(path: str | None) -> None:
            try:
                new_home = workspace.set_home(path)
            except OSError as error:
                ui.notify(f"Cannot use this folder: {error}", type="negative")
                return
            reset_services()
            app.storage.user.pop("draft_id", None)
            flash(f"Workspace folder: {new_home}")
            ui.navigate.reload()

        with ui.row().classes("gap-2"):
            ui.button(
                "Use this folder", icon="check", on_click=lambda: use(folder.value)
            ).props("unelevated").set_enabled(source != "environment")
            ui.button(
                "Reset to default",
                icon="restart_alt",
                on_click=lambda: use(None),
            ).props("outline").set_enabled(source == "settings")
