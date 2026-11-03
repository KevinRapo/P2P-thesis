"""Experiments: what to train, before it is started.

An experiment file from ``config/experiments/`` is the template: its JSON is shown in
an editor, and every edit is checked as a start would check it
(``RunService.describe``), with the runs it makes or what is wrong. The file itself is
never changed. The Test and Full presets rewrite the run size settings in the editor
(``RunService.apply_preset``) and leave every other edit, and the paradigms, seeds,
budget, PPO settings, workers and cluster resources are also offered as fields that
rewrite the JSON. The experiment plays the active scenario, saved or not, and its JSON
follows it. What was loaded last decides: opening a scenario turns this on, choosing an
experiment file turns it off, so the file's own scenario plays. It stays selected
(``RunService.save_selected``): the Summary page shows it.

Start starts the edited experiment as a new one (``RunService.start_new_experiment``):
if the target has an experiment of that name, the date and time are added to it. For a
cluster the page checks the target when it opens and when the target changes, and
keeps Start disabled until the check has no problems.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from nicegui import run, ui

from studio.adapters.run_service import QUICK_GROUPS, QUICK_SETTINGS, RunService
from studio.components.cards import key_values, placeholder, section
from studio.components.choices import checkboxes
from studio.components.memory import remember
from studio.components.run_check import (
    experiment_facts,
    fail,
    read_check,
    show_report,
)
from studio.layout import shell
from studio.state import services

LOCAL = "local"  # the target that is this PC; any other target is a cluster
# preset -> (button, icon, what it is for)
PRESET_BUTTONS = {
    "test": ("Test preset", "science", "the smallest version, to check the pipeline"),
    "full": ("Full preset", "rocket_launch", "the template's run size"),
}

PARADIGM_CHOICES = {"ctce": "CTCE", "ctde": "CTDE", "dtde": "DTDE"}


# --------------------------------------------------------------------------------------
# The form
# --------------------------------------------------------------------------------------
class ExperimentForm:
    """The experiment being prepared, and where to start it.

    Args:
        service: The Runs service.
        targets: ``(name, label)`` of every target.
    """

    def __init__(self, service: RunService, targets: list[tuple[str, str]]) -> None:
        self.service = service
        self.targets = dict(targets)
        self.templates: dict[str, dict] = {}  # the experiment files, by path
        self.record: Optional[dict] = None  # ``describe`` of the editor's text
        self.report: Optional[dict] = None  # the check of the chosen cluster
        self.fit: list[str] = []  # what that cluster cannot give the experiment
        self.starting = False  # a start request is running: one at a time
        self.quick: dict[str, Any] = {}  # the fields of the quick settings
        self._filling = False  # the fields are being set from the editor
        self.body = ui.column().classes("w-full gap-4")  # filled by ``show``

    async def show(self) -> None:
        """Build the form with the experiment files as they are now, on the selected
        experiment if there is one, else on the first file."""
        records = await run.io_bound(self.service.spec_files)
        self.templates = {str(r["path"]): r for r in records}
        selected = self.service.selected()

        if selected and selected["template"]:  # a file from elsewhere is not listed
            self.templates.setdefault(selected["template"], selected)

        kept = selected and selected["template"] in self.templates
        first = selected["template"] if kept else next(iter(self.templates), None)
        self.body.clear()

        with self.body:
            self._build(first, selected["active"] if kept else True)

        if kept:
            self.editor.set_value(selected["text"])
            self._changed()
        else:
            self._template_changed()

        await self._on_check()

    def _build(self, template: Optional[str], active: bool) -> None:
        """The cards, top to bottom: the template, the quick settings, the JSON
        editor, and what it starts with where to run."""
        with section(
            "Template",
            "An experiment file to start from; the file itself is not changed",
            "description",
        ):
            self.template = ui.select(
                {path: Path(path).stem for path in self.templates},
                label="Experiment file",
                value=template,
                on_change=self._template_chosen,
            ).classes("w-full")

            self.active = ui.switch(
                "Play the active scenario", value=active, on_change=self._changed
            )
            self.scenario_note = ui.label().classes("mls-card-caption")

            # One row of preset buttons
            with ui.row().classes("w-full items-center gap-2"):
                for preset, (label, icon, purpose) in PRESET_BUTTONS.items():
                    ui.button(
                        label,
                        icon=icon,
                        on_click=lambda p=preset: self._apply_preset(p),
                    ).props("outline no-caps dense").tooltip(
                        f"Overwrite name, seeds, days, budget, evaluation and "
                        f"resources in the editor with {purpose}; other edits stay"
                    )

        with section(
            "Paradigms, PPO and resources",
            "Each field rewrites its setting in the JSON below",
            "tune",
        ):
            self._build_quick()

        with section(
            "Experiment",
            "Every setting is written out, with its default where the template gives "
            "none (docs: Config). What the editor holds is what "
            "starts.",
            "data_object",
        ):
            self.editor = (
                ui.textarea(on_change=self._changed)
                .classes("w-full mls-mono")
                .props("outlined rows=24")
            )

        with section(
            "Start",
            "If the target has an experiment of this name, the start adds the date "
            "and time to it",
            "play_arrow",
        ):
            # What the experiment starts, or what is wrong (filled by _show_details)
            self.details = ui.column().classes("w-full gap-1")
            self.target = ui.select(
                self.targets,
                label="Where to run",
                value=LOCAL,
            ).classes("w-full")
            remember(self.target, "experiments_target")
            self.target.on_value_change(self._on_check)  # show() checks it once
            # The cluster's check report (filled by _check)
            self.check_box = ui.column().classes("w-full gap-1")

            # Bottom button, right-aligned
            with ui.row().classes("w-full justify-end"):
                self.start = ui.button(
                    "Start", icon="play_arrow", on_click=self._on_start
                ).props("unelevated no-caps")

    def _build_quick(self) -> None:
        """The quick settings: each field rewrites its setting in the JSON."""
        for group, fields in QUICK_GROUPS.items():
            ui.label(group).classes("mls-card-caption")

            # The group's fields in one row
            with ui.row().classes("w-full gap-2"):
                for name, (label, kind, _) in fields.items():
                    if kind == "paradigms":
                        field = checkboxes(
                            ui.select(PARADIGM_CHOICES, multiple=True, label=label)
                        ).props("dense")
                        field.classes("min-w-[260px]")
                    elif kind == "seeds":
                        field = ui.input(label).props("dense").classes("w-40")
                    else:
                        field = ui.number(label).props("dense").classes("w-40")
                    field.on_value_change(lambda e, n=name: self._quick_changed(n))
                    self.quick[name] = field

    def _fill_quick(self) -> None:
        """Show the editor's values in the quick settings."""
        values = self.service.quick_settings(self.editor.value or "")
        self._filling = True

        try:
            for name, field in self.quick.items():
                value = values.get(name)
                if name == "seeds":
                    value = ", ".join(str(s) for s in value) if value else ""
                elif name == "paradigms":
                    value = list(value or [])
                if field.value != value:
                    field.set_value(value)
        finally:
            self._filling = False

    def _quick_changed(self, name: str) -> None:
        """A quick setting was edited: write it into the editor's JSON."""
        if self._filling:
            return

        kind = QUICK_SETTINGS[name][1]
        value = self.quick[name].value

        try:
            if kind == "seeds":
                value = [
                    int(s) for s in str(value or "").replace(" ", "").split(",") if s
                ]
            elif kind == "int" and value is not None:
                value = int(value)
            elif kind == "float" and value is not None:
                value = float(value)
            text = self.service.apply_settings(self.editor.value or "", {name: value})
        except ValueError as error:
            fail(f"Cannot set {name}: {error}")
            return

        self.editor.set_value(text)  # checked again by ``_changed``

    def _default_target(self, preset: str) -> str:
        """A test runs on this PC; a full experiment on the first cluster, if any."""
        clusters = [name for name in self.targets if name != LOCAL]
        return clusters[0] if preset == "full" and clusters else LOCAL

    # --- The experiment ---------------------------------------------------------------
    def _template_chosen(self) -> None:
        """A file was chosen: everything shown is now the file's, its scenario too."""
        self.active.set_value(False)
        self._template_changed()

    def _template_changed(self) -> None:
        """Put the chosen template's text in the editor."""
        template = self.templates.get(self.template.value)

        if template is None:
            self.editor.set_value("")
        else:
            name = Path(self.template.value).stem
            self.editor.set_value(self.service.editable(template["text"], name))

        self._changed()

    def _apply_preset(self, preset: str) -> None:
        """Rewrite the editor's run size settings as the preset's, and pick the
        target that suits it."""
        template = self.templates.get(self.template.value)

        if template is None:
            return

        name = Path(self.template.value).stem

        try:
            text = self.service.apply_preset(
                self.editor.value or "",
                preset,
                self.service.editable(template["text"], name),  # written out
                name,
            )
        except ValueError as error:
            fail(f"Cannot apply the {preset} preset: {error}")
            return

        self.editor.set_value(text)  # checked again by ``_changed``
        self.target.set_value(self._default_target(preset))

    def _changed(self) -> None:
        """Check the editor's text and show what it makes."""
        if self.active.value:
            text = self.editor.value or ""
            shown = self.service.showing_scenario(text, services().scenario.reference())

            if shown != text:
                self.editor.set_value(shown)  # checked again by ``_changed``
                return

        template = self.templates.get(self.template.value)

        if template is None:
            self.record = None
        else:
            name = Path(self.template.value).stem  # as for a file without a name
            self.record = self.service.describe(self._played(), name)

        self._show_scenario()
        self.service.save_selected(
            self.template.value, self.editor.value or "", self.active.value
        )
        self._fill_quick()
        self._refit()

    def _played(self) -> str:
        """The editor's text with the scenario it plays: what a start starts."""
        return self.service.with_scenario(
            self.editor.value or "",
            services().scenario.played() if self.active.value else None,
        )

    def _show_scenario(self) -> None:
        scenario = services().scenario
        self.scenario_note.set_text(
            f"Plays the active scenario, {scenario.shown_name()}"
            + (" (unsaved)" if scenario.unsaved() else "")
            + "; the JSON below follows it."
            if self.active.value
            else "Plays the scenario the JSON below names."
        )

    def _refit(self) -> None:
        """Check the experiment against the chosen cluster's last report (what it
        asks that the cluster cannot give, e.g. a node it does not have), then show
        the details and update Start."""
        experiment = self.record["experiment"] if self.record else None
        self.fit = []

        if experiment is not None and self.report is not None:
            nodes = self.report.get("nodes")
            self.fit = self.service.check_fit(self.target.value, experiment, nodes)

        self._show_details()
        self._update_start()

    def _show_details(self) -> None:
        """The runs the experiment makes, or what is wrong; and what the chosen
        cluster cannot give."""
        self.details.clear()
        record = self.record

        if record is None:
            return

        with self.details:
            if record["error"]:
                # Error icon | message
                with ui.row().classes("items-start gap-2 no-wrap"):
                    ui.icon("error_outline", size="20px", color="negative")
                    ui.label(record["error"]).classes("text-body2 text-negative")
                return

            key_values(experiment_facts(record))
            label = self.targets.get(self.target.value, self.target.value)

            for problem in self.fit:
                # Error icon | what the cluster cannot give
                with ui.row().classes("items-start gap-2 no-wrap"):
                    ui.icon("error_outline", size="20px", color="negative")
                    ui.label(f"On {label}: {problem}").classes(
                        "text-body2 text-negative"
                    )

    # --- Checking and starting -------------------------------------------------------
    async def _on_check(self) -> None:
        """Check the chosen cluster (this PC needs no check) and show the report; the
        experiment itself is checked here on every edit. Start stays disabled until
        the report is ok."""
        asked = self.target.value
        self.report = None
        self.check_box.clear()
        self._refit()

        if asked == LOCAL:
            return

        with self.check_box:
            ui.label(f"Checking {self.targets[asked]} ...").classes("mls-card-caption")

        report = await read_check(self.service, asked, None)

        if asked != self.target.value:  # changed in the meantime
            return

        self.report = report
        self.check_box.clear()

        with self.check_box:
            show_report(report)
            ui.button("Check again", icon="refresh", on_click=self._on_check).props(
                "flat no-caps dense"
            )

        self._refit()

    def _update_start(self) -> None:
        """Start needs an experiment that loads, for a cluster a report that is ok
        and nothing the cluster cannot give, and no start that is still running."""
        ready = bool(self.record and self.record["experiment"]) and (
            self.target.value == LOCAL
            or bool(self.report and self.report["ok"] and not self.fit)
        )
        self.start.set_enabled(ready and not self.starting)

    async def _on_start(self) -> None:
        target, label = self.target.value, self.targets[self.target.value]
        experiment = self.record["experiment"]
        self.starting = True
        self._update_start()

        try:
            name = await run.io_bound(
                self.service.start_new_experiment, target, experiment, "full"
            )
        except (OSError, RuntimeError, ValueError) as error:
            self.starting = False
            fail(f"Could not start: {error}")
            await self._on_check()  # what was true a moment ago may not be now

            return

        self.starting = False
        ui.notify(f"started {name} on {label}", type="positive")
        ui.navigate.to(f"/runs?target={target}")


# --------------------------------------------------------------------------------------
# The page
# --------------------------------------------------------------------------------------
def page() -> None:
    """The form on the selected experiment."""
    service = services().runs

    with shell(
        "experiments",
        "Experiments",
        "What to train: choose an experiment file as a template, change it, and start "
        "it on this PC or on a cluster. The Runs page follows it from there.",
    ):
        try:
            names = service.target_names()
        except RuntimeError as error:  # hpc/targets.toml is not valid
            placeholder(f"The targets cannot be read: {error}", "error_outline")
            return

        form = ExperimentForm(service, names)
        ui.timer(0.05, form.show, once=True)
