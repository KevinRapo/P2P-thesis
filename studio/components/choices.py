"""Dropdowns that show their choices plainly."""

from __future__ import annotations

from nicegui import ui

# An option of a multiple choice as a ticked or empty box; a click on the row ticks
# it, so the box itself takes no clicks (two toggles would cancel out).
_CHECKBOX = """
<q-item v-bind="props.itemProps">
  <q-item-section side>
    <q-checkbox :model-value="props.selected" class="no-pointer-events" dense />
  </q-item-section>
  <q-item-section>
    <q-item-label>{{ props.opt.label }}</q-item-label>
  </q-item-section>
</q-item>
"""


def checkboxes(select: ui.select) -> ui.select:
    """A multiple-choice dropdown with a tick box per option in its list and the chosen
    ones as chips in the field, so what is chosen shows without opening it."""
    select.add_slot("option", _CHECKBOX)

    return select.props("use-chips")
