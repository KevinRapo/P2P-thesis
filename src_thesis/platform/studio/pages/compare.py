"""Compare (05 §6): the 3 × 3 matrix view and run overlays."""

from nicegui import ui

from src_thesis.platform.studio.components.charts import heatmap_figure, line_figure
from src_thesis.platform.studio.components.cards import section
from src_thesis.platform.studio.layout import shell
from src_thesis.platform.studio.state import services

_METRICS = {
    "p2p_share": "P2P share",
    "served_demand_share": "Served demand",
    "voltage_violations": "Voltage violations",
    "losses_kwh": "Losses",
    "rl_return": "RL return",
}


@ui.page("/compare")
def compare_page() -> None:
    """Compare (05 §6): the algorithm × paradigm matrix and run overlays. Sample data
    until R7.
    """
    s = services()
    with shell("compare", "Compare", "Paradigm × algorithm matrix and run overlays"):
        with ui.row().classes("w-full gap-2 items-center"):
            # Placeholder: the experiment list is fixed and the paper-reference switch
            # does nothing yet.
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
                # Overlay of the first three runs (sample data).
                runs = [r.run_id for r in s.experiments.list_runs()][:3]
                ui.plotly(
                    line_figure(s.results.compare(runs, metric.value), height=320)
                ).classes("w-full")
                ui.label(
                    "Runs with different reward versions are marked non-comparable."
                ).classes("mls-card-caption")

        def render() -> None:
            """Redraw the matrix for the chosen experiment and metric."""
            matrix_box.clear()
            with matrix_box:
                ui.plotly(
                    heatmap_figure(
                        s.results.matrix(experiment.value, metric.value), height=320
                    )
                ).classes("w-full")

        # Changing the metric redraws the matrix; the overlay keeps the first metric.
        metric.on_value_change(lambda: render())
        render()
