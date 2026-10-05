"""Simulate: scripted controllers play days on the draft's market and network.

Pick a controller, a start day and the number of days, run, and watch the market
and the network step by step. The checks below the replay say whether the engine
and the network behaved: invariants (bugs), known faults of the original market,
and the limits the network hit.
"""

from datetime import date

from nicegui import run, ui

from src_thesis.platform.studio.components.cards import section, stat, stat_grid
from src_thesis.platform.studio.components.checks_panel import checks_panel
from src_thesis.platform.studio.components.replay import replay
from src_thesis.platform.studio.components.tables import data_table, state_color
from src_thesis.platform.studio.layout import shell
from src_thesis.platform.studio.state import current_draft, services

DEFAULT_DAY = "2016-06-15"
TERMINAL = ("COMPLETED", "FAILED", "CANCELLED")


def _first_day(draft) -> str:
    """The first day of the draft's time window, else a summer workday."""
    try:
        days = services().config.days(draft)
    except (ValueError, KeyError):
        return DEFAULT_DAY
    return (days["train"] or days["eval"] or [DEFAULT_DAY])[0]


@ui.page("/simulate")
def simulate_page() -> None:
    """Simulate: set up a run."""
    _render(None)


@ui.page("/simulate/{run_id}")
def simulate_run_page(run_id: str) -> None:
    """Simulate: set up a run and watch the one in the URL.

    Args:
        run_id: A simulation run, from the URL.
    """
    _render(run_id)


def _render(run_id: str | None) -> None:
    s = services()
    draft = current_draft()
    with shell(
        "simulate",
        "Simulate",
        "Scripted controllers play days on the draft's market and network",
    ):
        report = s.validation.validate(draft, level="schema")
        errors = [f for f in report.findings if f.severity.value == "error"]
        controllers = {c.name: c for c in s.simulate.controllers()}
        values: dict[str, float] = {}

        with ui.row().classes("w-full gap-4 items-stretch no-wrap"):
            with section(
                "Set up", "What plays, when and with which seed", "tune", "basis-1/3"
            ):
                choice = ui.select(
                    {k: c.title for k, c in controllers.items()},
                    value="net_position",
                    label="Controller",
                ).classes("w-full")
                about = ui.label("").classes("mls-card-caption")
                params_box = ui.column().classes("w-full gap-1")
                day = ui.input("First day", value=_first_day(draft)).classes("w-full")
                ui.label(
                    "A day of the SimBench profile year 2016 (YYYY-MM-DD)."
                ).classes("mls-card-caption")
                days = ui.number("Days", value=1, min=1, max=7, step=1).classes(
                    "w-full"
                )
                ui.label(
                    "Consecutive days from the first day; each is its own day "
                    "with its own seed."
                ).classes("mls-card-caption")
                seed = ui.number("Seed", value=1, step=1).classes("w-full")
                ui.label("Same seed, same day: the run repeats exactly.").classes(
                    "mls-card-caption"
                )

                def show_controller() -> None:
                    c = controllers[choice.value]
                    about.set_text(c.description)
                    params_box.clear()
                    values.clear()
                    with params_box:
                        for p in c.params:
                            values[p.name] = p.default
                            ui.label(p.label).classes("text-body2 q-mt-md")
                            ui.slider(
                                min=p.low,
                                max=p.high,
                                step=(p.high - p.low) / 20,
                                value=p.default,
                                on_change=lambda e, n=p.name: values.__setitem__(
                                    n, e.value
                                ),
                            ).props("label-always")
                            ui.label(p.help).classes("mls-card-caption")

                choice.on_value_change(lambda: show_controller())
                show_controller()

                dry_box = ui.column().classes("w-full gap-0")

                async def dry_run() -> None:
                    dry_box.clear()
                    with dry_box:
                        ui.spinner()
                    result = await run.io_bound(s.validation.dry_run, draft)
                    dry_box.clear()
                    with dry_box:
                        ui.label(
                            "dry run passed" if result.ok else "dry run failed"
                        ).classes("text-positive" if result.ok else "text-negative")
                        for m in result.messages:
                            ui.label(m).classes("mls-card-caption")

                def start() -> None:
                    try:
                        date.fromisoformat(day.value)
                        new = s.simulate.create_simulation(
                            draft,
                            choice.value,
                            dict(values),
                            day.value,
                            int(days.value or 1),
                            int(seed.value or 0),
                        )
                    except ValueError as error:
                        ui.notify(str(error), type="negative")
                        return
                    s.experiments.start([new])
                    ui.navigate.to(f"/simulate/{new}")

                if errors:
                    ui.label(
                        f"{len(errors)} error(s) in the draft block the run: "
                        + "; ".join(f.message for f in errors[:2])
                    ).classes("text-negative text-caption")
                with ui.row().classes("gap-2"):
                    ui.button("Dry run", icon="science", on_click=dry_run).props(
                        "outline" + (" disable" if errors else "")
                    )
                    ui.button(
                        "Run simulation", icon="play_arrow", on_click=start
                    ).props("unelevated" + (" disable" if errors else ""))

            with section(
                "Recent simulations",
                "Click one to replay it",
                "history",
                "grow basis-0",
            ):
                rows = [
                    {
                        "id": r.run_id,
                        "controller": r.cell.algorithm,
                        "days": r.cell.days,
                        "state": r.state.value,
                        "state_color": state_color(r.state.value),
                        "progress": f"{r.progress:.0%}",
                    }
                    for r in s.experiments.list_runs()
                    if r.cell.kind == "simulate"
                ][:8]
                if rows:
                    table = data_table(
                        rows,
                        [
                            ("controller", "Controller"),
                            ("days", "Days"),
                            ("state", "State"),
                            ("progress", "Progress"),
                        ],
                        badge_columns={"state": "state_color"},
                        pagination=8,
                    )
                    table.on(
                        "rowClick",
                        lambda e: ui.navigate.to(f"/simulate/{e.args[1]['id']}"),
                    )
                else:
                    ui.label("No simulation yet.").classes("mls-card-caption")

        if run_id is not None:
            _watch(run_id)


