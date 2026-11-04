"""The results reader (``core/runner/results.py``) over hand-written run folders: no
training, no cluster. Two seeds of one configuration on this PC, one run in a
cluster's mirror, and an older run with only its means."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
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
            "bill": e["team_return"] / 2,
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
    assert not runs["local/grid/ppo_dtde_s0"].has("heldout_steps")


def test_a_compressed_table_is_read_and_its_trades_placed_in_the_band(tmp_path):
    folder = tmp_path / "grid" / "ppo_dtde_s0"
    folder.mkdir(parents=True)
    head = {"policy": "trained", "episode": 0, "step": 0}
    pd.DataFrame(
        [
            head | {"stage": 2, "price": 0.2, "kwh": 1.0},
            head | {"stage": 3, "price": 0.3, "kwh": 1.0},
        ]
    ).to_csv(folder / "heldout_trades.csv.gz", index=False)
    pd.DataFrame([head | {"feed_in_tariff": 0.1, "utility_price": 0.5}]).to_csv(
        folder / "heldout_steps.csv", index=False
    )
    ref = results.RunRef("local", "grid", "ppo_dtde_s0", folder)
    run = results.load_run(ref)
    assert run.has("heldout_trades") and len(run.table("heldout_trades")) == 2
    table = results.trade_table([run])
    assert table.band[0] == pytest.approx(0.25) and np.isnan(table.band[1])
    assert set(table.key) == {"local/grid/ppo_dtde_s0"}
    assert results.trade_table([]).empty


def test_a_compressed_table_still_being_copied_is_not_ready(tmp_path):
    whole = tmp_path / "whole.csv.gz"
    pd.DataFrame({"a": range(2000)}).to_csv(whole, index=False)
    cut = tmp_path / "cut.csv.gz"
    cut.write_bytes(whole.read_bytes()[:-30])  # the end not copied yet
    assert results._table(cut) is None  # an EOFError, not a crash
    assert len(results._table(whole)) == 2000


@pytest.mark.parametrize(
    "saved", ["ppo_dtde_s0_v2/experiment.json", "experiment_v2.json"]
)
def test_a_variant_reads_its_own_arm(where, saved):
    exp = where["local"] / "grid"
    make_run(exp, "ppo_dtde_s0_v2", 0, [-8, -9])
    write(
        exp / saved,
        {
            "scenario": {"name": "s1", "grid": {"method": "graph"}},
            "test_days": DAYS,
            "env_config": {"episode_days": 7},
        },
    )
    runs = {r.key: r for r in results.load_runs(results.find_runs(where))}
    arm = runs["local/grid/ppo_dtde_s0_v2"].settings
    assert arm["scenario"]["grid"] == {"method": "graph"}
    assert arm["env_config"] == {"episode_days": 7}
    assert runs["local/grid/ppo_dtde_s0"].settings["scenario"] == {"name": "s1"}
    assert "env_config" not in runs["local/grid/ppo_dtde_s0_v2"].labels
    # a variant from before the arm files: the base experiment's
    assert runs["cluster/grid/ppo_dtde_s0_v1"].settings["scenario"] == {"name": "s2"}


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
    assert results.differing_settings([base, other]) == [
        "overrides",
        "scenario",
        "test_days",
    ]


def test_overview_and_curves(where):
    runs = results.load_runs(results.find_runs(where))
    table = results.overview(runs).set_index("key")
    assert table.loc["local/grid/ppo_dtde_s1", "money_trained"] == -6.5
    assert table.loc["local/grid/ppo_dtde_s1", "participants"] == 2
    assert table.loc["local/old/sac_ctce_s3", "state"] == "completed"
    curves = results.learning_curves(runs)
    first = curves[(curves.key == "local/grid/ppo_dtde_s0") & (curves.env_steps == 100)]
    assert first.team_return_mean.tolist() == [
        -8
    ] and first.per_participant.tolist() == [-4]
    assert len(results.training_curves(runs)) == 3 * 2  # the old run has none


def test_overview_gives_the_start_as_sortable_text(tmp_path):
    exp = tmp_path / "grid"
    make_run(exp, "ppo_dtde_s0", 0, [-8, -9], started="2026-11-02T18:13:05")
    make_run(exp, "ppo_dtde_s1", 1, [-7, -6])
    table = results.overview(
        results.load_runs(results.find_runs({"local": tmp_path}))
    ).set_index("key")

    assert table.loc["local/grid/ppo_dtde_s0", "started"] == "2026-11-02 18:13"
    assert pd.isna(table.loc["local/grid/ppo_dtde_s1", "started"])


def test_participant_metrics_are_long(where):
    runs = results.load_runs(results.find_runs(where))
    people = results.participant_metrics(runs)
    p1 = people[(people.key == "local/grid/ppo_dtde_s0") & (people.agent == "P1")]
    assert len(p1) == 3 * 2 * 2  # policies x days x metrics
    assert {"paradigm", "variant", "day"} <= set(people.columns)
    assert "seed" in people and people.metric.nunique() == 2  # not the episode's seed
    assert results.participant_metrics([]).empty


def test_a_table_is_read_again_only_when_its_file_changed(where):
    (run,) = [
        r
        for r in results.load_runs(results.find_runs(where))
        if r.key == "local/grid/ppo_dtde_s0"
    ]
    first = run.table("metrics")
    assert run.table("metrics") is first  # unchanged: the same frame

    rows = pd.DataFrame({"env_steps": [50, 100, 150], "team_return_mean": [1, 2, 3]})
    write(run.ref.folder / "metrics.csv", rows)
    assert len(run.table("metrics")) == 3
    assert run.table("missing") is None


def test_a_run_is_a_market_run_a_probe_run_or_not_known_yet(where):
    assert results.run_kind("market") == "market"
    assert results.run_kind("core.env.market_env:MarketEnv") == "market"
    assert results.run_kind("core.rl.envs.probes:ConstantProbe") == "probe"
    assert results.run_kind("my.module:Env") == "other"
    assert results.run_kind(None) is None
    table = results.overview(results.load_runs(results.find_runs(where)))
    assert table.kind.isna().all()  # these hand-written runs name no environment


def test_participant_days(where):
    runs = {r.key: r for r in results.load_runs(results.find_runs(where))}
    table = results.participant_days(runs["local/grid/ppo_dtde_s0"])
    assert len(table) == 2 * 2  # days x participants
    assert set(table.trained_minus_zero) == {(-8 + 10) / 2, (-9 + 10) / 2}
    assert results.participant_days(runs["local/old/sac_ctce_s3"]).empty


def test_learner_metrics_per_module_and_part(tmp_path):
    """Any run's metrics.csv as one long table: the training return (no module),
    each module's own metrics, each action part's statistics; the modules' mean,
    min and max columns left out; the run's gradient clip in its settings."""
    exp = tmp_path / "runs" / "probes"
    run = make_run(
        exp,
        "ppo_dtde_s0",
        0,
        [-8, -9],
        settings_effective={"grad_clip": 0.5, "use_kl_loss": True},
    )
    off = make_run(
        exp,
        "ppo_dtde_s1",
        1,
        [-8, -9],
        settings_effective={"grad_clip": 0.5, "use_kl_loss": False},
    )
    write(
        off / "metrics.csv",
        pd.DataFrame({"env_steps": [500], "agent_1/mean_kl_loss": [0.0]}),
    )
    write(
        run / "metrics.csv",
        pd.DataFrame(
            {
                "env_steps": [500, 1000],
                "team_return_mean": [0.5, 0.9],
                "agent_1/policy_loss": [-0.1, -0.2],
                "agent_1/gradients_default_optimizer_global_norm": [1.2, 3.4],
                "agent_1/mean_kl_loss": [0.02, 0.01],
                "agent_1/level/mean": [0.0, 0.3],
                "agent_1/level/log_std": [-0.2, -1.0],
                "agent_1/side/entropy": [0.69, 0.2],
                "modules/policy_loss_mean": [-0.1, -0.2],
                "train_call_s": [1.0, 1.1],
            }
        ),
    )
    found = results.load_runs(results.find_runs({"local": tmp_path / "runs"}))
    assert found[0].settings["grad_clip"] == 0.5

    table = results.learner_metrics(found)
    assert set(table[table.key.str.endswith("s0")].metric) == {
        "team_return_mean",
        "policy_loss",
        "gradients_default_optimizer_global_norm",
        "mean_kl_loss",
        "mean",
        "log_std",
        "entropy",
    }
    # With the KL off, RLlib's constant 0 is not shown as a measurement.
    assert "mean_kl_loss" not in set(table[table.key.str.endswith("s1")].metric)
    table = table[table.key.str.endswith("s0")]
    level = table[(table.part == "level") & (table.metric == "mean")]
    assert list(level.value) == [0.0, 0.3] and set(level.module) == {"agent_1"}
    assert set(table[table.metric == "team_return_mean"].module) == {""}
    assert set(table[table.metric == "policy_loss"].part) == {""}
    assert set(table.key) == {"local/probes/ppo_dtde_s0"}


