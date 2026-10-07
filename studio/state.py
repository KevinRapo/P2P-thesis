"""What the Studio holds: the services. The scenario and the market live in them
(``services().scenario``, ``services().market``)."""

from __future__ import annotations

from studio.adapters.container import Services, build_services

_SERVICES: Services | None = None


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
