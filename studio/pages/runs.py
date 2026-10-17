"""Runs: the training experiments, on this PC and on a cluster.

One tab per target in ``hpc/targets.toml`` (This PC, TalTech). A tab has one card per
experiment (the most recently changed first) with the number of runs in each state and
a button to stop it, and a table of its runs: state, progress, environment steps,
elapsed time, ETA, the latest evaluation return and the held-out return, and a Stop
button on every run that is queued or running. Everything is read from the target's
files (the same as ``python -m core.runner status``) and updated in place: a card or a
table is only touched when what it shows has changed.

This PC's tab is read every two seconds. A cluster is read over SSH, so its tab is read
every 20 seconds and only while it is the tab shown (nothing connects before it is
opened). It adds the SLURM state and the node to the table, a Sync results button to
each card (results are copied only when asked), and a line at the top with what the
runner's ``check`` found: "Ready", or the problems that stop a start. A read that fails
is not a notification: a line says why and when the data shown was last updated, and
goes away with the next read that works. Start, Stop and Sync show their errors as
notifications. The "Start experiment" button starts a spec from ``experiments/`` on
either target.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional

from nicegui import run, ui

from core.runner.registry import RunState
from studio.adapters.run_service import RunService
from studio.components.cards import key_values, placeholder, section
from studio.layout import shell
from studio.state import services

LOCAL = "local"  # the target that is this PC; any other target is a cluster
LOCAL_REFRESH_S = 2.0
REMOTE_REFRESH_S = 20.0  # every read of a cluster is a round trip over SSH
START_HINT = (
    "Start an experiment with the button above, or "
    "`python -m core.runner start experiments/<name>.json [--target taltech]`"
)
PROFILES = {"test": "Test (tiny, checks the pipeline)", "full": "Full"}

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


def _fail(message: str) -> None:
    """The error of an action the user asked for: a notification that stays until it
    is closed."""
    ui.notify(message, type="negative", multi_line=True, close_button=True)


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
        caption = (spec or {}).get("description") or (
            "" if spec else "Runs made without the runner (no experiment.json)"
        )
        with section(name, caption, "insights"):
            with ui.row().classes("w-full items-center gap-2"):
                self.badges = ui.row().classes("items-center gap-2")
                ui.space()
                if monitor.remote:
                    ui.button(
                        "Sync results",
                        icon="sync",
                        on_click=lambda e: monitor.sync(name, e.sender),
                    ).props("outline no-caps dense")
                self.stop = ui.button(
                    "Stop experiment",
                    icon="stop_circle",
                    on_click=lambda: monitor.confirm_stop(name),
                ).props("outline no-caps dense color=negative")
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
            self.table.on("stop", lambda e: monitor.stop_run(name, e.args))

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
            self.stop.set_visibility(any(counts[state] for state in STOPPABLE))
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
# What ``check`` found
# --------------------------------------------------------------------------------------
async def _check(service: RunService, target: str, spec_path: Optional[str]) -> dict:
    """``service.check`` in a worker thread. A target that cannot even be made
    (incomplete ``targets.toml``) is a report that is not ok, with the reason."""
    try:
        return await run.io_bound(service.check, target, spec_path)
    except (OSError, RuntimeError, ValueError) as error:
        return {
            "ok": False,
            "problems": [str(error)],
            "local_commit": None,
            "cluster_commit": None,
            "active": None,
        }


def _short(commit: Optional[str]) -> str:
    return commit[:8] if commit else "unknown"


def _show_report(report: dict) -> None:
    """A report of ``check`` in the current container: Ready, or the problems that
    stop a start; the two commits; and the experiments that are queued or running, as
    a reminder not to update the cluster's checkout while they are."""
    with ui.row().classes("items-start gap-2 no-wrap"):
        if report["ok"]:
            ui.icon("check_circle", size="20px", color="positive")
            ui.label("Ready").classes("text-body2")
        else:
            ui.icon("warning", size="20px", color="orange-8")
            with ui.column().classes("gap-0"):
                for problem in report["problems"]:
                    ui.label(problem).classes("text-body2")
    cluster, local = report["cluster_commit"], report["local_commit"]
    ui.label(f"cluster {_short(cluster)} · this PC {_short(local)}").classes("mls-mono")
    if report["active"]:
        ui.label(
            f"Queued or running: {', '.join(report['active'])}. Do not update or edit "
            "the cluster's checkout while they run."
        ).classes("mls-card-caption")


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
        with panel:
            if self.remote:
                with ui.row().classes("w-full items-start gap-3 no-wrap"):
                    self.status = ui.column().classes("grow gap-1")
                    ui.button(
                        "Check", icon="wifi_tethering", on_click=self.check
                    ).props("flat no-caps dense")
            with ui.row().classes("w-full items-center gap-2"):
                self.note = ui.label()
                if self.remote:
                    ui.button(
                        "Refresh now",
                        icon="refresh",
                        on_click=lambda: self.refresh(True),
                    ).props("flat no-caps dense")
            self.box = ui.column().classes("w-full gap-4")
            ui.timer(REMOTE_REFRESH_S if self.remote else LOCAL_REFRESH_S, self.refresh)

    async def show(self) -> None:
        """The tab was opened: read the target now (and keep reading it), and check a
        cluster the first time."""
        self.active = True
        if self.remote and not self._checked:
            await asyncio.gather(self.check(), self.refresh())
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
            data = await run.io_bound(self.service.overview, self.target)
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

    async def check(self) -> None:
        """Ask the cluster whether it is ready and show the report."""
        self._checked = True
        self.status.clear()
        with self.status:
            ui.label(f"Checking {self.label} ...").classes("mls-card-caption")
        report = await _check(self.service, self.target, None)
        self.status.clear()
        with self.status:
            _show_report(report)

    # --- Syncing ---------------------------------------------------------------------
    async def sync(self, experiment: str, button: ui.button) -> None:
        """Copy the experiment's results from the cluster to this PC."""
        button.props("loading")
        try:
            folder, copied = await run.io_bound(
                self.service.sync, self.target, experiment
            )
        except (OSError, RuntimeError) as error:
            _fail(f"Could not sync {experiment}: {error}")
        else:
            ui.notify(f"Synced {copied} files to {folder}", type="positive")
        finally:
            button.props(remove="loading")

    # --- Stopping --------------------------------------------------------------------
    async def stop_run(self, experiment: str, name: str) -> None:
        """Stop one run, at once."""
        await self._stop(experiment, name, f"{experiment}/{name}")

    async def confirm_stop(self, experiment: str) -> None:
        """Ask first, then stop the worker and every run of the experiment."""
        what = (
            "Cancels every queued and running SLURM task of the experiment and marks "
            "its runs stopped."
            if self.remote
            else "Kills the worker and every running run, and marks the queued ones "
            "stopped."
        )
        # Built in the tab's panel, not in a card: a card can be rebuilt meanwhile.
        with self.panel, ui.dialog() as dialog, ui.card().classes("w-[460px] gap-3"):
            ui.label(f"Stop experiment {experiment}?").classes("text-h6")
            ui.label(
                f"{what} A stopped run keeps no result: starting the experiment "
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
            result = await run.io_bound(
                self.service.stop, self.target, experiment, name
            )
        except (OSError, RuntimeError) as error:
            _fail(f"Could not stop {label}: {error}")
            return
        done = "cancelled" if "cancelled" in result else "killed"
        ui.notify(
            f"Stopped {label}: {len(result[done])} {done}, "
            f"{len(result['stopped'])} marked stopped",
            type="positive",
        )
        await self.refresh()


# --------------------------------------------------------------------------------------
# Starting an experiment: the dialog
# --------------------------------------------------------------------------------------
def _budget(budget: int | dict) -> str:
    """The environment steps of each run: one number, or one per algorithm."""
    if isinstance(budget, dict):
        steps = ", ".join(f"{algorithm} {n:,}" for algorithm, n in budget.items())
    else:
        steps = f"{budget:,}"
    return f"{steps} env steps"


def _resources(resources: dict) -> str:
    return (
        f"{resources['cpus']} cpus, {resources['mem_gb']:g} GB, "
        f"{resources['minutes']} min"
    )


class StartDialog:
    """The dialog that starts a spec from ``experiments/`` on a target: which spec,
    which profile, where. For a cluster it checks the chosen spec there whenever the
    spec or the target changes, lists the problems, and keeps Start disabled until
    there are none (``start`` checks again anyway).

    Args:
        service: The Runs service.
        targets: ``(name, label)`` of every target.
        on_started: Called with the target's name once the experiment has started (the
            page then shows that target's tab).
    """

    def __init__(
        self,
        service: RunService,
        targets: list[tuple[str, str]],
        on_started: Callable[[str], Awaitable[None]],
    ) -> None:
        self.service = service
        self.targets = dict(targets)
        self.on_started = on_started
        self.specs: dict[str, dict] = {}  # the specs that load, by path
        self.report: Optional[dict] = None  # the check of the chosen cluster and spec
        self.starting = False  # a start request is running: one at a time
        with ui.dialog() as self.dialog:
            with ui.card().classes("w-[560px] max-w-full gap-3"):
                self.body = ui.column().classes("w-full gap-3")  # filled by ``show``

    async def show(self) -> None:
        """Open the dialog with the specs as they are now."""
        records = await run.io_bound(self.service.spec_files)
        self.specs = {str(r["path"]): r for r in records if not r["error"]}
        self.body.clear()
        with self.body:
            self._build([r for r in records if r["error"]])
        self.dialog.open()
        self._show_details()
        await self._check()

    def _build(self, broken: list[dict]) -> None:
        """The fields, made again each time the dialog opens, in the order the user
        fills them."""
        ui.label("Start an experiment").classes("text-h6")
        self.spec = ui.select(
            {path: spec["name"] for path, spec in self.specs.items()},
            label="Experiment",
            value=next(iter(self.specs), None),
            on_change=self._spec_changed,
        ).classes("w-full")
        self.details = ui.column().classes("w-full gap-1")
        for record in broken:
            ui.label(
                f"{record['path'].name} cannot be used: {record['error']}"
            ).classes("text-negative text-caption")
        self.profile = ui.radio(
            PROFILES, value="test", on_change=self._profile_changed
        ).props("inline")
        self.target = ui.select(
            self.targets,
            label="Where to run",
            value=self._default_target("test"),
            on_change=self._check,
        ).classes("w-full")
        self.check_box = ui.column().classes("w-full gap-1")
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=self.dialog.close).props("flat no-caps")
            self.start = ui.button(
                "Start", icon="play_arrow", on_click=self._start
            ).props("unelevated no-caps")

    def _default_target(self, profile: str) -> str:
        """A test runs on this PC; a full experiment on the first cluster, if any."""
        clusters = [name for name in self.targets if name != LOCAL]
        return clusters[0] if profile == "full" and clusters else LOCAL

    # --- What the fields show --------------------------------------------------------
    def _show_details(self) -> None:
        """What the chosen spec is, and what the chosen profile makes of it."""
        self.details.clear()
        spec = self.specs.get(self.spec.value)
        if spec is None:
            return
        prefix = "test_" if self.profile.value == "test" else ""
        with self.details:
            if spec["description"]:
                ui.label(spec["description"]).classes("mls-card-caption")
            key_values(
                {
                    "Runs": f"{spec['runs']} (test: {spec['test_runs']})",
                    "Budget per run": _budget(spec[f"{prefix}budget"]),
                    "Cluster resources per run": _resources(spec[f"{prefix}resources"]),
                }
            )

    async def _spec_changed(self) -> None:
        self._show_details()
        await self._check()

    def _profile_changed(self) -> None:
        self.target.set_value(self._default_target(self.profile.value))
        self._show_details()

    # --- Checking and starting -------------------------------------------------------
    async def _check(self) -> None:
        """Check the chosen spec on the chosen cluster (this PC needs no check) and
        show the report. Start stays disabled until it is ok."""
        asked = (self.target.value, self.spec.value)
        self.report = None
        self.check_box.clear()
        self._update_start()
        target, spec = asked
        if target == LOCAL or spec not in self.specs:
            return
        with self.check_box:
            ui.label(f"Checking {self.targets[target]} ...").classes("mls-card-caption")
        report = await _check(self.service, target, spec)
        if asked != (self.target.value, self.spec.value):  # changed in the meantime
            return
        self.report = report
        self.check_box.clear()
        with self.check_box:
            _show_report(report)
            ui.button("Check again", icon="refresh", on_click=self._check).props(
                "flat no-caps dense"
            )
        self._update_start()

    def _update_start(self) -> None:
        """Start needs a spec, for a cluster a report that is ok, and no start that
        is still running."""
        ready = self.spec.value in self.specs and (
            self.target.value == LOCAL or bool(self.report and self.report["ok"])
        )
        self.start.set_enabled(ready and not self.starting)

    async def _start(self) -> None:
        target, label = self.target.value, self.targets[self.target.value]
        self.starting = True
        self._update_start()
        try:
            name = await run.io_bound(
                self.service.start, target, self.spec.value, self.profile.value
            )
        except (OSError, RuntimeError, ValueError) as error:
            self.starting = False
            _fail(f"Could not start: {error}")
            await self._check()  # what was true a moment ago may not be now
            return
        self.starting = False
        ui.notify(f"started {name} on {label}", type="positive")
        self.dialog.close()
        await self.on_started(target)


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """The experiments of each target, read at once and then every few seconds."""
    service = services().runs

    async def show_target(target: str) -> None:
        """Open a target's tab (after starting an experiment on it) and read it."""
        tabs.set_value(target)
        await monitors[target].refresh(True)

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
        ui.button(
            "Start experiment…", icon="play_arrow", on_click=lambda: dialog.show()
        ).props("unelevated no-caps")
        with ui.tabs().props("align=left no-caps").classes("w-full") as tabs:
            for name, label in names:
                icon = "computer" if name == LOCAL else "cloud"
                ui.tab(name, label=label, icon=icon)
        first = names[0][0]
        monitors: dict[str, RunsMonitor] = {}
        with ui.tab_panels(tabs, value=first).classes("w-full bg-transparent"):
            for name, label in names:
                with ui.tab_panel(name).classes("p-0 gap-4") as panel:
                    monitors[name] = RunsMonitor(
                        service, name, label, panel, active=name == first
                    )
        dialog = StartDialog(service, names, show_target)
        tabs.on_value_change(opened)
        ui.timer(0.05, monitors[first].show, once=True)
