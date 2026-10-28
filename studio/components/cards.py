"""Cards, stat tiles and placeholders; a box's states while it loads."""

from collections.abc import Callable, Generator
from contextlib import contextmanager
from typing import Any, Optional

from nicegui import run, ui


# --------------------------------------------------------------------------------------
# Cards and tiles
# --------------------------------------------------------------------------------------
@contextmanager
def section(
    title: str, caption: str = "", icon: str | None = None, classes: str = ""
) -> Generator[ui.column, None, None]:
    """A bordered card with a title row; content goes inside the `with` block."""
    # The card itself
    with ui.column().classes(f"mls-card gap-3 w-full min-w-0 {classes}") as card:
        # Title row: icon | title with the caption under it
        with ui.row().classes("items-center gap-2 no-wrap w-full"):
            if icon:
                ui.icon(icon, size="20px").classes("text-primary")
            with ui.column().classes("gap-0"):
                ui.label(title).classes("mls-card-title")
                if caption:
                    ui.label(caption).classes("mls-card-caption")

        # The caller's content follows here, under the title row
        yield card


def stat(
    label: str, value: str, caption: str = "", icon: str = "", tone: str = "primary"
) -> None:
    """A metric tile: small label, large value, optional caption and icon.

    Args:
        label: Title, e.g. ``"Participants"``.
        value: The number or text shown large; long values get a smaller font.
        caption: Line under the value.
        icon: Material icon name shown top-right.
        tone: Colour of the icon (``"primary"``, ``"warning"``, …).
    """
    # The tile: label and icon on top, the value, the caption
    with ui.column().classes("mls-card gap-1"):
        # Top line: label (left) | icon (right)
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
    """Two-column list of labels and values."""
    with ui.element("div").classes("mls-kv"):
        for key, value in items.items():
            ui.label(str(key)).classes("mls-card-caption")
            ui.label(str(value)).classes("text-body2")


# --------------------------------------------------------------------------------------
# Placeholders and a box's states: loading, failed, filled
# --------------------------------------------------------------------------------------
def placeholder(text: str, icon: str = "construction") -> None:
    """A muted box with an icon and text, for content that does not exist yet."""
    with ui.column().classes("mls-placeholder w-full items-center gap-1"):
        ui.icon(icon, size="22px")
        ui.label(text)


def busy(box: ui.element, text: str) -> None:
    """Replace a box's content with a spinner while a slow call runs."""
    box.clear()

    # Spinner | text
    with box, ui.row().classes("items-center gap-2"):
        ui.spinner(size="md")
        ui.label(text).classes("mls-card-caption")


def failed(box: ui.element, error: Exception) -> None:
    """Show an error in place of a box's content."""
    box.clear()

    with box:
        ui.label(f"Failed: {error}").classes("text-negative text-body2")


async def fill(
    box: ui.element,
    read: Callable[[], Any],
    draw: Callable[[Any], None],
    waiting: str = "Loading …",
) -> Optional[Any]:
    """The usual way to show data: a spinner in ``box`` while ``read()`` runs in a
    worker thread, then ``draw(result)`` into the box, or the error in its place.

    Returns:
        What ``read`` returned, for a page that uses it again; ``None`` after an
        error.
    """
    busy(box, waiting)

    try:
        result = await run.io_bound(read)
    except Exception as e:  # noqa: BLE001  show the error on the page
        failed(box, e)
        return None

    box.clear()

    with box:
        draw(result)

    return result


def not_implemented(action: str) -> None:
    """Default handler for buttons whose service call is not wired yet."""
    ui.notify(
        f"{action}: not implemented yet (UI scaffold).",
        type="info",
        position="bottom-right",
    )
