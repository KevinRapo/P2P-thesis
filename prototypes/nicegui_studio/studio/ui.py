"""NiceGUI presentation layer for the standalone Studio prototype."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import plotly.graph_objects as go
from nicegui import ui

from .domain import GridResult, GridScenario
from .service import RunSnapshot, StudioService


service = StudioService()


def _nav_item(label: str, path: str, icon: str) -> None:
    with ui.link(target=path).classes("no-underline w-full"):
        with ui.item().props("clickable").classes("rounded-lg"):
            with ui.item_section().props("avatar"):
                ui.icon(icon).classes("text-primary")
            with ui.item_section().props("main"):
                ui.label(label)


def _shell(title: str):
    """Shared page shell; domain code never appears here."""

    with ui.header().classes("items-center justify-between bg-slate-900 px-6 py-3"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("electric_bolt", size="md").classes("text-amber-300")
            ui.label("MARLEM Studio test").classes("text-xl font-semibold text-white")
        ui.badge("prototype", color="amber").classes("text-slate-900")
    with ui.left_drawer(value=True).classes("bg-slate-50"):
        ui.label("Research workspace").classes(
            "px-3 pb-3 pt-5 text-xs uppercase tracking-widest text-slate-500"
        )
        _nav_item("Dashboard", "/", "dashboard")
        _nav_item("Grid explorer", "/grid", "account_tree")
        _nav_item("Run history", "/runs", "history")
    with ui.column().classes("mx-auto w-full max-w-7xl gap-5 p-6"):
        ui.label(title).classes("text-3xl font-semibold text-slate-900")
        return ui.column().classes("w-full gap-5")


def _metric_card(label: str, value: str, caption: str) -> None:
    with ui.card().classes("min-w-48 flex-1 border border-slate-200 shadow-sm"):
        ui.label(label).classes("text-sm text-slate-500")
        ui.label(value).classes("text-2xl font-semibold text-slate-900")
        ui.label(caption).classes("text-xs text-slate-500")


def _result_rows(result: GridResult) -> list[dict[str, Any]]:
    return [
        {"metric": "Net household exchange", "value": f"{result.net_household_kw:.2f} kW"},
        {"metric": "Feeder exchange", "value": f"{result.feeder_exchange_kw:.2f} kW"},
        {"metric": "Minimum voltage", "value": f"{result.min_voltage_pu:.4f} pu"},
        {"metric": "Maximum line loading", "value": f"{result.max_line_loading_percent:.2f}%"},
        {"metric": "Transformer loading", "value": f"{result.transformer_loading_percent:.2f}%"},
        {"metric": "Estimated losses", "value": f"{result.losses_kw:.3f} kW"},
    ]


def _voltage_figure(result: GridResult) -> go.Figure:
    buses = [f"Bus {index}" for index in range(len(result.voltage_profile_pu))]
    figure = go.Figure(
        go.Scatter(
            x=buses,
            y=result.voltage_profile_pu,
            mode="lines+markers",
            line={"color": "#2563eb", "width": 3},
            marker={"size": 8},
            customdata=buses,
            selected={"marker": {"color": "#f59e0b", "size": 14}},
            unselected={"marker": {"opacity": 0.35}},
            name="Voltage",
        )
    )
    figure.update_layout(
        title="Illustrative voltage profile",
        yaxis_title="Voltage (pu)",
        yaxis={"range": [0.98, 1.03]},
        margin={"l": 45, "r": 20, "t": 45, "b": 35},
        height=320,
        template="plotly_white",
        dragmode="select",
    )
    return figure


@ui.page("/")
def dashboard() -> None:
    with _shell("Dashboard"):
        latest = service.latest
        with ui.row().classes("w-full flex-wrap gap-4"):
            _metric_card("Prototype status", "Ready", "No MARLEM runtime is connected")
            _metric_card("Runs this session", str(len(service.history)), "In-memory demo history")
            _metric_card(
                "Latest result",
                latest.run_id if latest else "—",
                "Run a scenario in Grid explorer",
            )

        with ui.card().classes("w-full border border-slate-200 shadow-sm"):
            ui.label("What this slice demonstrates").classes("text-lg font-medium")
            ui.markdown(
                """
                This is the first Studio shell, not a simulation replacement. The
                **Grid explorer** sends a typed scenario to an application service,
                receives a typed result, updates a chart, and records a run snapshot.
                The service currently uses a transparent illustrative grid model.
                """
            )
            ui.button(
                "Open grid explorer",
                on_click=lambda: ui.navigate.to("/grid"),
                icon="bolt",
            ).props("color=primary")

        with ui.card().classes("w-full border border-slate-200 shadow-sm"):
            ui.label("Architecture boundary").classes("text-lg font-medium")
            ui.code(
                "NiceGUI pages → StudioService → IllustrativeGridModel → GridResult",
                language="text",
            ).classes("w-full")
            ui.label(
                "The future SimBench/pandapower adapter can replace only the model behind this service."
            ).classes("text-sm text-slate-600")


@ui.page("/grid")
def grid_explorer() -> None:
    with _shell("Grid explorer"):
        with ui.row().classes("w-full items-start gap-5"):
            with ui.card().classes("w-full max-w-sm border border-slate-200 shadow-sm"):
                ui.label("Operating point").classes("text-lg font-medium")
                demand = ui.number(
                    "Household demand (kW)", value=6.0, min=0, max=30, step=0.5
                ).classes("w-full")
                pv = ui.number(
                    "PV generation (kW)", value=5.0, min=0, max=30, step=0.5
                ).classes("w-full")
                battery = ui.number(
                    "Battery discharge (kW)", value=0.0, min=0, max=30, step=0.5
                ).classes("w-full")
                ui.label(
                    "Battery discharge is modelled as reducing household demand."
                ).classes("text-xs text-slate-500")
                with ui.row().classes("gap-2"):
                    run_button = ui.button(
                        "Run power-flow demo", icon="play_arrow"
                    ).props("color=primary")
                    reset_button = ui.button("Reset", icon="restart_alt").props("outline")
                save_button = ui.button(
                    "Save latest JSON snapshot", icon="save"
                ).props("flat")
                status = ui.label("No scenario has been run yet.").classes(
                    "text-sm text-slate-600"
                )

            with ui.column().classes("min-w-0 flex-1 gap-4"):
                with ui.row().classes("w-full flex-wrap gap-4"):
                    metric_min = ui.label("Vmin —").classes("text-lg font-medium")
                    metric_line = ui.label("Line —").classes("text-lg font-medium")
                    metric_losses = ui.label("Losses —").classes("text-lg font-medium")
                with ui.row().classes("w-full items-start gap-4"):
                    figure = ui.plotly(go.Figure()).classes("min-w-0 flex-1")
                    with ui.card().classes("w-72 border border-slate-200 shadow-sm"):
                        ui.label("Selected buses").classes("text-lg font-medium")
                        selection_status = ui.label("Click or box-select buses on the graph.").classes(
                            "text-xs text-slate-500"
                        )
                        selected_columns = [
                            {"name": "bus", "label": "Bus", "field": "bus", "align": "left"},
                            {"name": "voltage", "label": "Voltage", "field": "voltage", "align": "right"},
                        ]
                        selected_table = ui.table(
                            columns=selected_columns,
                            rows=[],
                            row_key="bus",
                        ).classes("w-full")
                        clear_button = ui.button("Clear selection", icon="clear").props("flat")
                columns = [
                    {"name": "metric", "label": "Metric", "field": "metric", "align": "left"},
                    {"name": "value", "label": "Value", "field": "value", "align": "right"},
                ]
                table = ui.table(columns=columns, rows=[], row_key="metric").classes("w-full")

        current_result: GridResult | None = None
        selected_indices: set[int] = set()
        ignore_next_deselect = False

        def read_scenario() -> GridScenario:
            return GridScenario(
                demand_kw=float(demand.value or 0),
                pv_kw=float(pv.value or 0),
                battery_discharge_kw=float(battery.value or 0),
            )

        def _event_points(event: Any) -> list[dict[str, Any]]:
            args = getattr(event, "args", {})
            if isinstance(args, dict):
                points = args.get("points", [])
                return points if isinstance(points, list) else []
            return []

        def _show_selected(indices: set[int], *, update_plot: bool = True) -> None:
            nonlocal ignore_next_deselect
            if current_result is None:
                return
            selected_indices.clear()
            selected_indices.update(
                index
                for index in indices
                if 0 <= index < len(current_result.voltage_profile_pu)
            )
            rows = [
                {
                    "bus": f"Bus {index}",
                    "voltage": f"{current_result.voltage_profile_pu[index]:.5f} pu",
                }
                for index in sorted(selected_indices)
            ]
            selected_table.rows = rows
            selected_table.update()
            selection_status.set_text(
                f"{len(rows)} bus{'es' if len(rows) != 1 else ''} selected."
                if rows
                else "Click or box-select buses on the graph."
            )
            if update_plot:
                updated_figure = _voltage_figure(current_result)
                updated_figure.data[0].selectedpoints = sorted(selected_indices)
                # Updating a Plotly figure can emit a deselect event. Consume
                # that internal event instead of clearing the new selection.
                ignore_next_deselect = True
                figure.update_figure(updated_figure)

        def on_plot_selected(event: Any) -> None:
            indices = {
                int(point.get("pointIndex", point.get("pointNumber")))
                for point in _event_points(event)
                if point.get("pointIndex", point.get("pointNumber")) is not None
            }
            # Plotly already highlights box/lasso selections. Redrawing here
            # would emit a deselect event and erase the table immediately.
            _show_selected(indices, update_plot=False)

        def on_plot_clicked(event: Any) -> None:
            points = _event_points(event)
            if points:
                point = points[0]
                index = point.get("pointIndex", point.get("pointNumber"))
                if index is not None:
                    _show_selected({int(index)})

        def clear_selection() -> None:
            _show_selected(set())

        def on_plot_deselected(_: Any) -> None:
            nonlocal ignore_next_deselect
            if ignore_next_deselect:
                ignore_next_deselect = False
                return
            _show_selected(set(), update_plot=False)

        def show_result(snapshot: RunSnapshot) -> None:
            nonlocal current_result
            current_result = snapshot.result
            result = snapshot.result
            metric_min.set_text(f"Vmin {result.min_voltage_pu:.4f} pu")
            metric_line.set_text(f"Line {result.max_line_loading_percent:.1f}%")
            metric_losses.set_text(f"Losses {result.losses_kw:.3f} kW")
            status.set_text(f"{snapshot.run_id} completed at {snapshot.created_at}")
            figure.update_figure(_voltage_figure(result))
            _show_selected(set(), update_plot=False)
            table.rows = _result_rows(result)
            table.update()

        def run_scenario() -> None:
            try:
                snapshot = service.run_grid(read_scenario())
            except ValueError as error:
                ui.notify(str(error), type="negative")
                return
            show_result(snapshot)
            ui.notify("Grid demo completed", type="positive")

        def reset() -> None:
            demand.value = 6.0
            pv.value = 5.0
            battery.value = 0.0
            status.set_text("Inputs reset. Run the scenario to calculate new results.")
            ui.notify("Inputs reset")

        def save_snapshot() -> None:
            try:
                path = service.save_latest(Path("output/latest_snapshot.json"))
            except ValueError as error:
                ui.notify(str(error), type="warning")
                return
            ui.notify(f"Saved {path}", type="positive")

        run_button.on_click(run_scenario)
        reset_button.on_click(reset)
        save_button.on_click(save_snapshot)
        figure.on("plotly_selected", on_plot_selected)
        figure.on("plotly_click", on_plot_clicked)
        figure.on("plotly_deselect", on_plot_deselected)
        clear_button.on_click(clear_selection)


@ui.page("/runs")
def run_history() -> None:
    with _shell("Run history"):
        if not service.history:
            with ui.card().classes("w-full border border-slate-200"):
                ui.label("No runs yet").classes("text-lg font-medium")
                ui.label(
                    "Run a scenario in Grid explorer and it will appear here for this browser session."
                )
                ui.button(
                    "Go to grid explorer",
                    on_click=lambda: ui.navigate.to("/grid"),
                    icon="account_tree",
                )
            return

        rows = [
            {
                "run": snapshot.run_id,
                "time": snapshot.created_at,
                "vmin": f"{snapshot.result.min_voltage_pu:.4f} pu",
                "line": f"{snapshot.result.max_line_loading_percent:.1f}%",
                "losses": f"{snapshot.result.losses_kw:.3f} kW",
            }
            for snapshot in reversed(service.history)
        ]
        columns = [
            {"name": "run", "label": "Run", "field": "run", "align": "left"},
            {"name": "time", "label": "Created", "field": "time", "align": "left"},
            {"name": "vmin", "label": "Vmin", "field": "vmin", "align": "right"},
            {"name": "line", "label": "Line", "field": "line", "align": "right"},
            {"name": "losses", "label": "Losses", "field": "losses", "align": "right"},
        ]
        with ui.card().classes("w-full border border-slate-200 shadow-sm"):
            ui.label("In-memory session runs").classes("text-lg font-medium")
            ui.table(columns=columns, rows=rows, row_key="run").classes("w-full")
