"""Access to services and the per-user draft experiment file.

The Studio holds no research state of its own: services own the data, and the
browser session only remembers which draft is open (05-studio-ui.md §2).
"""

import os

from nicegui import app

from src_thesis_reference.application import Services, build_services
from src_thesis_reference.application.models import ExperimentFile

_SERVICES: Services | None = None
DEFAULT_PRESET = "case6-3x3"


def services() -> Services:
    """The process-wide services.

    The grid catalog is real (SimBench / pandapower) unless MARLEM_STUDIO_GRID=demo;
    everything else is demo data until its roadmap phase.
    """
    global _SERVICES
    if _SERVICES is None:
        grid = os.environ.get("MARLEM_STUDIO_GRID", "pandapower")
        _SERVICES = build_services(
            "demo", grid="demo" if grid == "demo" else "pandapower"
        )
    return _SERVICES


def current_draft() -> ExperimentFile:
    """The experiment file the Build and Experiment pages edit."""
    draft_id = app.storage.user.get("draft_id")
    if draft_id:
        return services().config.load(draft_id)
    draft = services().config.new_from_preset(DEFAULT_PRESET)
    app.storage.user["draft_id"] = draft.meta.id
    return draft


def open_draft(file: ExperimentFile) -> None:
    services().config.save(file)
    app.storage.user["draft_id"] = file.meta.id
