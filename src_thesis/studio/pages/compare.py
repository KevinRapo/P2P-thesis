"""Compare (05 §4.10): the 3 × 3 matrix view and run overlays."""

from nicegui import ui

from ..components import heatmap_figure, line_figure, section
from ..layout import shell
from ..state import services

_METRICS = {
    "p2p_share": "P2P share",
    "served_demand_share": "Served demand",
    "voltage_violations": "Voltage violations",
    "losses_kwh": "Losses",
    "rl_return": "RL return",
}


@ui.page("/compare")
def compare_page() -> None:
    s = services()
    with shell("compare", "Compare", "Paradigm × algorithm matrix and run overlays"):
        with ui.row().classes("w-full gap-2 items-center"):
            experiment = ui.select(
                ["case6-3x3"], value="case6-3x3", label="Experiment"
            ).classes("w-56")
            metric = ui.select(_METRICS, value="p2p_share", label="Metric").classes(
                "w-56"
            )
            ui.switch("Show paper reference", value=False)

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Matrix", "Mean ± std over seeds", "grid_on", classes="grow basis-0"
            ):
                matrix_box = ui.column().classes("w-full")
            with section(
                "Overlay",
                "Evaluation curves of the selected runs",
                "stacked_line_chart",
                classes="grow basis-0",
            ):
                runs = [r.run_id for r in s.experiments.list_runs()][:3]
                ui.plotly(
                    line_figure(s.results.compare(runs, metric.value), height=320)
                ).classes("w-full")
                ui.label(
                    "Runs with different reward versions are marked non-comparable."
                ).classes("mls-card-caption")

        def render() -> None:
            matrix_box.clear()
            with matrix_box:
                ui.plotly(
                    heatmap_figure(
                        s.results.matrix(experiment.value, metric.value), height=320
                    )
                ).classes("w-full")

        metric.on_value_change(lambda: render())
        render()
