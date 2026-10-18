"""The results reader (``core/runner/results.py``) over hand-written run folders: no
training, no cluster. Two seeds of one configuration on this PC, one run in a
cluster's mirror, and an older run with only its means."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from core.runner import results

DAYS = ["2016-07-01", "2016-07-02"]


def write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, pd.DataFrame):
        data.to_csv(path, index=False)
    else:
        path.write_text(json.dumps(data), encoding="utf-8")


def make_run(exp_dir: Path, name: str, seed: int, trained: list[float], **record):
    """A completed run whose trained policy scores ``trained`` on the two days; the
    baselines score -10 (zero) and -6 (net_position) on both."""
    run = exp_dir / name
    write(run / "status.json", {"state": "completed", "budget": 100, "index": seed})
    write(
        run / "run.json",
        {
            "algorithm": "ppo",
            "paradigm": "dtde",
            "seed": seed,
            "budget_env_steps": 100,
            "git": {"commit": "abcdef123456", "uncommitted_changes": False},
        }
        | record,
    )
    episodes = []
    for policy, scores in (
        ("trained", trained),
        ("zero", [-10, -10]),
        ("net_position", [-6, -6]),
    ):
        for i, (day, score) in enumerate(zip(DAYS, scores)):
            episodes.append(
                {
                    "policy": policy,
                    "episode": i,
                    "seed": 2000 + i,
                    "day": day,
                    "team_return": score,
                }
            )
    write(run / "heldout_episodes.csv", pd.DataFrame(episodes))
    summary = pd.DataFrame(episodes).groupby("policy", sort=False).team_return.mean()
    write(
        run / "heldout.csv",
        pd.DataFrame(
            {
                "policy": summary.index,
                "team_return_mean": summary.values,
                "return/P1": 0,
                "return/P2": 0,
            }
        ),
    )
    agents = [
        {
            "policy": e["policy"],
            "episode": e["episode"],
            "day": e["day"],
            "agent": a,
            "return": e["team_return"] / 2,
        }
        for e in episodes
        for a in ("P1", "P2")
    ]
    write(run / "heldout_agents.csv", pd.DataFrame(agents))
    write(
        run / "evaluation.csv",
        pd.DataFrame(
            {
                "env_steps": [0, 0, 100],
                "policy": ["trained", "zero", "trained"],
                "team_return_mean": [-12, -10, trained[0]],
                "return/P1": 0,
                "return/P2": 0,
            }
        ),
    )
    write(
        run / "metrics.csv",
        pd.DataFrame({"env_steps": [50, 100], "team_return_mean": [-11, -9]}),
    )
    return run


@pytest.fixture()
def where(tmp_path) -> dict[str, Path]:
    root = tmp_path / "runs"
    exp = root / "grid"
    write(
        exp / "experiment.json",
        {"name": "grid", "scenario": {"name": "s1"}, "test_days": DAYS},
    )
    make_run(exp, "ppo_dtde_s0", 0, [-8, -9])
    make_run(exp, "ppo_dtde_s1", 1, [-7, -6])
    mirror = root / "@cluster"
    cluster = mirror / "grid"
    write(
        cluster / "experiment.json",
        {"name": "grid", "scenario": {"name": "s2"}, "test_days": DAYS},
    )
    make_run(cluster, "ppo_dtde_s0_v1", 0, [-5, -5])
    old = root / "old" / "sac_ctce_s3"
    write(
        old / "run.json",
        {"status": "completed", "algorithm": "sac", "paradigm": "ctce"},
    )
    write(
        old / "heldout.csv",
        pd.DataFrame(
            {"policy": ["trained", "zero"], "team_return_mean": [-4.0, -10.0]}
        ),
    )
    return {"local": root, "cluster": mirror}


def test_every_run_once_with_its_target(where):
    refs = results.find_runs(where)
    assert sorted(r.key for r in refs) == [
        "cluster/grid/ppo_dtde_s0_v1",  # the mirror's run, under the cluster's name
        "local/grid/ppo_dtde_s0",
        "local/grid/ppo_dtde_s1",
        "local/old/sac_ctce_s3",
    ]


def test_settings_come_from_the_saved_files(where):
    runs = {r.key: r for r in results.load_runs(results.find_runs(where))}
    one = runs["cluster/grid/ppo_dtde_s0_v1"]
    settings = one.settings
    assert (settings["algorithm"], settings["paradigm"]) == ("ppo", "dtde")
    assert (settings["seed"], settings["variant"]) == (0, "v1")
    assert settings["scenario"] == {"name": "s2"}  # its contents, to compare
    assert (settings["commit"], settings["test"]) == ("abcdef12", False)
    assert settings["test_days"] == DAYS
    labels = one.labels  # for display
    assert (labels["scenario"], labels["test_days"]) == (
        "s2",
        "2016-07-01 … 2016-07-02 (2)",
    )
    assert "overrides" not in labels
    old = runs["local/old/sac_ctce_s3"].settings
    assert (old["algorithm"], old["seed"]) == ("sac", 3)  # from the folder's name
    assert runs["local/grid/ppo_dtde_s0"].table("missing") is None
    assert runs["local/grid/ppo_dtde_s0"].has("heldout_agents")
    assert not runs["local/grid/ppo_dtde_s0"].has("heldout_trace_steps")


def test_differences_are_found_in_the_full_values_not_the_labels():
    base = {
        "scenario": {"name": "s", "participants": [1, 2]},
        "test_days": ["2016-07-01", "2016-07-02", "2016-07-03"],
        "overrides": {"lr": 0.001, "gamma": 0.99},
    }
    same = base | {"overrides": {"gamma": 0.99, "lr": 0.001}}  # other order
    assert results.differing_settings([base, same]) == []
    other = {
        "scenario": {"name": "s", "participants": [1, 2, 3]},  # same name
        "test_days": ["2016-07-01", "2016-07-05", "2016-07-03"],  # same ends
        "overrides": {"lr": 0.01, "gamma": 0.99},
    }
    assert results.differing_settings([base, other], results.COMPARED) == [
        "scenario",
        "test_days",
        "overrides",
    ]


def test_overview_and_curves(where):
    runs = results.load_runs(results.find_runs(where))
    table = results.overview(runs).set_index("key")
    assert table.loc["local/grid/ppo_dtde_s1", "heldout_trained"] == -6.5
    assert table.loc["local/grid/ppo_dtde_s1", "participants"] == 2
    assert table.loc["local/old/sac_ctce_s3", "state"] == "completed"
    curves = results.learning_curves(runs)
    first = curves[(curves.key == "local/grid/ppo_dtde_s0") & (curves.env_steps == 100)]
    assert first.team_return_mean.tolist() == [
        -8
    ] and first.per_participant.tolist() == [-4]
    assert len(results.training_curves(runs)) == 3 * 2  # the old run has none


def test_heldout_days_are_paired_and_older_runs_give_their_means(where):
    runs = results.load_runs(results.find_runs(where))
    days = results.heldout_days(runs).set_index(["key", "day"], drop=False)
    row = days.loc[("local/grid/ppo_dtde_s0", "2016-07-02")]
    assert (row.trained, row.zero, row.trained_minus_zero) == (-9, -10, 1)
    assert row.trained_minus_net_position == -3
    old = days[days.key == "local/old/sac_ctce_s3"]
    assert (
        len(old) == 1
        and old.day.isna().all()
        and old.trained_minus_zero.tolist() == [6]
    )


def test_participant_days(where):
    runs = {r.key: r for r in results.load_runs(results.find_runs(where))}
    table = results.participant_days(runs["local/grid/ppo_dtde_s0"])
    assert len(table) == 2 * 2  # days x participants
    assert set(table.trained_minus_zero) == {(-8 + 10) / 2, (-9 + 10) / 2}
    assert results.participant_days(runs["local/old/sac_ctce_s3"]).empty


def test_seed_groups_spread_over_seeds_and_what_differs(where):
    runs = results.load_runs(results.find_runs(where))
    groups = results.seed_groups(runs).set_index(["target", "experiment"])
    grid = groups.loc[("local", "grid")]
    assert (grid.runs, grid.completed, grid.seeds) == (2, 2, [0, 1])
    assert grid["mean"] == pytest.approx((-8.5 - 6.5) / 2)
    assert grid["std"] == pytest.approx(1.0)  # over the two seeds, not the days
    assert grid.trained_minus_zero == pytest.approx(10 - 7.5)
    assert grid.differs == []
    merged = results.seed_groups(runs, by=("algorithm", "paradigm")).set_index(
        "algorithm"
    )
    assert merged.loc["ppo", "differs"] == ["scenario"]  # s1 here, s2 on the cluster
