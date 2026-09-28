"""Access to services and the per-user draft experiment file.

The Studio holds no research state of its own: services own the data, and the
browser session only remembers which draft is open (04-presentation.md §2).
"""

import os

from nicegui import app

from src_thesis.application import Services, build_services
from src_thesis.application.models import ExperimentFile

_SERVICES: Services | None = None
DEFAULT_PRESET = "case6-3x3"


def services() -> Services:
    """The process-wide services.

    The grid catalog is real (SimBench / pandapower) unless MARLEM_STUDIO_GRID=demo,
    and experiment files are real files in the workspace library (outside OneDrive,
    MARLEM_HOME to move it) unless MARLEM_STUDIO_CONFIG=demo. Everything else is
    demo data until its roadmap phase.
    """
    global _SERVICES
    if _SERVICES is None:
        grid = os.environ.get("MARLEM_STUDIO_GRID", "pandapower")
        config = os.environ.get("MARLEM_STUDIO_CONFIG", "files")
        _SERVICES = build_services(
            "demo",
            grid="demo" if grid == "demo" else "pandapower",
            config="demo" if config == "demo" else "files",
        )
    return _SERVICES


def current_draft() -> ExperimentFile:
    """The experiment file the Build and Experiment pages edit.

    A new browser session continues the most recently changed library file, so
    the library only grows when the user starts something new.
    """
    draft_id = app.storage.user.get("draft_id")
    if draft_id:
        try:
            return services().config.load(draft_id)
        except FileNotFoundError:  # deleted, or remembered from the demo service
            pass
    drafts = services().config.list(kind="draft")
    if drafts:
        latest = max(drafts, key=lambda d: d.modified)
        app.storage.user["draft_id"] = latest.id
        return services().config.load(latest.id)
    draft = services().config.new_from_preset(DEFAULT_PRESET)
    app.storage.user["draft_id"] = draft.meta.id
    return draft


def open_draft(file: ExperimentFile) -> None:
    services().config.save(file)
    app.storage.user["draft_id"] = file.meta.id
