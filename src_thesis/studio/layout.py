"""Shared page shell: header, navigation drawer, footer and page heading."""

from collections.abc import Generator
from contextlib import contextmanager

from nicegui import app, ui

from .navigation import NAV
from .state import current_draft, services
from .theme import apply_theme


def _toggle_dark(dark: ui.dark_mode) -> None:
    dark.toggle()
    app.storage.user["dark"] = bool(dark.value)


@contextmanager
def shell(active: str, title: str, subtitle: str = "") -> Generator[None, None, None]:
    """Build the page frame; the caller fills the content inside the `with` block."""
    apply_theme()
    dark = ui.dark_mode(value=app.storage.user.get("dark", False))
    draft = current_draft()
    report = services().validation.validate(draft, level="schema")
    running = sum(
        1 for r in services().experiments.list_runs() if r.state.value == "RUNNING"
    )

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
        with ui.row().classes("items-center gap-2 no-wrap"):
            with ui.row().classes("mls-draft-chip items-center gap-1 no-wrap").on(
                "click", lambda: ui.navigate.to("/build/summary")
            ):
                ui.icon("description", size="18px")
                ui.label(draft.meta.name).classes("text-caption ellipsis").style(
                    "max-width: 280px"
                )
                ui.tooltip("Draft experiment file")
            errors = sum(1 for f in report.findings if f.severity.value == "error")
            warnings = sum(1 for f in report.findings if f.severity.value == "warning")
            ui.chip(
                "valid" if errors == 0 else f"{errors} errors",
                icon="check_circle" if errors == 0 else "error",
                on_click=lambda: ui.navigate.to("/experiment/validate"),
            ).props(
                f"dense color={'positive' if errors == 0 else 'negative'} text-color=white"
            ).tooltip(
                f"{warnings} warnings"
            )
            ui.chip(
                f"{running} running" if running else "worker idle",
                icon="memory",
                on_click=lambda: ui.navigate.to("/runs"),
            ).props("dense color=blue-grey-8 text-color=white")
            if services().mode == "demo":
                ui.chip("DEMO DATA", icon="science").props(
                    "dense color=amber-8 text-color=white"
                ).tooltip("Demo services: no MARLEM code is executed")
            ui.button(icon="dark_mode", on_click=lambda: _toggle_dark(dark)).props(
                "flat round dense color=white"
            )

    with ui.footer(elevated=False).classes("mls-footer items-center q-px-md"):
        ui.label(
            "MARLEM Studio · presentation layer · all data via application services"
        )
        ui.space()
        ui.label(f"services: {services().mode}")

    with ui.column().classes("mls-page w-full"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("mls-title")
            if subtitle:
                ui.label(subtitle).classes("mls-subtitle")
        yield
