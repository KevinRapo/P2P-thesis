"""The checks of a simulated run, grouped so a red row is never misread."""

from collections.abc import Callable

from nicegui import ui

from src_thesis.platform.services.models import CheckResult
from src_thesis.platform.studio.components.cards import section

# severity -> (title, what a failure means, icon and colour when failed)
GROUPS = {
    "invariant": (
        "Invariants",
        "Must hold for any correct engine. A failure here is a bug in the engine, "
        "the adapter or the experiment file.",
        ("error", "negative"),
    ),
    "engine_fault": (
        "Known faults of the original market",
        "Documented defects of the original market (issue IDs from the register). "
        "They are expected to show up while the original engine is used and will "
        "disappear with a clean engine.",
        ("bug_report", "warning"),
    ),
    "physical": (
        "Network limits",
        "What the day did to the grid (voltage, loading, power flow). Not bugs: "
        "this is the result the simulation is for.",
        ("bolt", "info"),
    ),
}


def checks_panel(
    checks: list[CheckResult], on_jump: Callable[[str, int], None] | None = None
) -> None:
    """List every check with its failures, in three groups.

    Args:
        checks: From ``ResultService.checks``.
        on_jump: Called with ``(day, step)`` when a failing check's step button is
            clicked, e.g. to move a replay there.
    """
    for severity, (title, meaning, (icon, color)) in GROUPS.items():
        rows = [c for c in checks if c.severity == severity]
        failed = sum(1 for c in rows if c.failures)
        with section(
            title,
            meaning,
            icon,
            classes="w-full",
        ):
            ui.label(
                "all passed" if not failed else f"{failed} of {len(rows)} failed"
            ).classes("text-positive" if not failed else f"text-{color}")
            for c in rows:
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    if c.failures:
                        ui.icon(icon, color=color)
                    else:
                        ui.icon("check_circle", color="positive")
                    with ui.column().classes("gap-0 grow"):
                        ui.label(c.title).classes("text-body2")
                        ui.label(c.explanation).classes("mls-card-caption")
                    if c.issue:
                        ui.chip(c.issue).props("dense outline")
                    if c.failures:
                        ui.label(f"{c.failures}×").classes("mls-mono")
                        if on_jump and c.first_step is not None and c.first_day:
                            ui.button(
                                f"step {c.first_step}",
                                on_click=lambda c=c: on_jump(c.first_day, c.first_step),
                            ).props("flat dense no-caps")
