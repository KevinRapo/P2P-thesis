"""Shared page shell: header, navigation drawer and page heading."""

from collections.abc import Generator
from contextlib import contextmanager

from nicegui import app, ui

from studio.navigation import NAV
from studio.theme import apply_theme


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
                with ui.item(on_click=lambda r=item.route: ui.navigate.to(r)).props(
                    "dense"
                ).classes("mls-nav-item" + (" mls-nav-active" if is_active else "")):
                    with ui.item_section().props("avatar").style("min-width: 34px"):
                        ui.icon(item.icon, size="20px")
                    with ui.item_section():
                        ui.item_label(item.label)

    with ui.header(elevated=False).classes("mls-header items-center q-px-md gap-3"):
        ui.button(icon="menu", on_click=drawer.toggle).props(
            "flat round dense color=white"
        )
        ui.icon("bolt", size="26px").classes("text-amber-4")
        ui.label("MARLEM Studio").classes("mls-brand")
        ui.space()
        ui.button(icon="dark_mode", on_click=lambda: _toggle_dark(dark)).props(
            "flat round dense color=white"
        )

    # Page heading; the page's own content follows where the caller's
    # `with shell(...)` block continues (the yield).
    with ui.column().classes("mls-page w-full"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("mls-title")
            if subtitle:
                ui.label(subtitle).classes("mls-subtitle")
        yield
