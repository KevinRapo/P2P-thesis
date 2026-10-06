"""Validate (05 §6): is the draft sound, and does the network respond as expected?

Three tabs: the file's own findings, sanity scenarios (fixture days with a stated
expectation, run on the draft's own network and participants) and a dry run.
Checks of an actual run are on the Simulate and Results pages.
"""

from nicegui import run, ui

from src_thesis.platform.studio.components.cards import section, stat, stat_grid
from src_thesis.platform.studio.components.charts import line_figure
from src_thesis.platform.studio.layout import shell
from src_thesis.platform.studio.state import current_draft, services

_ICONS = {
    "error": ("error", "negative"),
    "warning": ("warning", "warning"),
    "info": ("info", "info"),
}
# Page that fixes a finding of each area; clicking a finding opens it.
_AREA_ROUTES = {
    "grid": "/build/grid",
    "participants": "/build/grid?tab=participants",
    "market": "/build/market",
    "dso": "/build/market",
    "learning": "/build/rl",
    "time": "/build/grid?tab=participants",
}


@ui.page("/experiment/validate")
def validate_page() -> None:
    """Validate (05 §6): file findings, sanity scenarios and a dry run."""
    s = services()
    draft = current_draft()
    with shell(
        "validate",
        "Validate",
        "Is the draft sound, and does the chosen network respond the way it should?",
    ):
        report = s.validation.validate(draft, level="full")
        counts = {
            k: sum(f.severity.value == k for f in report.findings)
            for k in ("error", "warning", "info")
        }
        with stat_grid():
            stat(
                "Errors", str(counts["error"]), "block a run", "error", tone="negative"
            )
            stat(
                "Warnings",
                str(counts["warning"]),
                "worth reading",
                "warning",
                tone="warning",
            )
            stat("Info", str(counts["info"]), "", "info", tone="info")
            stat("File hash", report.file_hash, report.level, "fingerprint")

        with ui.tabs().classes("w-full").props("align=left no-caps") as tabs:
            ui.tab("file", label="File", icon="rule")
            ui.tab("scenarios", label="Sanity scenarios", icon="science")
            ui.tab("dry", label="Dry run", icon="play_arrow")
        with ui.tab_panels(tabs, value="file").classes("w-full"):
            with ui.tab_panel("file"):
                _file_tab(report)
            with ui.tab_panel("scenarios"):
                _scenarios_tab(draft, report.ok)
            with ui.tab_panel("dry"):
                _dry_tab(draft, report.ok)

        with ui.row().classes("justify-end w-full gap-2"):
            ui.button(
                "Simulate this file",
                icon="slideshow",
                on_click=lambda: ui.navigate.to("/simulate"),
            ).props("unelevated" + ("" if report.ok else " disable"))
            ui.label(
                "Disabled while the file has errors."
                if not report.ok
                else "Training runs come with the RL part; simulation runs work now."
            ).classes("mls-card-caption self-center")


def _file_tab(report) -> None:
    with section(
        "Findings",
        "Click a finding to open the field. Errors block a run; warnings are kept "
        "with the results.",
        "rule",
    ):
        for f in sorted(
            report.findings,
            key=lambda x: ["error", "warning", "info"].index(x.severity.value),
        ):
            icon, color = _ICONS[f.severity.value]
            route = _AREA_ROUTES.get(f.area, "/build/summary")
            with ui.item(on_click=lambda r=route: ui.navigate.to(r)).classes(
                "w-full rounded-borders"
            ):
                with ui.item_section().props("avatar"):
                    ui.icon(icon, color=color)
                with ui.item_section():
                    ui.item_label(f.message)
                    ui.item_label(
                        f"{f.code} · {f.path}"
                        + (f" · {f.fix_hint}" if f.fix_hint else "")
                    ).props("caption").classes("mls-mono")


def _scenarios_tab(draft, ok: bool) -> None:
    s = services()
    ui.label(
        "A scenario replaces the participants' profiles with a simple fixture, "
        "runs a day with a scripted controller on this network, and checks what "
        "physics says must happen. A failed scenario points at the pipeline "
        "(profiles, settlement, injections, power flow), not at a controller."
    ).classes("mls-card-caption")
    for scenario in s.validation.scenarios():
        with section(scenario.title, scenario.expected, "science"):
            box = ui.column().classes("w-full gap-1")

            async def run_it(scenario=scenario, box=box) -> None:
                box.clear()
                with box:
                    ui.spinner()
                out = await run.io_bound(s.validation.run_scenario, draft, scenario.id)
                box.clear()
                with box:
                    if out.error:
                        ui.label(out.error).classes("text-negative")
                        return
                    ui.label("passed" if out.passed else "failed").classes(
                        "text-positive" if out.passed else "text-negative"
                    )
                    for e in out.expectations:
                        with ui.row().classes("items-center gap-2 no-wrap"):
                            ui.icon(
                                "check_circle" if e.passed else "cancel",
                                color="positive" if e.passed else "negative",
                            )
                            with ui.column().classes("gap-0"):
                                ui.label(e.statement).classes("text-body2")
                                ui.label(e.detail).classes("mls-card-caption")
                    if out.series:
                        ui.plotly(line_figure(out.series, height=280)).classes("w-full")

            ui.button("Run scenario", icon="play_arrow", on_click=run_it).props(
                "outline" + ("" if ok else " disable")
            )


def _dry_tab(draft, ok: bool) -> None:
    s = services()
    with section(
        "Dry run",
        "Builds the world of one day and takes the first step with nobody ordering.",
        "play_arrow",
    ):
        box = ui.column().classes("w-full gap-1")

        async def dry_run() -> None:
            box.clear()
            with box:
                ui.spinner()
            result = await run.io_bound(s.validation.dry_run, draft)
            box.clear()
            with box:
                ui.label("passed" if result.ok else "failed").classes(
                    "text-positive" if result.ok else "text-negative"
                )
                ui.label(
                    f"power flow converged: {result.power_flow_converged}"
                ).classes("text-body2")
                for message in result.messages:
                    ui.label(message).classes("mls-card-caption")

        ui.button("Run dry run", icon="play_arrow", on_click=dry_run).props(
            "outline" + ("" if ok else " disable")
        )
