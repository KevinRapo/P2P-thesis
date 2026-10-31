"""Runs: the training experiments, on this PC and on a cluster.

One tab per target in ``hpc/targets.toml`` (This PC, TalTech). A tab has one card per
experiment (the most recently changed first) with the number of runs in each state and
a button to stop it, and a table of its runs: state, progress, environment steps,
elapsed time, ETA, the latest evaluation return and the held-out return, and a Stop
button on every run that is queued or running. Everything is read from the target's
files (the same as ``python -m core.runner status``) and updated in place: a card or a
table is only touched when what it shows has changed.

This PC's tab is read every two seconds. A cluster is read over SSH, so its tab is read
every 10 seconds and only while it is the tab shown (nothing connects before it is
opened). It adds the SLURM state and the node to the table, a Sync results button to
each card (results are copied only when asked), and a line at the top with what the
runner's ``check`` found: "Ready", or the problems that stop a start. A read that fails
is not a notification: a line says why and when the data shown was last updated, and
goes away with the next read that works. Start, Stop and Sync show their errors as
notifications. Experiments are started on the Experiments page; "Restart failed
runs" starts one again from the settings saved in its folder.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
from typing import Any, Optional

from nicegui import run, ui

from core.runner.registry import RunState
from studio.adapters.run_service import RunService
from studio.components.cards import placeholder, section
from studio.components.run_check import fail, read_check, show_report
from studio.layout import shell
from studio.state import services

LOCAL = "local"  # the target that is this PC; any other target is a cluster
LOCAL_REFRESH_S = 2.0
RECENT = 8  # experiments shown unless all are asked for (and those running)
REMOTE_REFRESH_S = 10.0  # every read of a cluster is a round trip over SSH
START_HINT = (
    "Start an experiment on the Experiments page, or "
    "`python -m core.runner start config/experiments/<name>.json [--target taltech]`"
)
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
RESTARTABLE = ("failed", "stopped", "lost")

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
# A cluster's table has these after the state.
CLUSTER_COLUMNS = [
    {"name": "slurm", "label": "SLURM", "field": "slurm", "sortable": True},
    {"name": "node", "label": "Node", "field": "node", "sortable": True},
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


def _columns(cluster: bool) -> list[dict]:
    """The table's columns (a cluster's also has the SLURM state and the node)."""
    columns = COLUMNS[:2] + CLUSTER_COLUMNS + COLUMNS[2:] if cluster else COLUMNS
    return [c | {"align": "left"} for c in columns]


def _row(run_state: RunState) -> dict[str, Any]:
    """The table row of one run: every cell as the text it shows."""
    color, text_color = STATE_STYLE.get(run_state.state, STATE_STYLE["unknown"])
    budget = f"{run_state.budget:,}" if run_state.budget else "?"

    return {
        "name": run_state.name,
        "state": run_state.state,
        "slurm": run_state.slurm_state or "-",
        "node": run_state.host or "-",
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

    ``update`` rebuilds the badges only when the counts or the worker changed, and
    replaces the table's rows only when a row changed, so the page does not flicker.
    """

    def __init__(self, name: str, monitor: RunsMonitor, spec: Optional[dict]) -> None:
        self.name = name
        self.monitor = monitor
        self.runs: list[RunState] = []
        self._badges_key: Any = None
        self.has_spec = spec is not None  # settings saved: it can be restarted
        caption = (spec or {}).get("description") or (
            "" if spec else "Runs made without the runner (no experiment.json)"
        )

        # The experiment's card: a header row, then the table of its runs
        with section(name, caption, "insights"):
            # Header row: state badges (left) | Sync, Restart and Stop (right)
            with ui.row().classes("w-full items-center gap-2"):
                self.badges = ui.row().classes("items-center gap-2")
                ui.space()

                if monitor.remote:
                    ui.button(
                        "Sync results",
                        icon="sync",
                        on_click=lambda e: monitor.on_sync(name, e.sender),
                    ).props("outline no-caps dense")

                self.restart = ui.button(
                    "Restart failed runs",
                    icon="replay",
                    on_click=lambda e: monitor.on_restart(name, e.sender),
                ).props("outline no-caps dense")
                self.restart.tooltip(
                    "Train the failed, stopped and lost runs again, from scratch, "
                    "with the settings this experiment was started with"
                )
                self.stop = ui.button(
                    "Stop experiment",
                    icon="stop_circle",
                    on_click=lambda: monitor.on_stop_experiment(name),
                ).props("outline no-caps dense color=negative")

            # The runs table; its state, progress and Stop cells are the HTML
            # templates STATE_CELL, PROGRESS_CELL and ACTIONS_CELL above
            self.table = (
                ui.table(
                    columns=_columns(monitor.remote),
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
            self.table.on("stop", lambda e: monitor.on_stop_run(name, e.args))

    def update(self, entry: dict) -> None:
        """Show an entry of ``RunService.overview``."""
        runs = entry["runs"]
        counts = Counter(state.state for state in runs)
        alive = entry["summary"]["worker_alive"]
        key = (alive, tuple(counts.items()))

        if key != self._badges_key:
            self._badges_key = key
            self.badges.clear()

            with self.badges:
                self._build_badges(counts, alive)

            busy = any(counts[state] for state in STOPPABLE)
            self.stop.set_visibility(busy)
            self.restart.set_visibility(
                self.has_spec
                and not busy
                and any(counts[state] for state in RESTARTABLE)
            )

        if runs != self.runs:
            self.table.rows[:] = [_row(r) for r in runs]
            self.table.update()
            self.runs = runs

    def _build_badges(self, counts: Counter, alive: bool) -> None:
        ui.label(f"{sum(counts.values())} runs").classes("text-body2")
        for state, (color, text_color) in STATE_STYLE.items():
            if counts[state]:
                ui.badge(f"{counts[state]} {state}", color=color).props(
                    f"text-color={text_color}"
                )
        if not self.monitor.remote:  # a cluster has SLURM tasks, no worker process
            if alive:
                ui.badge("worker alive", color="positive").props("outline")
            else:
                ui.badge("no worker", color="grey-6").props("outline")


# --------------------------------------------------------------------------------------
# The monitor: one target's cards, refreshed on a timer
# --------------------------------------------------------------------------------------
class RunsMonitor:
    """One tab: the cards of a target and the actions on them (one per open browser
    tab and target).

    Args:
        service: The Runs service.
        target: The target's name in ``hpc/targets.toml``.
        label: The name the tab shows.
        panel: The tab panel to build into.
        active: Whether the tab is the one shown. A monitor refreshes only while it is,
            so a cluster is not asked about until its tab is opened.
    """

    def __init__(
        self,
        service: RunService,
        target: str,
        label: str,
        panel: ui.element,
        active: bool,
    ) -> None:
        self.service = service
        self.target = target
        self.label = label
        self.remote = target != LOCAL
        self.panel = panel
        self.active = active
        self.cards: dict[str, ExperimentCard] = {}
        self._busy = False  # a read is running: the next one waits
        self._built = False
        self._checked = False
        self._updated = ""  # when the data shown was read

        # The target's tab, top to bottom: (cluster) check report with its button,
        # the "updated" note with Refresh now, then the experiment cards
        with panel:
            if self.remote:
                # Check report (grows) | Check button
                with ui.row().classes("w-full items-start gap-3 no-wrap"):
                    self.status = ui.column().classes("grow gap-1")
                    ui.button(
                        "Check", icon="wifi_tethering", on_click=self.on_check
                    ).props("flat no-caps dense")

            # When the data was read | Refresh now | All experiments
            with ui.row().classes("w-full items-center gap-2"):
                self.note = ui.label()
                if self.remote:
                    ui.button(
                        "Refresh now",
                        icon="refresh",
                        on_click=lambda: self.refresh(True),
                    ).props("flat no-caps dense")

                ui.space()
                self.all = ui.switch(
                    f"All experiments (else the {RECENT} newest and those running)",
                    on_change=lambda: self.refresh(True),
                )

            # The experiment cards, newest first (built by _build)
            self.box = ui.column().classes("w-full gap-4")
            ui.timer(REMOTE_REFRESH_S if self.remote else LOCAL_REFRESH_S, self.refresh)

    async def show(self) -> None:
        """The tab was opened: read the target now (and keep reading it), and check a
        cluster the first time."""
        self.active = True
        if self.remote and not self._checked:
            await asyncio.gather(self.on_check(), self.refresh())
        else:
            await self.refresh()

    # --- Reading ---------------------------------------------------------------------
    async def refresh(self, force: bool = False) -> None:
        """Read the target and update the cards; skipped while the last read runs, and
        while the tab is not shown (unless ``force``). A read that fails is shown in
        the note, and the cards stay."""
        if self._busy or not (self.active or force):
            return

        self._busy = True

        try:
            recent = None if self.all.value else RECENT
            data = await run.io_bound(self.service.experiments, self.target, recent)
        except (OSError, RuntimeError) as error:
            self._show_note(error)
            return
        finally:
            self._busy = False

        self._updated = f"{datetime.now():%H:%M:%S}"
        self._show_note()

        if not self._built or {e["name"] for e in data} != set(self.cards):
            self._build(data)

        for entry in data:
            self.cards[entry["name"]].update(entry)

    def _show_note(self, error: Optional[BaseException] = None) -> None:
        """Why the last read failed and how old the data shown is, or on a cluster
        when the data was read. Nothing on this PC's tab while all is well."""
        if error is not None:
            verb = "reach" if self.remote else "read"
            text = f"Cannot {verb} {self.label}: {error}."
            if self._updated:
                text += f" Showing data last updated at {self._updated}."
        else:
            text = f"Updated {self._updated}" if self.remote else ""

        self.note.set_text(text)
        self.note.classes(
            add="text-negative" if error else "mls-card-caption",
            remove="mls-card-caption" if error else "text-negative",
        )

    def _build(self, data: list[dict]) -> None:
        """New cards for a changed set of experiments, in the order read."""
        self.box.clear()
        self.cards = {}
        self._built = True

        with self.box:
            if not data:
                placeholder(
                    f"No experiments on {self.label} yet. {START_HINT}", "insights"
                )
            for entry in data:
                self.cards[entry["name"]] = ExperimentCard(
                    entry["name"], self, entry["spec"]
                )

    async def on_check(self) -> None:
        """Ask the cluster whether it is ready and show the report."""
        self._checked = True
        self.status.clear()

        with self.status:
            ui.label(f"Checking {self.label} ...").classes("mls-card-caption")

        report = await read_check(self.service, self.target, None)
        self.status.clear()

        with self.status:
            show_report(report)

    # --- Syncing ---------------------------------------------------------------------
    async def on_sync(self, experiment: str, button: ui.button) -> None:
        """Copy the experiment's results from the cluster to this PC."""
        button.props("loading")
        try:
            folder, copied = await run.io_bound(
                self.service.sync_experiment, self.target, experiment
            )
        except (OSError, RuntimeError) as error:
            fail(f"Could not sync {experiment}: {error}")
        else:
            ui.notify(f"Synced {copied} files to {folder}", type="positive")
        finally:
            button.props(remove="loading")

    # --- Restarting ------------------------------------------------------------------
    async def on_restart(self, experiment: str, button: ui.button) -> None:
        """Start the experiment again from the settings saved in its folder."""
        button.props("loading")
        try:
            await run.io_bound(self.service.restart_experiment, self.target, experiment)
        except (OSError, RuntimeError, ValueError) as error:
            fail(f"Could not restart {experiment}: {error}")
        else:
            ui.notify(f"Restarted the failed runs of {experiment}", type="positive")
            await self.refresh(True)
        finally:
            button.props(remove="loading")

    # --- Stopping --------------------------------------------------------------------
    async def on_stop_run(self, experiment: str, name: str) -> None:
        """Stop one run, at once."""
        await self._stop_and_report(experiment, name, f"{experiment}/{name}")

    async def on_stop_experiment(self, experiment: str) -> None:
        """Ask first, then stop the worker and every run of the experiment."""
        what = (
            "Cancels every queued and running SLURM task of the experiment and marks "
            "its runs stopped."
            if self.remote
            else "Kills the worker and every running run, and marks the queued ones "
            "stopped."
        )

        # Built in the tab's panel, not in a card: a card can be rebuilt meanwhile.
        # Pop-up window: question, explanation, Cancel | Stop experiment
        with self.panel, ui.dialog() as dialog, ui.card().classes("w-[460px] gap-3"):
            ui.label(f"Stop experiment {experiment}?").classes("text-h6")
            ui.label(
                f"{what} A stopped run keeps no result: starting the experiment "
                "again trains it from scratch."
            ).classes("mls-card-caption")

            # Buttons, right-aligned
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
            await self._stop_and_report(experiment, None, experiment)

    async def _stop_and_report(
        self, experiment: str, name: Optional[str], label: str
    ) -> None:
        ui.notify(f"Stopping {label} ...")

        try:
            result = await run.io_bound(
                self.service.stop_experiment, self.target, experiment, name
            )
        except (OSError, RuntimeError) as error:
            fail(f"Could not stop {label}: {error}")
            return

        done = "cancelled" if "cancelled" in result else "killed"
        ui.notify(
            f"Stopped {label}: {len(result[done])} {done}, "
            f"{len(result['stopped'])} marked stopped",
            type="positive",
        )
        await self.refresh()


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page(target: str = "") -> None:
    """The experiments of each target, read at once and then every few seconds;
    ``/runs?target=taltech`` opens that target's tab."""
    service = services().runs

    async def opened(e) -> None:
        """A tab was chosen: only its monitor reads from now on."""
        for name, monitor in monitors.items():
            monitor.active = name == e.value
        await monitors[e.value].show()

    with shell(
        "runs",
        "Runs",
        "Training experiments, newest first, on this PC or on a cluster. They keep "
        "running when this page is closed.",
    ):
        try:
            names = service.target_names()
        except RuntimeError as error:  # hpc/targets.toml is not valid
            placeholder(f"The targets cannot be read: {error}", "error_outline")
            return

        # Tab bar: one tab per target (this PC, then each cluster)
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            for name, label in names:
                icon = "computer" if name == LOCAL else "cloud"
                ui.tab(name, label=label, icon=icon)

        first = target if target in dict(names) else names[0][0]
        monitors: dict[str, RunsMonitor] = {}

        # One panel per target, each filled by its RunsMonitor
        with ui.tab_panels(tabs, value=first).classes("w-full bg-transparent"):
            for name, label in names:
                with ui.tab_panel(name).classes("p-0 gap-4") as panel:
                    monitors[name] = RunsMonitor(
                        service, name, label, panel, active=name == first
                    )

        tabs.on_value_change(opened)
        ui.timer(0.05, monitors[first].show, once=True)
