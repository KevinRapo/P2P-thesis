"""Settings: the workspace folder, the network cache and appearance."""

from __future__ import annotations

from nicegui import app, run, ui

from config import workspace
from studio.components.cards import section
from studio.components.tables import data_table
from studio.layout import shell
from studio.state import reset_services, services

# What the "Prepare" buttons build; levels whose networks are all cached are off.
PREPARE = (
    ("Prepare LV and MV", ["LV", "MV"]),
    ("Prepare HV and EHV", ["HV", "EHV"]),
    ("Prepare all", ["LV", "MV", "HV", "EHV", "MVLV", "HVMV", "EHVHV"]),
)


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """Settings: workspace folder, network cache, appearance."""
    with shell("settings", "Settings", "Local preferences of this computer"):
        _workspace_section()
        _cache_section()
        with section("Appearance", icon="palette"):
            ui.switch(
                "Dark mode",
                value=app.storage.user.get("dark", False),
                on_change=lambda e: app.storage.user.update(dark=e.value),
            )


# --------------------------------------------------------------------------------------
# Network cache
# --------------------------------------------------------------------------------------
def _cache_section() -> None:
    """The network cache: how much of the catalogue is prepared, and buttons to
    prepare or clear it."""
    grid = services().grid
    with section(
        "Network cache",
        "Built networks are kept on disk, so they open in a fraction of a second "
        "instead of 3-4 s",
        "bolt",
    ):
        status = ui.label().classes("text-body2")
        progress = ui.linear_progress(show_value=False).props("rounded size=8px")
        detail = ui.label().classes("mls-card-caption mls-mono")
        table_box = ui.column().classes("w-full")
        ui.label(
            "At start-up the Studio prepares the LV and MV networks in the "
            "background. Any other network is cached the first time you open it. "
            "HV, EHV and the combined networks are large: up to 120 MB each. "
            "Built-in networks are only cached when opened."
        ).classes("mls-card-caption")
        with ui.row().classes("gap-2"):
            buttons = [
                (
                    ui.button(
                        label,
                        icon="download",
                        on_click=lambda levels=levels: prepare(levels),
                    ).props("outline no-caps"),
                    levels,
                )
                for label, levels in PREPARE
            ]
            ui.button(
                "Clear cache",
                icon="delete",
                on_click=lambda: (grid.clear_cache(), refresh_coverage()),
            ).props("flat no-caps color=negative")
        state = {"coverage": [], "running": False}

        def prepare(levels: list[str]) -> None:
            grid.warm_cache(levels)
            refresh()

        async def refresh_coverage() -> None:
            """Count the cached networks per level (a folder scan)."""
            state["coverage"] = await run.io_bound(grid.cache_coverage)
            show_coverage()

        def show_coverage() -> None:
            rows = state["coverage"]
            cached = sum(r["cached"] for r in rows)
            total = sum(r["total"] for r in rows)
            done = {r["group"] for r in rows if r["cached"] == r["total"]}
            status.set_text(
                f"{cached} of {total} networks cached ({cached / total:.0%})"
                if total
                else "No cache folder."
            )
            progress.set_value(cached / total if total else 0)
            table_box.clear()
            with table_box:
                data_table(
                    [
                        {
                            "group": r["group"],
                            "cached": f"{r['cached']} of {r['total']}",
                            "state": (
                                "complete"
                                if r["cached"] == r["total"]
                                else f"{r['total'] - r['cached']} to build"
                            ),
                        }
                        for r in rows
                    ],
                    [
                        ("group", "Networks"),
                        ("cached", "Cached"),
                        ("state", ""),
                    ],
                    row_key="group",
                    pagination=0,
                )
            for button, levels in buttons:
                button.set_enabled(not set(levels) <= done)
                button.tooltip("All cached" if set(levels) <= done else "")

        def refresh() -> None:
            """Folder, size and the background preparation; the coverage table is
            counted again when a preparation ends."""
            s = grid.cache_status()
            text = f"{s['bytes'] / 1e9:.2f} GB in {s['folder']}"
            if s["running"]:
                text = (
                    f"Preparing {', '.join(s['levels'])}: {s['done']} of "
                    f"{s['total'] or '…'} · " + text
                )
            detail.set_text(text)
            if state["running"] and not s["running"]:
                ui.timer(0, refresh_coverage, once=True)
            state["running"] = s["running"]

        refresh()
        ui.timer(0, refresh_coverage, once=True)
        ui.timer(2.0, refresh)


# --------------------------------------------------------------------------------------
# Workspace folder
# --------------------------------------------------------------------------------------
def _workspace_section() -> None:
    """The workspace folder: where the Studio keeps its data."""
    home = workspace.default_home()
    source = workspace.home_source()
    with section(
        "Workspace folder",
        "Where the Studio keeps its data",
        "storage",
    ):
        folder = ui.input("Folder", value=str(home)).classes("w-full mls-mono")
        for name, what in (
            ("cache/networks", "built networks"),
            ("studio-state", "per-browser state (dark mode)"),
        ):
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
                "This folder is synced by OneDrive: the cache holds large files, "
                "which sync clients lock and duplicate. Choose a local folder."
            ).classes("text-warning text-caption")
        ui.label(
            f"Remembered in {workspace.settings_path()}. Existing files are not "
            "moved. The per-browser state moves after a restart."
        ).classes("mls-card-caption")

        def use(path: str | None) -> None:
            """Remember ``path`` as the workspace folder (``None`` = default),
            rebuild the services and reload."""
            try:
                new_home = workspace.set_home(path)
            except OSError as error:
                ui.notify(f"Cannot use this folder: {error}", type="negative")
                return
            reset_services()
            ui.notify(f"Workspace folder: {new_home}")
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
