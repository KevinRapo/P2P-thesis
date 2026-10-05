"""The sanity scenarios on the SimBench network of a preset."""

import json
from pathlib import Path

import pytest

from src_thesis.marlem.simulation.scenarios import SCENARIOS, describe, run_scenario
from src_thesis.platform.experiments.factory.environment import (
    build_engine_spec,
    world_builder,
)
from src_thesis.platform.experiments.models.records import ExperimentFile
from src_thesis.platform.experiments.models.resolve import resolve

PRESET = (
    Path(__file__).resolve().parents[1]
    / "src_thesis/platform/experiments/presets/case6-3x3.marlem.json"
)


@pytest.fixture(scope="module")
def world():
    file = resolve(ExperimentFile.model_validate(json.loads(PRESET.read_text("utf-8"))))
    return build_engine_spec(file, seed=1), world_builder(file)


@pytest.mark.parametrize("scenario", list(SCENARIOS))
def test_the_network_responds_as_expected(scenario, world) -> None:
    spec, build = world
    out = run_scenario(SCENARIOS[scenario], spec, build)
    detail = [(e.statement, e.detail) for e in out.expectations if not e.passed]
    assert out.passed, detail
    assert len(out.result.steps) == 24


def test_scenarios_are_described_for_the_ui() -> None:
    assert [d["id"] for d in describe()] == list(SCENARIOS)
    assert all(d["title"] and d["expected"] for d in describe())


def test_a_wrong_expectation_is_caught(world) -> None:
    from dataclasses import replace

    from src_thesis.marlem.simulation.scenarios import _rises

    spec, build = world
    wrong = replace(SCENARIOS["export_at_noon"], verify=lambda c: _rises(c, -1))
    assert not run_scenario(wrong, spec, build).passed
