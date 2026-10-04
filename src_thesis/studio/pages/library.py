"""Library (05 §6) and Settings."""

import zipfile

from nicegui import app, events, ui

from src_thesis.studio.components.tables import data_table
from src_thesis.studio.components.cards import section
from src_thesis.studio.layout import shell
from src_thesis.application import workspace

from src_thesis.studio.state import flash, open_draft, reset_services, services

ACTIONS_SLOT = """<q-td :props="props" auto-width>
  <template v-if="props.row.kind !== 'preset'">
    <q-btn flat dense round icon="content_copy" size="sm"
      @click.stop="$parent.$emit('clone', props.row)">
      <q-tooltip>Clone</q-tooltip></q-btn>
    <q-btn flat dense round icon="delete" size="sm" color="negative"
      @click.stop="$parent.$emit('remove', props.row)">
      <q-tooltip>Delete</q-tooltip></q-btn>
  </template>
</q-td>"""


@ui.page("/library")
def library_page() -> None:
    """Library (05 §6): presets and your files; click one to open it as the draft."""
    s = services()
    with shell("library", "Library", "Experiment files and presets"):
        with ui.row().classes("w-full gap-2"):
            ui.button(
                "Open file",
                icon="folder_open",
                on_click=lambda: _upload_dialog(
                    "Open an experiment file",
                    "A .marlem.json file; it is copied into your library and opened "
                    "as the draft.",
                    ".json",
                    s.config.import_file,
                ),
            ).props("outline")
            ui.button(
                "Import bundle",
                icon="unarchive",
                on_click=lambda: _upload_dialog(
                    "Import a bundle",
                    "A .zip made by Export bundle: the experiment file and its data "
                    "files (unpacked into the workspace's imports folder).",
                    ".zip",
                    s.config.import_bundle,
                ),
            ).props("outline")
        with section(
            "Files",
            "Click a row to open it as the draft (a preset opens as a new draft). "
            "Presets are read-only.",
            "folder",
        ):
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
            for row in rows:
                row["actions"] = ""
            table = data_table(
                rows,
                [
                    ("actions", ""),
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
                """Open a row as the draft: a preset becomes a new draft, a file
                opens as it is.
                """
                file = (
                    s.config.new_from_preset(file_id)
                    if kind == "preset"
                    else s.config.load(file_id)
                )
                open_draft(file)
                ui.navigate.to("/build/summary")

            # Clone and delete per library file; their clicks do not open the row.
            table.add_slot("body-cell-actions", ACTIONS_SLOT)
            table.on(
                "rowClick", lambda e: open_file(e.args[1]["id"], e.args[1]["kind"])
            )
            table.on("clone", lambda e: _clone_dialog(e.args["id"]))
            table.on("remove", lambda e: _delete_dialog(e.args["id"]))
        with section("Provenance", icon="account_tree"):
            ui.label(
                "preset → experiment file → runs (shown per file once real services exist)"
            ).classes("mls-card-caption")


def _upload_dialog(title: str, text: str, accept: str, read) -> None:
    """Upload one file, hand its bytes to ``read`` (a ConfigService import), open
    the result as the draft.
    """
    with ui.dialog() as dialog, ui.card().classes("mls-card w-[34rem]"):
        ui.label(title).classes("mls-card-title")
        ui.label(text).classes("mls-card-caption")
        message = ui.label().classes("text-negative text-body2")

        async def received(e: events.UploadEventArguments) -> None:
            try:
                file = read(await e.file.read())
            except (ValueError, OSError, zipfile.BadZipFile) as error:
                message.set_text(str(error))
                return
            open_draft(file)
            flash(f"Imported {file.meta.id}")
            ui.navigate.to("/build/summary")

        ui.upload(on_upload=received, auto_upload=True).props(
            f'accept="{accept}"'
        ).classes("w-full")
        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
    dialog.open()


def _clone_dialog(file_id: str) -> None:
    """Copy a library file under a new ID."""
    config = services().config
    with ui.dialog() as dialog, ui.card().classes("mls-card w-[28rem]"):
        ui.label(f"Clone {file_id}").classes("mls-card-title")
        new_id = ui.input("New file id", value=f"{file_id}-copy").classes("w-full")
        message = ui.label().classes("text-negative text-body2")

        def clone() -> None:
            try:
                config.clone(file_id, new_id.value.strip())
            except (ValueError, OSError) as error:
                message.set_text(str(error))
                return
            flash(f"Cloned {file_id} as {new_id.value.strip()}")
            ui.navigate.reload()

        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Clone", icon="content_copy", on_click=clone).props("unelevated")
    dialog.open()


def _delete_dialog(file_id: str) -> None:
    """Delete a library file after confirmation."""
    config = services().config
    with ui.dialog() as dialog, ui.card().classes("mls-card w-[28rem]"):
        ui.label(f"Delete {file_id}?").classes("mls-card-title")
        ui.label(
            "The file is removed from the library. Runs made from it keep their "
            "own copy."
        ).classes("text-body2")

        def delete() -> None:
            try:
                config.delete(file_id)
            except (FileNotFoundError, OSError) as error:
                ui.notify(str(error), type="negative")
                return
            if app.storage.user.get("draft_id") == file_id:
                app.storage.user.pop("draft_id", None)
            flash(f"Deleted {file_id}")
            ui.navigate.reload()

        with ui.row().classes("justify-end w-full"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Delete", icon="delete", on_click=delete).props(
                "unelevated color=negative"
            )
    dialog.open()


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
            sample = s.sample_data()
            ui.label(
                "Still sample data: " + (", ".join(sample) if sample else "nothing")
            ).classes("text-body2")
            ui.label(
                "A service returns sample data until its methods are built "
                "(see the implementation status document)."
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
            """Remember ``path`` as the workspace folder (``None`` = default),
            rebuild the services and reload.
            """
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
