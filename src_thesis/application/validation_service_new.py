"""Facade for UI-independent scenario and model validation."""

from typing import Any


class ValidationService:
    """Run validation rules and return a structured validation report."""

    def validate(self, scenario: Any) -> Any:
        raise NotImplementedError
