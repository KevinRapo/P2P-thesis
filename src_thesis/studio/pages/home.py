"""Home (04 §4.1): health, recent work, start points."""

from nicegui import ui

from ..components import data_table, section, stat, stat_grid, state_color
from ..layout import shell
from ..state import open_draft, services


@ui.page("/")
def home_page() -> None:
    s = services()
    with shell(
        "home", "Home", "Status of the repository, recent work and quick starts"
    ):
        health = s.experiments.health()
        runs = s.experiments.list_runs()
        with stat_grid():
            stat(
                "Validation plan",
                f"{health.validation_progress:.0%}",
                "issues closed (80 total)",
                "rule",
            )
            stat(
                "Runs",
                str(len(runs)),
                f"{sum(r.state.value == 'RUNNING' for r in runs)} running",
                "play_circle",
            )
            stat(
                "Experiment files",
                str(len(s.config.list())),
                "presets and drafts",
                "description",
            )
            stat(
                "Environment",
                "OK" if health.dependencies_ok else "check",
                "dependencies",
                "verified",
                tone="positive" if health.dependencies_ok else "negative",
            )

        with ui.row().classes("w-full gap-4 items-stretch"):
            with section(
                "Start",
                "Create a draft from a preset or open an existing file",
                "rocket_launch",
                classes="grow basis-0",
            ):
                presets = s.config.list(kind="preset")
                for p in presets:
                    with ui.row().classes(
                        "items-center justify-between w-full no-wrap"
                    ):
                        with ui.column().classes("gap-0"):
                            ui.label(p.name).classes("text-body2 text-weight-medium")
                            ui.label(p.path).classes("mls-card-caption mls-mono")
                        ui.button(
                            "New draft",
                            icon="add",
                            on_click=lambda pid=p.id: (
                                open_draft(s.config.new_from_preset(pid)),
                                ui.navigate.to("/build/grid"),
                            ),
                        ).props("flat dense no-caps")
            with section(
                "Recent runs",
                "Latest executions across experiments",
                "history",
                classes="grow basis-0",
            ):
                rows = [
                    {
                        "id": r.run_id,
                        "cell": f"{r.cell.algorithm.upper()} · {r.cell.paradigm.upper()} · s{r.cell.seed}",
                        "state": r.state.value,
                        "state_color": state_color(r.state.value),
                        "progress": f"{r.progress:.0%}",
                    }
                    for r in runs[:6]
                ]
                table = data_table(
                    rows,
                    [("cell", "Cell"), ("state", "State"), ("progress", "Progress")],
                    badge_columns={"state": "state_color"},
                    pagination=0,
                )
                table.on(
                    "rowClick", lambda e: ui.navigate.to(f"/results/{e.args[1]['id']}")
                )

        with section("Messages", icon="info"):
            for message in health.messages:
                with ui.row().classes("items-center gap-2"):
                    ui.icon("chevron_right", size="18px").classes("text-grey")
                    ui.label(message).classes("text-body2")
