"""Runs (04 §4.8): queue, live status, logs, cancellation."""

from nicegui import ui

from ..components import data_table, section, state_color
from ..layout import shell
from ..state import services


def _fmt_seconds(seconds: float | None) -> str:
    """A duration as ``Hh MMm``; ``—`` when unknown or zero."""
    if not seconds:
        return "—"
    hours, rest = divmod(int(seconds), 3600)
    return f"{hours}h {rest // 60:02d}m"


@ui.page("/runs")
def runs_page() -> None:
    """Runs (04 §4.8): queue, live status, log tail and cancel. Demo data until R7."""
    s = services()
    with shell(
        "runs", "Runs", "All runs from the experiment store; refreshed by polling"
    ):
        with ui.row().classes("w-full gap-2 items-center"):
            state_filter = ui.select(
                ["all", "RUNNING", "QUEUED", "COMPLETED", "FAILED"],
                value="all",
                label="State",
            ).classes("w-48")
            # Placeholder: the experiment filter is not applied yet.
            ui.select(["all", "case6-3x3"], value="all", label="Experiment").classes(
                "w-56"
            )
            ui.space()
            ui.label("auto-refresh every 2 s").classes("mls-card-caption")

        with section("Queue", icon="list"):
            table_box = ui.column().classes("w-full")

        def rows() -> list[dict]:
            """Table rows for the runs that pass the state filter."""
            out = []
            for r in s.experiments.list_runs():
                if state_filter.value != "all" and r.state.value != state_filter.value:
                    continue
                out.append(
                    {
                        "id": r.run_id,
                        "experiment": r.experiment_id,
                        "cell": f"{r.cell.algorithm.upper()} · {r.cell.paradigm.upper()}",
                        "seed": r.cell.seed,
                        "network": r.network,
                        "state": r.state.value,
                        "state_color": state_color(r.state.value),
                        "progress": f"{r.progress:.0%}",
                        "elapsed": _fmt_seconds(r.elapsed_s),
                        "eta": _fmt_seconds(r.eta_s),
                    }
                )
            return out

        def render() -> None:
            """Rebuild the queue table; called on filter changes and every 2 s."""
            table_box.clear()
            with table_box:
                table = data_table(
                    rows(),
                    [
                        ("experiment", "Experiment"),
                        ("cell", "Cell"),
                        ("seed", "Seed"),
                        ("network", "Network"),
                        ("state", "State"),
                        ("progress", "Progress"),
                        ("elapsed", "Elapsed"),
                        ("eta", "ETA"),
                    ],
                    badge_columns={"state": "state_color"},
                    pagination=15,
                )
                table.on("rowClick", lambda e: open_run(e.args[1]["id"]))

        with ui.dialog() as dialog, ui.card().classes("mls-card").style(
            "min-width: 640px"
        ):
            detail = ui.column().classes("w-full gap-2")

        def open_run(run_id: str) -> None:
            """Open the run drawer: progress, last metrics, log tail, results and
            cancel.
            """
            status = s.experiments.snapshot(run_id)
            detail.clear()
            with detail:
                ui.label(run_id).classes("mls-card-title mls-mono")
                ui.linear_progress(
                    value=status.summary.progress, show_value=False
                ).props("rounded size=8px")
                with ui.row().classes("gap-6"):
                    ui.label(f"iteration {status.iteration}").classes("text-body2")
                    for k, v in status.last_metrics.items():
                        ui.label(f"{k}: {v}").classes("text-body2")
                log = ui.log(max_lines=200).classes("w-full h-40 mls-mono")
                for line in status.log_tail:
                    log.push(line)
                with ui.row().classes("justify-end w-full gap-2"):
                    ui.button(
                        "Open results",
                        icon="insights",
                        on_click=lambda: ui.navigate.to(f"/results/{run_id}"),
                    ).props("flat")
                    ui.button(
                        "Cancel run",
                        icon="stop_circle",
                        color="negative",
                        on_click=lambda: (
                            s.experiments.cancel(run_id),
                            ui.notify("Cancellation requested (demo)."),
                        ),
                    ).props("outline")
            dialog.open()

        # Refresh on filter changes and poll every 2 s: runs execute in worker
        # processes, so the page has to ask for their state.
        state_filter.on_value_change(lambda: render())
        render()
        ui.timer(2.0, render)
