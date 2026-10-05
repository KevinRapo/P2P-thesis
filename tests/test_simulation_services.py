"""The services behind the Simulate page: runs, results, checks and validation."""

import time
from pathlib import Path

import pytest

from src_thesis.platform.services.container import build_services
from src_thesis.platform.services.models import RunState, Severity


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    s = build_services(home=tmp_path_factory.mktemp("home"))
    file = s.config.new_from_preset("case6-3x3")
    return s, file


@pytest.fixture(scope="module")
def run(world):
    s, file = world
    run_id = s.experiments.create_simulation(
        file, "net_position", {"aggressiveness": 0.5}, day="2016-06-15"
    )
    s.experiments.start([run_id])
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        s.experiments.tick()
        if s.experiments.snapshot(run_id).summary.state in (
            RunState.COMPLETED,
            RunState.FAILED,
        ):
            break
        time.sleep(0.5)
    return run_id


def test_controllers_are_listed_with_their_parameters(world) -> None:
    s, _ = world
    controllers = {c.name: c for c in s.experiments.controllers()}
    assert {"no_order", "random", "net_position"} <= set(controllers)
    assert controllers["net_position"].params[0].name == "aggressiveness"


def test_bad_controller_settings_are_refused(world) -> None:
    s, file = world
    with pytest.raises(ValueError):
        s.experiments.create_simulation(file, "nope")
    with pytest.raises(ValueError):
        s.experiments.create_simulation(file, "net_position", {"aggressiveness": 5})


def test_a_started_run_completes_through_the_pool(world, run) -> None:
    s, _ = world
    status = s.experiments.snapshot(run)
    assert status.summary.state == RunState.COMPLETED, status.log_tail
    assert status.summary.progress == 1.0
    assert [r.run_id for r in s.experiments.list_runs()] == [run]


def test_the_same_settings_can_be_run_again(world, run) -> None:
    s, file = world
    again = s.experiments.create_simulation(
        file, "net_position", {"aggressiveness": 0.5}, day="2016-06-15"
    )
    assert again != run


def test_results_read_the_run_folder(world, run) -> None:
    s, _ = world
    steps = s.results.replay(run)
    assert len(steps) == 24 and steps[0]["day"] == "2016-06-15"
    topology = s.results.topology(run)
    assert topology.topology.buses and topology.participants
    rows = s.results.step_records(run)
    assert len(rows) == 24 and rows[12]["min_v_pu"] is not None
    assert len(s.results.grid_series(run).x) == 24
    assert s.results.agent_series(run).y
    outcome = s.results.summary(run)
    assert outcome.outcomes["steps_played"] == 24 and outcome.rl_return is None


def test_checks_tell_invariants_from_engine_faults(world, run) -> None:
    s, _ = world
    checks = {c.id: c for c in s.results.checks(run)}
    assert all(c.failures == 0 for c in checks.values() if c.severity == "invariant")
    assert checks["battery_direction"].issue == "I-18"
    assert (
        checks["order_respected"].failures > 0 and checks["order_respected"].first_day
    )


def test_a_half_written_last_line_is_ignored(world, run, tmp_path) -> None:
    s, _ = world
    path = s.results.store.run_dir(run) / "raw" / "steps.jsonl"
    original = path.read_bytes()
    try:
        path.write_bytes(original + b'{"day": "2016-06-15", "step"')
        assert len(s.results.replay(run)) == 24
    finally:
        path.write_bytes(original)


def test_validation_finds_what_is_wrong_with_a_file(world) -> None:
    s, file = world
    ok = s.validation.validate(file, level="references")
    assert ok.ok, [f.message for f in ok.findings if f.severity == Severity.ERROR]
    broken = file.model_copy(deep=True)
    broken.participants[0].bus = "no such bus"
    report = s.validation.validate(broken, level="references")
    assert "PARTICIPANT_BUS_UNKNOWN" in {f.code for f in report.findings}
    empty = file.model_copy(update={"participants": []})
    assert "PARTICIPANTS_EMPTY" in {
        f.code for f in s.validation.validate(empty, level="schema").findings
    }


def test_dry_run_and_a_scenario_run_in_a_subprocess(world) -> None:
    s, file = world
    dry = s.validation.dry_run(file)
    assert dry.ok and dry.power_flow_converged, dry.messages
    out = s.validation.run_scenario(file, "export_at_noon")
    assert out.passed and out.series and not out.error, out.expectations
    assert [x.id for x in s.validation.scenarios()][0] == "idle_market"


def test_runs_that_have_not_started_sort_with_started_ones(world, run) -> None:
    s, file = world
    waiting = s.experiments.create_simulation(file, "no_order", day="2016-06-16")
    ids = [r.run_id for r in s.experiments.list_runs()]  # READY: no start time
    assert run in ids and waiting in ids and ids.index(run) < ids.index(waiting)
