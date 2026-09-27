"""Cards, stat tiles and placeholders."""

from collections.abc import Generator
from contextlib import contextmanager

from nicegui import ui


@contextmanager
def section(
    title: str, caption: str = "", icon: str | None = None, classes: str = ""
) -> Generator[ui.column, None, None]:
    """A bordered card with a title row; content goes inside the `with` block."""
    with ui.column().classes(f"mls-card gap-3 w-full min-w-0 {classes}") as card:
        with ui.row().classes("items-center gap-2 no-wrap w-full"):
            if icon:
                ui.icon(icon, size="20px").classes("text-primary")
            with ui.column().classes("gap-0"):
                ui.label(title).classes("mls-card-title")
                if caption:
                    ui.label(caption).classes("mls-card-caption")
        yield card


def stat(
    label: str, value: str, caption: str = "", icon: str = "", tone: str = "primary"
) -> None:
    with ui.column().classes("mls-card gap-1"):
        with ui.row().classes("items-center justify-between w-full no-wrap"):
            ui.label(label).classes("mls-stat-label")
            if icon:
                ui.icon(icon, size="20px").classes(f"text-{tone}")
        ui.label(value).classes(
            "mls-stat-value" if len(value) <= 12 else "mls-stat-value-sm"
        )
        if caption:
            ui.label(caption).classes("mls-card-caption")


@contextmanager
def stat_grid() -> Generator[ui.element, None, None]:
    """Responsive grid for stat tiles."""
    with ui.element("div").classes("mls-stat-grid") as grid:
        yield grid


def key_values(items: dict) -> None:
    with ui.element("div").classes("mls-kv"):
        for key, value in items.items():
            ui.label(str(key)).classes("mls-card-caption")
            ui.label(str(value)).classes("text-body2")


def placeholder(text: str, icon: str = "construction") -> None:
    with ui.column().classes("mls-placeholder w-full items-center gap-1"):
        ui.icon(icon, size="22px")
        ui.label(text)


def not_implemented(action: str) -> None:
    """Default handler for buttons whose service call is not wired yet."""
    ui.notify(
        f"{action}: not implemented yet (UI scaffold).",
        type="info",
        position="bottom-right",
    )
