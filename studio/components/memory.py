"""What a browser remembers of a page between visits.

Every visit builds a page anew, so what it shows has to come back from somewhere: the
choices that decide it (a tab, a dropdown, the ticked runs) are kept in
``app.storage.user``, per browser, in the workspace's ``studio-state/`` folder. They
survive moving between pages, a restart of the server and closing the browser. The
scenario, the experiment and the market are not kept here: they live in the services
(``studio/state.py``).

Keys are ``<page>_<what>``. Only a choice that is connected here is remembered.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from typing import Any, Optional, Union

from nicegui import app
from nicegui.elements.choice_element import ChoiceElement
from nicegui.elements.mixins.value_element import ValueElement

Allowed = Union[Collection, Callable[[Any], bool]]


def _fits(value: Any, allowed: Optional[Allowed]) -> bool:
    if allowed is None:
        return True

    return allowed(value) if callable(allowed) else value in allowed


def recalled(key: str, default: Any = None, allowed: Optional[Allowed] = None) -> Any:
    """The value kept under ``key``; ``default`` without one, or if ``allowed`` (the
    values that can be used now, or a test of a value) rules it out."""
    store = app.storage.user

    if key in store and _fits(store[key], allowed):
        return store[key]

    return default


def keep(key: str, value: Any) -> None:
    """Keep ``value`` under ``key``; the same value again writes nothing."""
    store = app.storage.user

    if key not in store or store[key] != value:
        store[key] = value


def remember(
    control: ValueElement, key: str, allowed: Optional[Allowed] = None
) -> ValueElement:
    """Bring back ``control``'s value and keep it from now on.

    Call it before connecting the control's handlers, so that bringing the value
    back runs none of them: the page then reads the control as it builds. A control
    with one choice can only take a value it offers, so that is what is allowed; a
    control filled later brings its value back after that.
    """
    single = not getattr(control, "multiple", False)

    if allowed is None and isinstance(control, ChoiceElement) and single:
        allowed = control.options

    control.value = recalled(key, control.value, allowed)
    control.on_value_change(lambda e: keep(key, e.value))

    return control
