"""Base configuration, Step 1: the stress case, without learning (thesis §4.5).

The rule ``net_position`` plays every validation day on its own, from the scenario's
initial state, at each PV scale; per scale it counts the hours in which a line or the
transformer is above 100 % or a bus outside 0.95-1.05 pu, per season and over the
four weeks. The base takes the lower scale whose share over the four weeks lies in
[5 %, 25 %]; if neither does, the scale closest to that interval.

    python analysis/stress_case.py [scale ...]      default: 1.0 1.25

Writes ``analysis/out/stress_case.csv`` (a row per scale and season) and prints the
choice.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.env import MarketEnv  # noqa: E402
from core.rl.policy import baselines, evaluation  # noqa: E402
from core.runner.spec import Experiment  # noqa: E402

SPEC = ROOT / "config" / "experiments" / "base_step2.json"
BAND = (0.05, 0.25)


def play(scale: float, experiment: Experiment) -> pd.DataFrame:
    """Every validation day's steps under ``net_position`` at PV x ``scale``."""
    scenario = json.loads(experiment.scenario_path.read_text(encoding="utf-8"))
    scenario["grid"]["generation_scale"] = scale
    folder = Path(tempfile.mkdtemp())
    path = folder / "scenario.json"
    path.write_text(json.dumps(scenario), encoding="utf-8")
    options = experiment.validation_options()
    days = [o["day"] for o in options]
    config = {"scenario": str(path), "days": days} | experiment.env_config
    rule = {"net_position": baselines(MarketEnv, config)["net_position"]}
    found = evaluation(
        MarketEnv, config, rule, list(range(len(days))), options=options, by_step=True
    )

    return found.steps.assign(scale=scale)


def summary(steps: pd.DataFrame) -> pd.DataFrame:
    """A row per scale and season (and ``all``): hours, hours over a limit, share."""
    steps = steps.assign(
        over=(steps.voltage_violations + steps.loading_violations) > 0,
        loading=steps.loading_violations > 0,
        voltage=steps.voltage_violations > 0,
    )
    rows = []

    for scale, part in steps.groupby("scale"):
        for period, hours in [("all", part)] + list(part.groupby("period")):
            rows.append(
                {
                    "scale": scale,
                    "period": period,
                    "hours": len(hours),
                    "hours_over": int(hours.over.sum()),
                    "share_over": hours.over.mean(),
                    "hours_loading": int(hours.loading.sum()),
                    "hours_voltage": int(hours.voltage.sum()),
                    "peak_trafo_percent": hours.max_trafo_loading_percent.max(),
                    "peak_line_percent": hours.max_line_loading_percent.max(),
                    "max_voltage_pu": hours.max_voltage_pu.max(),
                    "min_voltage_pu": hours.min_voltage_pu.min(),
                }
            )

    return pd.DataFrame(rows)


def choose(table: pd.DataFrame) -> float:
    """The lower scale whose share over all weeks is in ``BAND``, else the closest."""
    whole = table[table.period == "all"].sort_values("scale")
    inside = whole[whole.share_over.between(*BAND)]

    if len(inside):
        return float(inside.scale.iloc[0])

    distance = whole.share_over.map(lambda s: max(BAND[0] - s, s - BAND[1], 0.0))

    return float(whole.scale.iloc[int(distance.to_numpy().argmin())])


if __name__ == "__main__":
    scales = [float(s) for s in sys.argv[1:]] or [1.0, 1.25]
    experiment = Experiment.load(SPEC)
    table = summary(pd.concat([play(s, experiment) for s in scales]))
    out = ROOT / "analysis" / "out"
    out.mkdir(exist_ok=True)
    table.to_csv(out / "stress_case.csv", index=False)
    print(table.to_string(index=False))
    print(f"\nPV scale chosen: {choose(table)}")
