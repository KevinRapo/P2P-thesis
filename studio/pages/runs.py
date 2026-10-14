"""Runs: the training experiments started with ``python -m core.runner``.

One card per experiment (the most recently changed first) with the number of runs in
each state, whether its worker is alive and a button to stop it, and a table of its
runs: state, progress, environment steps, elapsed time, ETA, the latest evaluation
return and the held-out return, and a Stop button on every run that is queued or
running. Everything is read from the files in ``runs/`` (the same as
``python -m core.runner status``), every two seconds, and updated in place: a card
or a table is only touched when what it shows has changed.
"""

from __future__ import annotations

from typing import Any, Optional

from nicegui import run, ui

from core.runner.registry import RunState
from studio.adapters.run_service import RunService
from studio.components.cards import placeholder, section
from studio.layout import shell
from studio.state import services

REFRESH_S = 2.0
START_HINT = "python -m core.runner start experiments/<name>.json"

# state -> (Quasar colour of the badge, colour of its text)
STATE_STYLE = {
    "queued": ("grey-6", "white"),
    "running": ("blue-7", "white"),
    "completed": ("positive", "white"),
    "failed": ("negative", "white"),
    "stopped": ("orange-8", "white"),
    "lost": ("amber-7", "black"),
    "unknown": ("amber-7", "black"),
}
STOPPABLE = ("queued", "running")

COLUMNS = [
    {"name": "name", "label": "Run", "field": "name", "sortable": True},
    {"name": "state", "label": "State", "field": "state", "sortable": True},
    {"name": "progress", "label": "Progress", "field": "progress", "sortable": True},
    {"name": "steps", "label": "Env steps / budget", "field": "steps"},
    {"name": "elapsed", "label": "Elapsed", "field": "elapsed"},
    {"name": "eta", "label": "ETA", "field": "eta"},
    {"name": "last_eval", "label": "Last eval", "field": "last_eval"},
    {"name": "heldout", "label": "Held-out", "field": "heldout"},
    {"name": "actions", "label": "", "field": "actions"},
]

# The cells that are not plain text. A click on Stop sends the run's name to Python.
STATE_CELL = """
<q-td :props="props">
  <q-badge :color="props.row.color" :text-color="props.row.text_color"
           :label="props.row.state" />
  <q-icon v-if="props.row.error" name="error_outline" color="negative" size="xs"
          class="q-ml-xs">
    <q-tooltip max-width="560px" class="text-body2" style="white-space: pre-wrap">
      {{ props.row.error }}
    </q-tooltip>
  </q-icon>
</q-td>
"""
PROGRESS_CELL = """
<q-td :props="props" style="min-width: 150px">
  <div class="row items-center no-wrap q-gutter-x-sm">
    <q-linear-progress :value="props.row.progress" :color="props.row.color"
                       rounded size="8px" style="flex: 1" />
    <span class="mls-mono" style="min-width: 3em; text-align: right">
      {{ props.row.percent }}
    </span>
  </div>
</q-td>
"""
ACTIONS_CELL = """
<q-td :props="props" auto-width>
  <q-btn v-if="props.row.can_stop" flat dense round size="sm" color="negative"
         icon="stop_circle" @click="() => $parent.$emit('stop', props.row.name)">
    <q-tooltip>Stop this run</q-tooltip>
  </q-btn>
</q-td>
"""


# --------------------------------------------------------------------------------------
# Text for the cells
# --------------------------------------------------------------------------------------
def _clock(seconds: Optional[float]) -> str:
    """``h:mm:ss`` (``-`` when not known)."""
    if seconds is None:
        return "-"
    hours, rest = divmod(int(seconds), 3600)
    return f"{hours}:{rest // 60:02d}:{rest % 60:02d}"


def _number(value: Optional[float]) -> str:
    return "-" if value is None else f"{value:.2f}"


def _row(run_state: RunState) -> dict[str, Any]:
    """The table row of one run: every cell as the text it shows."""
    color, text_color = STATE_STYLE.get(run_state.state, STATE_STYLE["unknown"])
    budget = f"{run_state.budget:,}" if run_state.budget else "?"
    return {
        "name": run_state.name,
        "state": run_state.state,
        "color": color,
        "text_color": text_color,
        "progress": run_state.progress,
        "percent": f"{run_state.progress:.0%}",
        "steps": f"{run_state.env_steps:,} / {budget}",
        "elapsed": _clock(run_state.elapsed_s),
        "eta": _clock(run_state.eta_s),
        "last_eval": _number(run_state.last_eval),
        "heldout": _number(run_state.heldout),
        "error": run_state.error or "",
        "can_stop": run_state.state in STOPPABLE,
    }


