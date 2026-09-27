"""Results (05 §4.9): one run; research outcomes kept apart from RL return."""

from nicegui import ui

from ..components import (
    data_table,
    key_values,
    line_figure,
    not_implemented,
    section,
    stat,
    stat_grid,
    state_color,
    topology_figure,
)
from ..layout import shell
from ..state import services
from src_thesis_implement.application.models import NetworkSource

_OUTCOME_LABELS = {
    "served_demand_share": ("Served demand", "{:.1%}"),
    "unmet_demand_kwh": ("Unmet demand", "{} kWh"),
    "curtailment_kwh": ("Curtailment", "{} kWh"),
    "p2p_share": ("P2P share", "{:.1%}"),
    "total_cost": ("Total cost", "{:,.0f}"),
    "voltage_violations": ("Voltage violations", "{:.0f}"),
    "losses_kwh": ("Losses", "{} kWh"),
}


@ui.page("/results")
def results_index_page() -> None:
    s = services()
    with shell("results", "Results", "Pick a run"):
        rows = [
            {
                "id": r.run_id,
                "experiment": r.experiment_id,
                "cell": f"{r.cell.algorithm.upper()} · {r.cell.paradigm.upper()} · s{r.cell.seed}",
                "state": r.state.value,
                "state_color": state_color(r.state.value),
            }
            for r in s.experiments.list_runs()
        ]
        with section("Runs", icon="insights"):
            table = data_table(
                rows,
                [
                    ("experiment", "Experiment"),
                    ("cell", "Cell"),
                    ("state", "State"),
                    ("id", "Run id"),
                ],
                badge_columns={"state": "state_color"},
                pagination=15,
            )
            table.on(
                "rowClick", lambda e: ui.navigate.to(f"/results/{e.args[1]['id']}")
            )


@ui.page("/results/{run_id}")
def results_page(run_id: str) -> None:
    s = services()
    with shell("results", "Results", run_id):
        result = s.results.summary(run_id)
        with ui.tabs().classes("w-full").props("align=left no-caps") as tabs:
            for name, label, icon in [
                ("overview", "Overview", "dashboard"),
                ("learning", "Learning", "trending_up"),
                ("replay", "Episode replay", "slideshow"),
                ("grid", "Grid", "hub"),
                ("agents", "Agents", "groups"),
                ("export", "Export", "download"),
            ]:
                ui.tab(name, label=label, icon=icon)
        with ui.tab_panels(tabs, value="overview").classes("w-full"):
            with ui.tab_panel("overview").classes("gap-4"):
                ui.label("Research outcomes").classes("mls-stat-label")
                with stat_grid():
                    for key, value in result.outcomes.items():
                        label, fmt = _OUTCOME_LABELS.get(key, (key, "{}"))
                        stat(label, fmt.format(value))
                ui.label("Learning signal (not a research outcome)").classes(
                    "mls-stat-label q-mt-md"
                )
                with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
                    with ui.column().classes("basis-1/4 min-w-0"):
                        stat(
                            "RL return",
                            f"{result.rl_return}",
                            "mean evaluation return",
                            "psychology",
                            tone="secondary",
                        )
                    with section(
                        "Run manifest",
                        "Provenance of this run",
                        "fingerprint",
                        classes="grow basis-0",
                    ):
                        key_values(result.manifest)
            with ui.tab_panel("learning"):
                with section(
                    "Training and evaluation return",
                    "Baselines drawn as reference lines",
                    "trending_up",
                ):
                    ui.plotly(
                        line_figure(
                            s.results.training_curve(run_id),
                            height=360,
                            dashed=("no_order baseline", "random baseline"),
                        )
                    ).classes("w-full")
            with ui.tab_panel("replay"):
                records = s.results.step_records(run_id)
                with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
                    with section("Step", icon="slideshow", classes="basis-1/3 min-w-0"):
                        step = ui.slider(min=0, max=len(records) - 1, value=18).props(
                            "label-always"
                        )
                        step_box = ui.column().classes("w-full gap-1")
                    with section(
                        "Grid at this step", icon="hub", classes="grow basis-0"
                    ):
                        grid_box = ui.column().classes("w-full")

                def show_step() -> None:
                    record = records[int(step.value)]
                    step_box.clear()
                    with step_box:
                        for k, v in record.items():
                            with ui.row().classes("justify-between w-full"):
                                ui.label(k.replace("_", " ")).classes(
                                    "mls-card-caption"
                                )
                                ui.label(str(v)).classes("text-body2")
                    source = NetworkSource(type="simbench", code="1-LV-semiurb4--0-sw")
                    preview = s.grid.preview_powerflow(
                        source, "2016-06-15", int(step.value)
                    )
                    grid_box.clear()
                    with grid_box:
                        ui.plotly(
                            topology_figure(
                                s.grid.topology(source),
                                voltages=preview.bus_voltage_pu,
                                height=380,
                            )
                        ).classes("w-full")

                step.on_value_change(lambda: show_step())
                show_step()
                with section("All steps", icon="table_rows"):
                    data_table(records, row_key="step", pagination=24)
            with ui.tab_panel("grid"):
                with section("Voltage band and loading over the episode", icon="hub"):
                    ui.plotly(
                        line_figure(s.results.grid_series(run_id), height=360)
                    ).classes("w-full")
            with ui.tab_panel("agents"):
                with section("Battery state of charge", icon="battery_charging_full"):
                    ui.plotly(
                        line_figure(s.results.agent_series(run_id), height=340)
                    ).classes("w-full")
            with ui.tab_panel("export"):
                with section("Export", "Raw series and figures", "download"):
                    with ui.row().classes("gap-2"):
                        ui.button(
                            "CSV",
                            icon="table_view",
                            on_click=lambda: ui.notify(
                                s.results.export([run_id], "csv")
                            ),
                        ).props("outline")
                        ui.button(
                            "JSON",
                            icon="data_object",
                            on_click=lambda: ui.notify(
                                s.results.export([run_id], "json")
                            ),
                        ).props("outline")
                        ui.button(
                            "Figures",
                            icon="image",
                            on_click=lambda: not_implemented("Export figures"),
                        ).props("outline")
