"""Progress reporting and timing without starting Ray or training a model."""

import importlib
from types import SimpleNamespace

import pandas as pd
import pytest

training = importlib.import_module("core.rl.train")


def result(steps, trained=0, **learner_metrics):
    return {
        "env_runners": {"num_env_steps_sampled_lifetime": steps, "sample": 0.2},
        "learners": {
            "__all_modules__": {
                "num_env_steps_trained_lifetime": trained,
                "learner_thread_update_timer": 0.4,
            },
            "agent": learner_metrics,
        },
        "timers": {"env_runner_sampling_timer": 0.3, "learner_update_timer": 0.01},
    }


def fake_training(monkeypatch, tmp_path, results):
    results = iter(results)
    algo = SimpleNamespace(
        train=lambda: next(results), save_to_path=lambda path: None, stop=lambda: None
    )
    monkeypatch.setattr(training, "build_config", lambda *a, **kw: None)
    monkeypatch.setattr(training, "_record", lambda *a: {})
    monkeypatch.setattr(training, "build_algo", lambda config: algo)
    monkeypatch.setattr(training.ray, "is_initialized", lambda: True)
    monkeypatch.setattr(training, "learner_modules", lambda algo: None)
    monkeypatch.setattr(training, "Policy", lambda *a: None)
    monkeypatch.setattr(training, "baselines", lambda *a: {})
    monkeypatch.setattr(
        training,
        "evaluation",
        lambda *a: SimpleNamespace(
            summary=pd.DataFrame([{"policy": "trained", "team_return_mean": 1.0}]),
            agents=pd.DataFrame([{"policy": "trained", "agent": "a", "return": 1.0}]),
            episodes=pd.DataFrame([{"policy": "trained", "team_return": 1.0}]),
        ),
    )
    return training.Run(
        "appo", "dtde", lambda config: None, budget=100, out_dir=tmp_path
    )


def test_idle_polls_are_omitted_but_learning_and_all_call_time_are_kept(
    monkeypatch, tmp_path
):
    run = fake_training(
        monkeypatch,
        tmp_path,
        [result(0), result(50), result(50), result(50, 20), result(100, 40)],
    )
    record = training.train(run)
    rows = pd.read_csv(tmp_path / "metrics.csv")
    assert rows.iteration.tolist() == [2, 4, 5]
    assert rows.env_steps.tolist() == [50, 50, 100]
    assert rows.learner_env_steps.tolist() == [0, 20, 40]
    assert record["iterations"] == 5
    assert rows.train_calls_s_total.iloc[-1] > rows.train_call_s.sum()
    assert record["timings"]["train_calls_s"] == pytest.approx(
        rows.train_calls_s_total.iloc[-1], abs=1e-6
    )
    assert rows.sampler_sample_s_mean.iloc[-1] == 0.2
    assert rows.sampling_s_mean.iloc[-1] == 0.3
    assert rows.learner_call_s_mean.iloc[-1] == 0.01
    assert rows.async_learner_update_s_mean.iloc[-1] == 0.4
    assert {"ray_init_s", "build_s", "evaluation_s", "checkpoint_s"} <= set(
        record["timings"]
    )


def test_nonfinite_learner_metric_is_not_hidden_by_idle_sampling(monkeypatch, tmp_path):
    run = fake_training(monkeypatch, tmp_path, [result(0, total_loss=float("nan"))])
    with pytest.raises(FloatingPointError):
        training.train(run)
    rows = pd.read_csv(tmp_path / "metrics.csv")
    assert len(rows) == 1
    assert rows.env_steps.iloc[0] == 0


def test_learner_metrics_per_module_and_over_the_modules():
    two = result(10, total_loss=1.0, entropy=0.5)
    two["learners"]["other"] = {"total_loss": 3.0, "entropy": 1.5}
    row = training._iteration_row(1, two)
    assert (row["agent/total_loss"], row["other/total_loss"]) == (1.0, 3.0)
    assert row["modules/total_loss_mean"] == 2.0
    assert (row["modules/total_loss_min"], row["modules/total_loss_max"]) == (1, 3)
    assert row["modules/entropy_mean"] == 1.0
    assert not any(k.startswith("modules/") for k in training._iteration_row(1, {}))


def test_every_evaluation_is_kept_per_episode_and_agent(monkeypatch, tmp_path):
    run = fake_training(monkeypatch, tmp_path, [result(50), result(100)])
    training.train(run)
    for name in ("evaluation", "evaluation_agents", "evaluation_episodes"):
        frame = pd.read_csv(tmp_path / f"{name}.csv")
        assert frame.env_steps.tolist() == [0, 100], name  # untrained, then final


def test_an_evaluation_point_appends_its_rows_in_the_first_columns(tmp_path):
    path, written = tmp_path / "e.csv", {}
    training._append_csv(path, pd.DataFrame({"a": [1], "b": [2]}), written)
    training._append_csv(path, pd.DataFrame({"b": [4], "a": [3]}), written)
    training._append_csv(path, pd.DataFrame({"a": [5]}), written)  # b missing
    frame = pd.read_csv(path)
    assert frame.a.tolist() == [1, 3, 5] and frame.b.tolist()[:2] == [2, 4]
    assert pd.isna(frame.b.iloc[2])
    training._append_csv(path, pd.DataFrame({"a": [9]}), {})  # a new run: replaced
    assert pd.read_csv(path).a.tolist() == [9]


def test_missing_timers_are_unknown_not_zero():
    row = training._iteration_row(1, {})
    assert pd.isna(row["sampling_s_mean"])
    assert pd.isna(row["async_learner_update_s_mean"])


def test_metrics_rows_are_appended_and_new_columns_widen_the_file_once(
    monkeypatch, tmp_path
):
    path, rows, columns = tmp_path / "metrics.csv", [], []
    replaced = []
    original = training._replace
    monkeypatch.setattr(
        training, "_replace", lambda p, write: (replaced.append(p), original(p, write))
    )
    for row in ({"a": 1}, {"a": 2}, {"a": 3, "loss": 0.5}, {"a": 4, "loss": 0.4}):
        rows.append(row)
        training._append_metrics(path, rows, columns)
    frame = pd.read_csv(path)
    assert frame.a.tolist() == [1, 2, 3, 4]
    assert pd.isna(frame.loss.iloc[0]) and frame.loss.tolist()[2:] == [0.5, 0.4]
    assert len(replaced) == 2  # the first row and the row with the new column
    assert not (tmp_path / "metrics.csv.tmp").exists()
