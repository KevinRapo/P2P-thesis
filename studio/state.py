"""What the Studio holds: the services, the scenario being edited and its session."""

from __future__ import annotations

from config.scenario import Scenario
from services.container import Services, build_services
from simulation.session import StepSession

_SERVICES: Services | None = None

scenario = Scenario()
session: StepSession | None = None


def services() -> Services:
    """The process-wide services, built on first use."""
    global _SERVICES
    if _SERVICES is None:
        _SERVICES = build_services()
    return _SERVICES


def reset_services() -> None:
    """Rebuild the services on next use (e.g. after the workspace moved)."""
    global _SERVICES
    _SERVICES = None