# --------------------------------------------------------------------------------------
# One experiment: its card
# --------------------------------------------------------------------------------------
class ExperimentCard:
    """The card of one experiment: a header and the table of its runs.

    ``update`` rebuilds the header only when the counts or the worker changed, and
    replaces the table's rows only when a row changed, so the page does not flicker.
    """

    def __init__(self, name: str, monitor: RunsMonitor, spec: Optional[dict]) -> None:
        self.name = name
        self.monitor = monitor
        self.runs: list[RunState] = []
        self._header_key: Any = None
        caption = (spec or {}).get("description") or (
            "" if spec else "Runs made without the runner (no experiment.json)"
        )
        with section(name, caption, "insights"):
            self.header = ui.row().classes("w-full items-center gap-2")
            self.table = (
                ui.table(
                    columns=[c | {"align": "left"} for c in COLUMNS],
                    rows=[],
                    row_key="name",
                    pagination={"rowsPerPage": 25},
                )
                .classes("w-full")
                .props("flat dense")
            )
            self.table.add_slot("body-cell-state", STATE_CELL)
            self.table.add_slot("body-cell-progress", PROGRESS_CELL)
            self.table.add_slot("body-cell-actions", ACTIONS_CELL)
            self.table.on("stop", lambda e: self.monitor.stop_run(self.name, e.args))

    def update(self, alive: bool, runs: list[RunState]) -> None:
        counts: dict[str, int] = {}
        for state in runs:
            counts[state.state] = counts.get(state.state, 0) + 1
        key = (alive, tuple(counts.items()))
        if key != self._header_key:
            self._header_key = key
            self.header.clear()
            with self.header:
                self._build_header(alive, counts)
        if runs != self.runs:
            self.table.rows[:] = [_row(r) for r in runs]
            self.table.update()
            self.runs = runs

    def _build_header(self, alive: bool, counts: dict[str, int]) -> None:
        ui.label(f"{sum(counts.values())} runs").classes("text-body2")
        for state, (color, text_color) in STATE_STYLE.items():
            if counts.get(state):
                ui.badge(f"{counts[state]} {state}", color=color).props(
                    f"text-color={text_color}"
                )
        ui.space()
        if alive:
            ui.badge("worker alive", color="positive").props("outline")
        else:
            ui.badge("no worker", color="grey-6").props("outline")
        if any(counts.get(state) for state in STOPPABLE):
            ui.button(
                "Stop experiment",
                icon="stop_circle",
                on_click=lambda: self.monitor.confirm_stop(self.name),
            ).props("outline no-caps dense color=negative")


# --------------------------------------------------------------------------------------
# The monitor: all cards, refreshed on a timer
# --------------------------------------------------------------------------------------
class RunsMonitor:
    """The cards on the page and the actions on them (one per open browser tab)."""

    def __init__(self, service: RunService, box: ui.element) -> None:
        self.service = service
        self.box = box
        self.cards: dict[str, ExperimentCard] = {}
        self._busy = False

    def _read(self) -> list[tuple[str, Optional[dict], bool, list[RunState]]]:
        """Everything the page shows (files only; runs in a worker thread)."""
        s = self.service
        return [
            (name, s.spec(name), s.worker_alive(name), s.runs(name))
            for name in s.experiments()
        ]

    async def refresh(self) -> None:
        """Read ``runs/`` and update the cards; skipped while the last read runs."""
        if self._busy:
            return
        self._busy = True
        try:
            data = await run.io_bound(self._read)
        except OSError:  # a file changed under the read: try again in two seconds
            return
        finally:
            self._busy = False
        if {name for name, *_ in data} != set(self.cards):
            self._build(data)
        for name, _spec, alive, runs in data:
            self.cards[name].update(alive, runs)

    def _build(self, data: list) -> None:
        """New cards for a changed set of experiments, in the order read."""
        self.box.clear()
        self.cards = {}
        with self.box:
            if not data:
                placeholder(
                    f"No experiments yet. Start one in a terminal: {START_HINT}",
                    "insights",
                )
            for name, spec, _alive, _runs in data:
                self.cards[name] = ExperimentCard(name, self, spec)

    # --- Stopping --------------------------------------------------------------------
    async def stop_run(self, experiment: str, name: str) -> None:
        """Stop one run, at once."""
        await self._stop(experiment, name, f"{experiment}/{name}")

    async def confirm_stop(self, experiment: str) -> None:
        """Ask first, then stop the worker and every run of the experiment."""
        # Built in the page's box, not in a card's header: that is rebuilt on a timer.
        with self.box, ui.dialog() as dialog, ui.card().classes("w-[460px] gap-3"):
            ui.label(f"Stop experiment {experiment}?").classes("text-h6")
            ui.label(
                "Kills the worker and every running run, and marks the queued ones "
                "stopped. A stopped run keeps no result: starting the experiment "
                "again trains it from scratch."
            ).classes("mls-card-caption")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=lambda: dialog.submit(False)).props(
                    "flat no-caps"
                )
                ui.button(
                    "Stop experiment", on_click=lambda: dialog.submit(True)
                ).props("unelevated no-caps color=negative")
        confirmed = await dialog
        dialog.delete()
        if confirmed:
            await self._stop(experiment, None, experiment)

    async def _stop(self, experiment: str, name: Optional[str], label: str) -> None:
        ui.notify(f"Stopping {label} ...")
        try:
            result = await run.io_bound(self.service.stop, experiment, name)
        except (OSError, RuntimeError) as error:
            ui.notify(f"Could not stop {label}: {error}", type="negative")
            return
        ui.notify(
            f"Stopped {label}: {len(result['killed'])} killed, "
            f"{len(result['stopped'])} marked stopped",
            type="positive",
        )
        await self.refresh()


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """The experiments, read at once and then every two seconds."""
    with shell(
        "runs",
        "Runs",
        "Training experiments, newest first. Start one in a terminal with "
        f"{START_HINT}; they keep running when this page is closed.",
    ):
        box = ui.column().classes("w-full gap-4")
    monitor = RunsMonitor(services().runs, box)
    ui.timer(0.05, monitor.refresh, once=True)
    ui.timer(REFRESH_S, monitor.refresh)