def test_timing_splits_a_training_call_and_a_run(tmp_path):
    """The training call's timers are split into parts that add up to it (a negative
    remainder counts as 0, an async learner's missing timer as 0); a run's stages come
    from ``run.json`` with what ``duration_s`` holds besides them; a run without
    timings has no stages."""
    exp = tmp_path / "runs" / "timing"
    run = make_run(exp, "ppo_dtde_s0", 0, [-8, -9])
    make_run(exp, "ppo_dtde_s1", 1, [-8, -9])
    older = make_run(exp, "ppo_dtde_s2", 2, [-8, -9])
    write(
        older / "metrics.csv",
        pd.DataFrame(
            {"env_steps": [500], "train_call_s": [10.0], "sampling_s_mean": [7.0]}
        ),
    )
    write(
        run / "metrics.csv",
        pd.DataFrame(
            {
                "env_steps": [500, 1000],
                "train_call_s": [10.0, 10.0],
                "sampler_sample_s_mean": [6.0, 6.0],
                "sampling_s_mean": [7.0, 7.0],
                "learner_call_s_mean": [2.0, float("nan")],
                "sampled_steps_per_train_s": [50.0, 100.0],
            }
        ),
    )
    record = json.loads((run / "run.json").read_text(encoding="utf-8"))
    write(
        run / "run.json",
        record
        | {
            "duration_s": 60.0,
            "timings": {
                "ray_init_s": 5.0,
                "build_s": 10.0,
                "train_calls_s": 20.0,
                "evaluation_s": 15.0,
                "checkpoint_s": 1.0,
            },
        },
    )
    found = {
        r.ref.run: r
        for r in results.load_runs(results.find_runs({"local": tmp_path / "runs"}))
    }
    both = [found["ppo_dtde_s0"], found["ppo_dtde_s1"]]
    # a run from before the runners' own timer: all its sampling is the runners'
    old = results.iteration_timing([found["ppo_dtde_s2"]]).iloc[0]
    assert (old.runners_s, old.sampling_overhead_s, old.unaccounted_s) == (7.0, 0.0, 3.0)
    calls = results.iteration_timing(both)
    first, second = calls.iloc[0], calls.iloc[1]
    assert (first.sampling_overhead_s, first.unaccounted_s) == (1.0, 1.0)
    assert (second.sampling_overhead_s, second.unaccounted_s) == (1.0, 3.0)
    assert (first.runners_s, second.runners_s) == (6.0, 6.0)
    assert len(calls[calls.key.str.endswith("s1")]) == 2  # no timers: NaN rows
    assert calls[calls.key.str.endswith("s1")].train_call_s.isna().all()
    stages = results.run_timings(both)
    assert len(stages) == 1 and stages.iloc[0].other_s == 60.0 - 46.0
