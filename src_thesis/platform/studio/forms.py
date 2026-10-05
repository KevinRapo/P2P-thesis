"""Editing the draft experiment file from page controls.

A page binds each control to a dotted path in the file (``market.mechanism``).
"Apply" sends only the controls the user changed to ``ConfigService.update``,
so fields left at their defaults stay unset in the file, and saves the result
to the library (drafts autosave, 05 §5).
"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from src_thesis.platform.services.models import ExperimentFile

from src_thesis.platform.studio.state import flash, open_draft, services


class DraftForm:
    """Ties page controls to fields of the draft experiment file.

    Args:
        draft: The file the page shows.
    """

    def __init__(self, draft: ExperimentFile) -> None:
        self.draft = draft
        self._fields: dict[str, tuple[Callable[[], Any], Any]] = {}
        self.elements: list[Any] = []  # bound controls, to listen for changes

    def bind(
        self, path: str, element: Any, cast: Callable[[Any], Any] | None = None
    ) -> Any:
        """Register ``element`` as the editor of ``path``; returns the element.

        An empty control (``None``) is written as ``null``; ``cast`` converts every
        other value (e.g. ``float``).
        """
        self.track(path, lambda: self._read(element, cast))
        self.elements.append(element)
        return element

    def track(self, path: str, read: Callable[[], Any]) -> None:
        """Register any value as the content of ``path``, e.g. a picked network.

        Args:
            path: Dotted path in the file.
            read: Returns the current value; called now (initial value) and on apply.
        """
        self._fields[path] = (read, read())

    @staticmethod
    def _read(element: Any, cast: Callable[[Any], Any] | None) -> Any:
        value = element.value
        if value == "" and cast is not None:  # a cleared number field
            return None
        return cast(value) if cast and value is not None else value

    def changes(self) -> dict[str, Any]:
        """Paths whose value differs from the value shown when the page opened."""
        out = {}
        for path, (read, initial) in self._fields.items():
            value = read()
            if value != initial:
                out[path] = value
        return out

    def apply(self) -> None:
        """Save the changed fields to the draft and reload the page.

        Only controls whose value changed are sent to ``ConfigService.update``. If the
        result is invalid, the error is shown and nothing is saved.
        """
        changes = self.changes()
        if not changes:
            ui.notify("No changes to apply")
            return
        self.save(changes)

    def save(self, changes: dict[str, Any]) -> None:
        """Write ``changes`` (dotted path -> value) to the draft and reload the page."""
        save_changes(self.draft, changes)


def save_changes(draft: ExperimentFile, changes: dict[str, Any]) -> None:
    """Write ``changes`` (dotted path -> value) to ``draft``, then reload the page.

    Shows the error instead and saves nothing if the result is invalid.
    """
    config = services().config
    try:
        updated = config.update(draft, changes)
        open_draft(updated)
    except (ValueError, OSError) as error:
        ui.notify(f"Not applied: {error}", type="negative", multi_line=True)
        return
    n = len(config.diff(draft, updated))
    flash(f"Applied {n} change{'s' * (n != 1)} to {updated.meta.id}")
    ui.navigate.reload()


def date_input(label: str, value: str | None) -> ui.input:
    """A ``YYYY-MM-DD`` text field with a calendar behind its icon."""
    with ui.input(label, value=value or "") as field:
        with ui.menu().props("no-parent-event") as menu:
            with ui.date(mask="YYYY-MM-DD").bind_value(field):
                with ui.row().classes("justify-end"):
                    ui.button("Close", on_click=menu.close).props("flat")
        with field.add_slot("append"):
            ui.icon("edit_calendar").on("click", menu.open).classes("cursor-pointer")
    return field
