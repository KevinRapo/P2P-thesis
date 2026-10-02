"""Editing the draft experiment file from page controls.

A page binds each control to a dotted path in the file (``market.mechanism``).
"Apply" sends only the controls the user changed to ``ConfigService.update``,
so fields left at their defaults stay unset in the file, and saves the result
to the library (drafts autosave, 04 §2).
"""

from __future__ import annotations

from typing import Any, Callable

from nicegui import ui

from src_thesis.application.models import ExperimentFile

from .state import flash, open_draft, services


class DraftForm:
    def __init__(self, draft: ExperimentFile) -> None:
        self.draft = draft
        self._fields: dict[str, tuple[Any, Callable[[Any], Any] | None, Any]] = {}

    def bind(
        self, path: str, element: Any, cast: Callable[[Any], Any] | None = None
    ) -> Any:
        """Register ``element`` as the editor of ``path``; returns the element."""
        self._fields[path] = (element, cast, self._read(element, cast))
        return element

    @staticmethod
    def _read(element: Any, cast: Callable[[Any], Any] | None) -> Any:
        value = element.value
        return cast(value) if cast and value is not None else value

    def changes(self) -> dict[str, Any]:
        """Paths whose control differs from the value shown when the page opened."""
        out = {}
        for path, (element, cast, initial) in self._fields.items():
            value = self._read(element, cast)
            if value != initial:
                out[path] = value
        return out

    def apply(self) -> None:
        changes = self.changes()
        if not changes:
            ui.notify("No changes to apply")
            return
        config = services().config
        try:
            updated = config.update(self.draft, changes)
            open_draft(updated)
        except (ValueError, OSError) as error:
            ui.notify(f"Not applied: {error}", type="negative", multi_line=True)
            return
        n = len(config.diff(self.draft, updated))
        flash(f"Applied {n} change{'s' * (n != 1)} to {updated.meta.id}")
        ui.navigate.reload()