def _watch(run_id: str) -> None:
    """Progress, replay, summary and checks of one run, live while it goes."""
    s = services()
    status = s.experiments.snapshot(run_id)
    with section(f"Run {run_id}", "", "slideshow", "w-full"):
        state_label = ui.label("").classes("text-body2")
        bar = ui.linear_progress(value=0, show_value=False).props("rounded size=8px")
        cancel = ui.button(
            "Cancel", icon="stop_circle", on_click=lambda: s.experiments.cancel(run_id)
        ).props("outline color=negative")
        handle = replay(run_id, live=status.summary.state.value not in TERMINAL)

    summary_box = ui.column().classes("w-full gap-3")
    checks_box = ui.column().classes("w-full gap-3")
    shown = {"state": None, "steps": -1}

    def refresh() -> None:
        snap = s.experiments.snapshot(run_id)
        state = snap.summary.state.value
        bar.set_value(snap.summary.progress)
        state_label.set_text(
            f"{state.lower()} · {snap.summary.progress:.0%}"
            + (f" · {snap.log_tail[-1]}" if snap.log_tail and state == "FAILED" else "")
        )
        cancel.set_visibility(state not in TERMINAL)
        steps = snap.iteration
        if state == shown["state"] and steps == shown["steps"]:
            return
        shown.update(state=state, steps=steps)
        summary_box.clear()
        with summary_box:
            outcomes = s.results.summary(run_id).outcomes
            if outcomes:
                with stat_grid():
                    stat(
                        "Steps played",
                        f"{outcomes['steps_played']:.0f}",
                        "",
                        "schedule",
                    )
                    stat(
                        "P2P energy",
                        f"{outcomes['p2p_kwh']:.1f} kWh",
                        "between participants",
                        "swap_horiz",
                    )
                    stat(
                        "DSO energy",
                        f"{outcomes['dso_kwh']:.1f} kWh",
                        "with the DSO",
                        "bolt",
                    )
                    low = outcomes.get("min_voltage_pu")
                    stat(
                        "Lowest voltage",
                        "—" if low is None else f"{low:.4f} pu",
                        f"{outcomes['grid_violations']:.0f} grid violations",
                        "speed",
                    )
        checks_box.clear()
        with checks_box:
            checks_panel(s.results.checks(run_id), handle.jump)

    refresh()
    if status.summary.state.value not in TERMINAL:
        ui.timer(2.0, refresh)
