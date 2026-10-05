"""Access to services and the per-user draft experiment file.

The Studio holds no research state of its own: services own the data, and the
browser session only remembers which draft is open (05-presentation.md §5).
"""

from nicegui import app

from src_thesis.platform.services.container import Services, build_services
from src_thesis.platform.services.models import ExperimentFile, NetworkSource

_SERVICES: Services | None = None
DEFAULT_PRESET = "case6-3x3"


def services() -> Services:
    """The process-wide services.

    Built once per process, on the workspace chosen on the Settings page.
    Services that are not built yet return sample data (``Services.sample_data``).
    """
    global _SERVICES
    if _SERVICES is None:
        _SERVICES = build_services()
    return _SERVICES


def reset_services() -> None:
    """Rebuild the services on next use (e.g. after the workspace moved)."""
    global _SERVICES
    _SERVICES = None


def current_draft() -> ExperimentFile:
    """The experiment file the Build and Experiment pages edit.

    A new browser session continues the most recently changed library file, so
    the library only grows when the user starts something new.
    """
    draft_id = app.storage.user.get("draft_id")
    if draft_id:
        try:
            return services().config.load(draft_id)
        except FileNotFoundError:  # deleted since this browser last opened it
            pass
    drafts = services().config.list(kind="draft")
    if drafts:
        latest = max(drafts, key=lambda d: d.modified)
        app.storage.user["draft_id"] = latest.id
        return services().config.load(latest.id)
    draft = services().config.new_from_preset(DEFAULT_PRESET)
    app.storage.user["draft_id"] = draft.meta.id
    return draft


def draft_network(file: ExperimentFile, default: dict[str, str]) -> NetworkSource:
    """The network the draft uses (``grid.source``), else ``default``."""
    source = file.grid.source
    if source and source.type and source.code:
        return NetworkSource(type=source.type, code=source.code)
    return NetworkSource(**default)


def open_draft(file: ExperimentFile) -> None:
    """Save ``file`` and make it the draft this browser session edits."""
    services().config.save(file)
    app.storage.user["draft_id"] = file.meta.id


def flash(message: str, kind: str = "positive") -> None:
    """A notification shown on the next page load (survives a reload)."""
    app.storage.user["flash"] = [message, kind]


def pop_flash() -> tuple[str, str] | None:
    """Take the pending flash notification, if any; the page shell shows it."""
    item = app.storage.user.pop("flash", None)
    return (item[0], item[1]) if item else None
