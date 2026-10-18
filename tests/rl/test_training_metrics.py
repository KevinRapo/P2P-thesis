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
        "evaluate",
        lambda *a: pd.DataFrame([{"policy": "trained", "team_return_mean": 1.0}]),
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


def test_missing_timers_are_unknown_not_zero():
    row = training._iteration_row(1, {})
    assert pd.isna(row["sampling_s_mean"])
    assert pd.isna(row["async_learner_update_s_mean"])
