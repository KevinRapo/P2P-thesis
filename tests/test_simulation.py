"""One simulated day end to end: preset, market, SimBench grid and checks."""

import json
from pathlib import Path

import pytest

from src_thesis.marlem.simulation.checks import CATALOG
from src_thesis.marlem.simulation.loop import run_simulation
from src_thesis.marlem.simulation.controllers import get_policy
from src_thesis.platform.kernel.factory.environment import (
    build_engine_spec,
    build_env,
    build_env_config,
    build_grid,
)
from src_thesis.platform.kernel.models.records import ExperimentFile, RunCell
from src_thesis.platform.kernel.models.resolve import resolve

PRESET = (
    Path(__file__).resolve().parents[1]
    / "src_thesis/platform/kernel/presets/case6-3x3.marlem.json"
)


def day(controller: str = "net_position", seed: int = 1):
    file = resolve(ExperimentFile.model_validate(json.loads(PRESET.read_text("utf-8"))))
    cell = RunCell(kind="noop", algorithm="-", paradigm="-", seed=seed)
    spec = build_engine_spec(file, seed=seed)
    engine = build_env(build_env_config(file, cell, episode_seed=seed))
    return run_simulation(
        engine, spec, get_policy(controller), build_grid(file, spec), seed
    )


@pytest.fixture(scope="module")
def result():
    return day()


def test_a_whole_day_is_simulated_with_a_power_flow_per_step(result) -> None:
    assert len(result.steps) == 24 and not result.stopped
    assert all(s["assessment"]["converged"] for s in result.steps)
    assert result.summary["steps_played"] == 24


def test_every_check_is_listed_and_the_invariants_hold(result) -> None:
    assert {c["id"] for c in result.checks} == set(CATALOG)
    broken = [
        c["id"] for c in result.checks if c["severity"] == "invariant" and c["failures"]
    ]
    assert broken == []


def test_findings_are_tied_to_steps_and_checks(result) -> None:
    for f in result.findings:
        assert f.check in CATALOG
    first = [s for s in result.steps if s["findings"]]
    assert all(f["check"] in CATALOG for s in first for f in s["findings"])


def test_the_known_engine_faults_show_up_as_engine_faults(result) -> None:
    seen = set(result.summary["engine_faults_seen"])
    assert {"I-14", "I-18", "I-19"} <= seen  # the original market's defects
    assert all(
        c["severity"] == "engine_fault" and c["issue"]
        for c in result.checks
        if c["failures"] and c["id"] in {"order_respected", "battery_direction"}
    )


def test_the_same_seed_gives_the_same_day(result) -> None:
    again = day()
    assert again.steps == result.steps


def test_a_silent_market_still_runs_the_physical_day() -> None:
    quiet = day("no_order")
    assert quiet.summary["trades"] == 0 or quiet.summary["p2p_kwh"] == 0
    assert all(s["assessment"]["converged"] for s in quiet.steps)


def test_stopping_ends_the_day_early() -> None:
    file = resolve(ExperimentFile.model_validate(json.loads(PRESET.read_text("utf-8"))))
    cell = RunCell(kind="noop", algorithm="-", paradigm="-", seed=1)
    spec = build_engine_spec(file, seed=1)
    engine = build_env(build_env_config(file, cell, episode_seed=1))
    calls = []
    out = run_simulation(
        engine,
        spec,
        get_policy("no_order"),
        None,
        1,
        should_stop=lambda: len(calls.append(1) or calls) > 3,
    )
    assert out.stopped and len(out.steps) == 3
