"""Griffe extension for the API reference: modules show their classes and functions.

Module-level variables (constants, tables, loggers) are left out of the API pages:
they are implementation detail, and the code they belong to documents them where
they are used. Attributes of a class (a dataclass's fields included) stay, since
they are part of the class.
"""

from __future__ import annotations

from typing import Any

import griffe


class ClassesAndFunctions(griffe.Extension):
    """Remove every module's own attributes once its package is loaded."""

    def on_package(self, *, pkg: griffe.Module, **kwargs: Any) -> None:
        self._prune(pkg)

    def _prune(self, module: griffe.Module) -> None:
        for name, member in list(module.members.items()):
            if member.is_alias:
                continue  # an import: shown or not by the module's own options
            if member.is_module:
                self._prune(member)
            elif member.is_attribute:
                del module.members[name]
