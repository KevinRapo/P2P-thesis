"""Shared page shell: header, navigation drawer and page heading. The header shows
whether the cluster answers, names the current scenario and opens another from a
scenario file."""

import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from nicegui import app, run, ui

from core.config.scenario import Scenario
from studio.navigation import NAV
from studio.state import services
from studio.theme import apply_theme

CONTACT_QUIET_S = 60  # seconds without contact before the status checks by itself
CONTACT_SHOW_S = 5  # seconds between looks at the status


def _toggle_dark(dark: ui.dark_mode) -> None:
    """Switch dark mode and remember the choice for this browser."""
    dark.toggle()
    app.storage.user["dark"] = bool(dark.value)


@contextmanager
def shell(active: str, title: str, subtitle: str = "") -> Generator[None, None, None]:
    """Build the page frame; the caller fills the content inside the `with` block."""
    apply_theme()
    dark = ui.dark_mode(value=app.storage.user.get("dark", False))

    # Left navigation (NAV in navigation.py); the current page is highlighted.
    with ui.left_drawer(value=True, bordered=True).props("width=232").classes(
        "mls-drawer q-pt-sm"
    ) as drawer:
        for group, items in NAV:
            if group:
                ui.label(group).classes("mls-nav-group")
            else:
                ui.element("div").classes("q-mt-sm")
            for item in items:
                is_active = item.key == active

                # One clickable entry: icon (left) | label
                with ui.item(on_click=lambda r=item.route: ui.navigate.to(r)).props(
                    "dense"
                ).classes("mls-nav-item" + (" mls-nav-active" if is_active else "")):
                    with ui.item_section().props("avatar").style("min-width: 34px"):
                        ui.icon(item.icon, size="20px")
                    with ui.item_section():
                        ui.item_label(item.label)

    # Top bar, left to right: menu button, logo and name, (space), cluster status,
    # scenario button, dark-mode button
    with ui.header(elevated=False).classes("mls-header items-center q-px-md gap-3"):
        ui.button(icon="menu", on_click=drawer.toggle).props(
            "flat round dense color=white"
        )
        ui.icon("bolt", size="26px").classes("text-amber-4")
        ui.label("MARLEM Studio").classes("mls-brand")
        ui.space()

        for name, label in services().runs.clusters():
            _cluster_status(name, label)

        _scenario_button()
        ui.button(icon="dark_mode", on_click=lambda: _toggle_dark(dark)).props(
            "flat round dense color=white"
        )

    # Page heading; the page's own content follows where the caller's
    # `with shell(...)` block continues (the yield).
    with ui.column().classes("mls-page w-full"):
        # Title with the subtitle under it
        with ui.column().classes("gap-0"):
            ui.label(title).classes("mls-title")
            if subtitle:
                ui.label(subtitle).classes("mls-subtitle")
        yield


# --------------------------------------------------------------------------------------
# The cluster: whether it answers over SSH
# --------------------------------------------------------------------------------------
def _ago(seconds: float) -> str:
    return f"{seconds:.0f} s" if seconds < 90 else f"{seconds / 60:.0f} min"


def contact_shown(contact, label: str, now: float) -> tuple[str, str, str]:
    """A cluster's status as the top bar shows it: ``(colour, text, tooltip)``, from
    its ``Contact`` (None: nothing has used the connection yet). Says when it last
    answered, not "connected": the connection is used, not watched."""
    if contact is None or not contact.at:
        return "grey-5", label, "Not checked yet."

    if contact.ok_at is None:
        last = "It has not answered since the Studio started."
    else:
        clock = time.strftime("%H:%M:%S", time.localtime(contact.ok_at))
        last = f"Last contact {clock} ({_ago(now - contact.ok_at)} ago)."

    if contact.error:
        return "red-5", f"{label}: no connection", f"{contact.error}. {last}"

    return "green-5", label, last


def _cluster_status(name: str, label: str) -> None:
    """One cluster's dot and name, kept up to date; a click checks it now. The status
    lives in the connection, so it stays the same from page to page. Green says SSH
    works, nothing more: whether an experiment can start is on the Runs page."""
    runs = services().runs

    # One button: dot | name, with what is known in the tooltip
    with ui.button().props("flat no-caps dense color=white") as button:
        dot = ui.icon("circle", size="12px").classes("q-mr-xs")
        text = ui.label()
        hint = ui.tooltip()

    def show() -> None:
        colour, shown, tip = contact_shown(runs.contact(name), label, time.time())
        dot.props(f"color={colour}")
        text.set_text(shown)
        hint.set_text(f"{tip} Click to check now.")

    async def tick() -> None:
        await run.io_bound(runs.check_connection, name, CONTACT_QUIET_S)

        if not button.is_deleted:
            show()

    async def on_check() -> None:
        button.props("loading")

        try:
            await run.io_bound(runs.check_connection, name)
        finally:
            button.props(remove="loading")
            show()

    button.on_click(on_check)
    show()
    ui.timer(CONTACT_SHOW_S, tick)


