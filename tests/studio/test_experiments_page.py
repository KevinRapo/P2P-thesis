"""The Experiments page's JSON follows what was loaded last."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from nicegui import ui
from nicegui.testing.user_simulation import user_simulation

from core.config import store
from studio import layout
from studio.adapters.run_service import RunService
from studio.adapters.scenario_service import ScenarioService
from studio.pages import experiments

REPO = Path(__file__).resolve().parents[2]
LIBRARY = REPO / "config" / "scenarios"
FILE = "config/scenarios/lv_rural1_s2.json"
SMOKE = str(REPO / "config" / "experiments" / "smoke.json")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def in_editor(form: experiments.ExperimentForm):
    return json.loads(form.editor.value)["scenario"]


@pytest.mark.anyio
async def test_the_json_follows_the_active_scenario_and_a_chosen_file(
    monkeypatch, tmp_path
):
    path = REPO / FILE
    scenario = ScenarioService(tmp_path / "current.json", LIBRARY)
    scenario.open(store.load(path), path.name, path)
    runs = RunService(selected=tmp_path / "selected.json")
    monkeypatch.setattr(
        experiments, "services", lambda: SimpleNamespace(scenario=scenario)
    )
    forms: list[experiments.ExperimentForm] = []

    async def root() -> None:
        forms.append(experiments.ExperimentForm(runs, [("local", "This PC")]))
        await forms[0].show()

    async with user_simulation(root) as user:
        await user.open("/")
        form = forms[0]
        assert form.active.value is True
        assert in_editor(form) == FILE

        scenario.current().market.seed = 7  # edited on the Scenario page
        form._changed()
        assert in_editor(form)["name"] == "lv_rural1_s2-mod"
        assert form.record["experiment"].scenario["market"]["seed"] == 7

        form.template.set_value(SMOKE)  # the file decides again
        written = json.loads(Path(SMOKE).read_text("utf-8"))["scenario"]
        assert form.active.value is False
        assert in_editor(form) == written

        form.active.set_value(True)
        assert in_editor(form)["name"] == "lv_rural1_s2-mod"
        assert form.record["experiment"].scenario["market"]["seed"] == 7


@pytest.mark.anyio
async def test_editing_the_json_marks_the_experiment_unsaved(monkeypatch, tmp_path):
    scenario = ScenarioService(tmp_path / "current.json", LIBRARY)
    runs = RunService(selected=tmp_path / "selected.json")
    monkeypatch.setattr(
        experiments, "services", lambda: SimpleNamespace(scenario=scenario)
    )
    forms: list[experiments.ExperimentForm] = []

    async def root() -> None:
        forms.append(experiments.ExperimentForm(runs, [("local", "This PC")]))
        await forms[0].show()

    async with user_simulation(root) as user:
        await user.open("/")
        form = forms[0]
        form.template.set_value(SMOKE)  # the file, as it is
        assert runs.selected_unsaved() is False

        form.editor.set_value(
            json.dumps(json.loads(form.editor.value) | {"description": "edited"})
        )
        assert runs.selected_unsaved() is True

        form.template.set_value(None)
        form.template.set_value(SMOKE)  # chosen again: the edits are gone
        assert runs.selected_unsaved() is False


@pytest.mark.anyio
async def test_a_file_from_elsewhere_stays_selected(monkeypatch, tmp_path):
    scenario = ScenarioService(tmp_path / "current.json", LIBRARY)
    runs = RunService(selected=tmp_path / "selected.json")
    runs.open_experiment("mine.json", Path(SMOKE).read_text("utf-8"))
    monkeypatch.setattr(
        experiments, "services", lambda: SimpleNamespace(scenario=scenario)
    )
    forms: list[experiments.ExperimentForm] = []

    async def root() -> None:
        forms.append(experiments.ExperimentForm(runs, [("local", "This PC")]))
        await forms[0].show()

    async with user_simulation(root) as user:
        await user.open("/")
        assert forms[0].template.value == "mine.json"
        assert forms[0].active.value is False
        assert forms[0].record["error"] is None


@pytest.mark.anyio
async def test_the_top_bar_marks_an_edited_experiment_unsaved(monkeypatch, tmp_path):
    runs = RunService(selected=tmp_path / "selected.json")
    text = Path(SMOKE).read_text("utf-8")
    runs.open_experiment(SMOKE, text)
    monkeypatch.setattr(layout, "services", lambda: SimpleNamespace(runs=runs))

    def root() -> None:
        layout._experiment_button()

    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see("Experiment: smoke")
        await user.should_not_see("smoke-mod")
        await user.should_not_see("unsaved")

    saved = runs.selected()
    edited = json.dumps(json.loads(saved["text"]) | {"description": "edited"})
    runs.save_selected(SMOKE, edited, False, saved["origin"])

    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see("Experiment: smoke-mod")


@pytest.mark.anyio
async def test_the_top_bar_names_the_experiment_and_opens_a_file(monkeypatch, tmp_path):
    runs = RunService(selected=tmp_path / "selected.json")
    monkeypatch.setattr(layout, "services", lambda: SimpleNamespace(runs=runs))

    def root() -> None:
        layout._experiment_button()

    async with user_simulation(root) as user:
        await user.open("/")
        await user.should_see("Experiment: none")
        user.find(kind=ui.button, content="Experiment").click()
        await user.should_see("Open an experiment file")
        await user.should_see("smoke.json")
        user.find(kind=ui.button, content="Open").click()  # the first file
        await user.should_see("Opened")
        first = sorted(Path(REPO / "config" / "experiments").glob("*.json"))[0]
        assert runs.selected_name() == first.stem
        assert runs.selected()["active"] is False
