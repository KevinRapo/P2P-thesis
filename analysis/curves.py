"""Learning curves of every synced TalTech run: the training return (smoothed) at 50,
75 and 100 % of the budget, its slope over the last quarter (per 100k steps), policy
entropy at the start and end, the KL per update at the end, and the evaluation
returns during training.

usage: python analysis/curves.py"""

from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

RUNS = Path(__file__).resolve().parents[1] / "runs" / "@taltech"
SMOOTHING = 10  # iterations in the rolling mean of the training return
LAST = 5  # iterations averaged for the end values
MIN_ITERATIONS = 20  # shorter runs are skipped


def evaluations(run: Path) -> Optional[str]:
    """The trained policy's evaluation returns during training, in order."""
    path = run / "evaluation.csv"

    if not path.exists():
        return None

    evaluation = pd.read_csv(path)
    trained = evaluation[evaluation.policy == "trained"]

    return " ".join(f"{v:.2f}" for v in trained.team_return_mean)


def curve(metrics: pd.DataFrame) -> dict:
    """One run's summary of its training metrics (one row per iteration)."""
    smooth = metrics.team_return_mean.rolling(SMOOTHING, min_periods=1).mean()
    n = len(metrics)
    entropy = [c for c in metrics.columns if c.endswith("/entropy")]
    kl = [c for c in metrics.columns if c.endswith("/mean_kl_loss")]

    # Slope of the last quarter, per 100k steps: a linear fit on the raw returns
    last = metrics.iloc[int(0.75 * n) :]
    slope = np.polyfit(last.env_steps / 1e5, last.team_return_mean, 1)[0]

    return {
        "steps": int(metrics.env_steps.iloc[-1]),
        "r50": smooth.iloc[int(0.5 * (n - 1))],
        "r75": smooth.iloc[int(0.75 * (n - 1))],
        "r100": smooth.iloc[n - 1],
        "slope_last25": slope,
        "ent0": metrics[entropy].iloc[0].mean(),
        "ent_end": metrics[entropy].iloc[-LAST:].mean().mean(),
        "kl_end": metrics[kl].iloc[-LAST:].mean().mean(),
    }


def main() -> None:
    rows = []

    for path in RUNS.glob("*/*/metrics.csv"):
        metrics = pd.read_csv(path)

        if len(metrics) < MIN_ITERATIONS:
            continue

        run = path.parent
        name = f"{run.parent.name}/{run.name}"
        rows.append({"run": name} | curve(metrics) | {"eval": evaluations(run)})

    table = pd.DataFrame(rows).sort_values("run")

    pd.set_option("display.width", 250)
    pd.set_option("display.max_rows", 300)
    pd.set_option("display.max_colwidth", 60)
    print(table.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
