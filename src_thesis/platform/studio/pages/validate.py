"""Validate (05 §6): preflight report, dry run, and the only launch point."""

from nicegui import ui

from src_thesis.platform.studio.components.cards import section, stat, stat_grid
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
    "participants": "/build/participants",
    "market": "/build/market",
    "dso": "/build/market",
    "learning": "/build/rl",
    "time": "/build/participants",
}


@ui.page("/experiment/validate")
def validate_page() -> None:
    """Validate (05 §6): preflight report, dry run and launch. Sample validation until
    R7.
    """
    s = services()
    draft = current_draft()
    with shell(
        "validate",
        "Validate",
        "Preflight of the draft experiment file; launch is enabled only without errors",
    ):
        # ValidationService returns sample data: the findings are fixed samples until R7.
        report = s.validation.validate(draft, level="full")
        counts = {
            k: sum(f.severity.value == k for f in report.findings)
            for k in ("error", "warning", "info")
        }
        with stat_grid():
            stat(
                "Errors",
                str(counts["error"]),
                "block the launch",
                "error",
                tone="negative",
            )
            stat(
                "Warnings",
                str(counts["warning"]),
                "shown in results",
                "warning",
                tone="warning",
            )
            stat("Info", str(counts["info"]), "", "info", tone="info")
            stat("File hash", report.file_hash, report.level, "fingerprint")

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Findings",
                "Click a finding to open the field",
                "rule",
                classes="grow basis-0",
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
            with section(
                "Dry run",
                "One step through the environment factory",
                "science",
                classes="basis-1/3 min-w-0",
            ):
                dry_box = ui.column().classes("w-full gap-1")

                def dry_run() -> None:
                    """Run the dry run and show what it checked (sample result until
                    R7).
                    """
                    result = s.validation.dry_run(draft)
                    dry_box.clear()
                    with dry_box:
                        ui.label("passed" if result.ok else "failed").classes(
                            "text-positive" if result.ok else "text-negative"
                        )
                        ui.label(
                            f"power flow converged: {result.power_flow_converged}"
                        ).classes("text-body2")
                        ui.label(
                            f"settlement residual: {result.settlement_residual_kwh} kWh"
                        ).classes("text-body2")
                        for message in result.messages:
                            ui.label(message).classes("mls-card-caption")

                ui.button("Run dry run", icon="play_arrow", on_click=dry_run).props(
                    "outline"
                )

        with ui.row().classes("justify-end w-full gap-2"):

            def launch() -> None:
                """Create and start one run per cell, then open Runs. Sample data: nothing
                actually starts.
                """
                run_ids = s.experiments.create_runs(draft)
                s.experiments.start(run_ids)
                ui.notify(
                    f"{len(run_ids)} runs created (sample data).", type="positive"
                )
                ui.navigate.to("/runs")

            # Disabled while the report has errors: Validate is the only way to Runs (05
            # §3).
            ui.button("Launch runs", icon="rocket_launch", on_click=launch).props(
                "unelevated" + ("" if report.ok else " disable")
            )