# --------------------------------------------------------------------------------------
# The scenario: which one is open, and opening another from a file
# --------------------------------------------------------------------------------------
def _summary(scenario: Scenario) -> str:
    n = len(scenario.participants)
    return (
        f"{scenario.grid.code} · {scenario.grid.day} · {n} participants · "
        f"{scenario.market.mechanism}"
    )


def _scenario_button() -> None:
    """The active scenario's name, and whether it is saved (kept up to date, as other
    pages change it); a click opens another from a file."""
    s = services().scenario
    current = s.current()
    button = ui.button(
        f"Scenario: {s.shown_name()}",
        icon="folder_open",
        on_click=_open_dialog,
    ).props("flat no-caps color=white")
    button.tooltip(f"{_summary(current)}. Click to open a scenario file.")
    badge = ui.badge("unsaved", color="amber-8").tooltip(
        "The active scenario has no file, or differs from the one it came from "
        "(-mod). It can be played and started all the same; the Scenario page saves "
        "it."
    )

    def show_state() -> None:
        button.set_text(f"Scenario: {s.shown_name()}")
        badge.set_visibility(s.unsaved())

    show_state()
    ui.timer(1.0, show_state)


def _open(scenario: Scenario, source: str, path: Optional[Path] = None) -> None:
    """Make ``scenario`` the Studio's, on every page, and start the pages again."""
    s = services()
    s.scenario.open(scenario, source, path)
    s.market.clear()  # the Step page's market was built from the old scenario
    ui.notify(f"Opened {source}: {_summary(scenario)}")
    ui.navigate.reload()


def _open_dialog() -> None:
    s = services().scenario

    # Pop-up window: the saved scenario files, an upload field, Cancel
    with ui.dialog() as dialog, ui.card().classes("w-[640px] max-w-full gap-3"):
        ui.label("Open a scenario file").classes("text-h6")
        ui.label(
            "Replaces the active scenario on every page: network, day, participants, "
            "market and DSO. The file itself is not changed: edits stay in the active "
            "scenario, marked unsaved. The Step page starts again from the opened "
            "scenario."
        ).classes("mls-card-caption")
        files = s.files()

        if s.library is not None:
            ui.label(f"In {s.library.parent.name}/{s.library.name}/").classes(
                "text-subtitle2"
            )

        if not files:
            ui.label(
                "No scenario files yet. A notebook writes one with "
                "core.config.store.save(scenario, path)."
            ).classes("mls-card-caption")

        for path in files:
            _file_row(path, dialog)

        ui.label("Or a file from elsewhere").classes("text-subtitle2")

        async def uploaded(e) -> None:
            try:
                scenario = s.parse(await e.file.text())
            except (ValueError, TypeError, KeyError) as err:
                ui.notify(
                    f"{e.file.name}: not a scenario file ({err})", type="negative"
                )
                return
            dialog.close()
            _open(scenario, e.file.name)

        ui.upload(label="Scenario JSON", auto_upload=True, on_upload=uploaded).props(
            "accept=.json flat bordered"
        ).classes("w-full")

        # Bottom: Cancel, right-aligned
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=dialog.close).props("flat no-caps")
    dialog.open()


def _file_row(path: Path, dialog: ui.dialog) -> None:
    """One file: its name, what is in it, and Open."""
    try:
        scenario = services().scenario.peek(path)
    except (OSError, ValueError, TypeError, KeyError) as err:
        ui.label(f"{path.name}: cannot be read ({err})").classes("text-negative")
        return

    def choose() -> None:
        dialog.close()
        _open(scenario, path.name, path)

    # One row: file name with its summary under it (left) | Open (right)
    with ui.row().classes("w-full items-center no-wrap gap-3"):
        with ui.column().classes("grow gap-0"):
            ui.label(path.name).classes("text-body1")
            ui.label(_summary(scenario)).classes("mls-card-caption")
        ui.button("Open", icon="folder_open", on_click=choose).props(
            "unelevated no-caps"
        )
