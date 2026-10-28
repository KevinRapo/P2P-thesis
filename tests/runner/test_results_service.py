"""The Studio's ResultsService (``studio/adapters/results_service.py``) over the
hand-written run folders of ``test_results.py``: it reads the runs once, passes the
reader's tables on as they are, and reads again after ``refresh``."""

from __future__ import annotations

from core.runner import results
from studio.adapters.results_service import ResultsService
from tests.runner.test_results import make_run, where  # noqa: F401 (the fixture)


def test_the_tables_are_the_readers(where):  # noqa: F811
    service = ResultsService(where)
    keys = ["local/grid/ppo_dtde_s0", "local/grid/ppo_dtde_s1"]
    assert list(service.overview().key) == [r.key for r in results.find_runs(where)]
    runs = results.load_runs([r for r in results.find_runs(where) if r.key in keys])
    assert service.heldout_days(keys).equals(results.heldout_days(runs))
    assert service.seed_groups(keys).equals(results.seed_groups(runs))
    assert service.differing_settings(keys) == ["seed"]
    one = keys[0]
    assert service.participant_days(one).equals(
        results.participant_days(service.result(one))
    )
    assert service.table(one, "heldout_episodes") is not None
    assert service.table(one, "heldout_trace_steps") is None


def test_runs_are_read_once_until_refresh(where):  # noqa: F811
    service = ResultsService(where)
    assert len(service.results()) == 4
    make_run(where["local"] / "grid", "ppo_dtde_s2", 2, [-1, -1])
    assert len(service.results()) == 4  # kept
    service.refresh()
    assert len(service.results()) == 5


# --------------------------------------------------------------------------------------
# What the Results page shows (its helpers, without a browser)
# --------------------------------------------------------------------------------------
def test_runs_of_two_targets_keep_their_target_in_the_labels():
    from studio.components.run_table import labels_of

    one = ["local/x/ppo_s0", "local/y/ppo_s0"]
    assert labels_of(one) == {
        "local/x/ppo_s0": "x/ppo_s0",
        "local/y/ppo_s0": "y/ppo_s0",
    }
    two = ["local/x/ppo_s0", "taltech/x/ppo_s0"]
    assert labels_of(two) == {k: k for k in two}  # apart, not one box


def test_the_heatmap_shows_the_largest_differences_or_the_filtered():
    import pandas as pd

    from studio.pages.results.market import shown_participants

    table = pd.DataFrame(
        {
            "agent": [f"P{i}" for i in range(50) for _ in range(2)],
            "d": [(-1) ** i * i for i in range(50) for _ in range(2)],
        }
    )
    top = shown_participants(table, "d", most=3)
    assert top == ["P49", "P48", "P47"]  # by size, either sign
    assert shown_participants(table, "d", "p1", most=30)[:2] == ["P19", "P18"]
    assert len(shown_participants(table, "d")) == 30


def test_baselines_are_each_runs_own_unless_they_are_the_same():
    import pandas as pd

    from studio.pages.results.validation import LearningChart

    def curves(zero_a, zero_b):
        rows = []

        for key, zero in (("t/x/a", zero_a), ("t/x/b", zero_b)):
            rows += [
                {
                    "key": key,
                    "env_steps": 0,
                    "policy": "zero",
                    "team_return_mean": zero,
                },
                {
                    "key": key,
                    "env_steps": 0,
                    "policy": "trained",
                    "team_return_mean": -5,
                },
                {
                    "key": key,
                    "env_steps": 100,
                    "policy": "trained",
                    "team_return_mean": -3,
                },
            ]

        frame = pd.DataFrame(rows)

        return frame.assign(per_participant=frame.team_return_mean / 2)

    labels = {"t/x/a": "x/a", "t/x/b": "x/b"}

    def figure(frame):
        chart = LearningChart(
            curves=frame, training=pd.DataFrame(), labels=labels, per=False, train=False
        )
        return chart.figure()

    shared = figure(curves(-10, -10))
    assert len(shared.data) == 2 and len(shared.layout.shapes) == 1  # one grey line
    own = figure(curves(-10, -20))
    names = [t.name for t in own.data]
    assert "x/a: zero" in names and "x/b: zero" in names  # each run's own
    assert len(own.layout.shapes) == 0
