"""The thesis experiments' numbers (thesis §4.5 and chapter 6; decision RP-6d).

    python analysis/thesis_results.py select          Step 2: learning rate and budget
    python analysis/thesis_results.py score <steps>   the arms cut at <steps>: per run,
                                                      per arm, paired differences

``select`` reads the synced ``base_step2`` runs' validation tables
(``results.validation_scores``), prints each rate's mean curve of the validation VTI
after fees over its three seeds and applies the rule fixed in RP-6d. Writes
``out/step2_curves.csv``.

``score`` reads the synced experiments cut at ``<steps>`` (``analysis/heldout_at.py``:
``<experiment>_at<steps>``), pools every run's 28 test days (each day on its own, its
references too, MP-1c) and writes ``out/thesis_runs.csv`` (a row per run),
``out/thesis_arms.csv`` (a row per arm: mean and 95 % bootstrap interval over seeds)
and ``out/thesis_paired.csv`` (each arm minus the base, seed by seed).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "out"
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from core.runner import results  # noqa: E402

RATES = {"lr3e4": 3e-4, "lr1e3": 1e-3}
RISE = 0.01  # RP-6d: "rises by less than 0.01 ..."
WINDOW = 480_000  # "... over the next 480k steps"
LAST = 1_920_000
SEED_BOOTSTRAPS = 10_000
# An arm: (experiments it is in, without the "_at<steps>" suffix; variant; paradigm)
ARMS = {
    "base (DTDE, paper, bill)": (("base_step2", "thesis_base"), "lr1e3", "dtde"),
    "E1 agent": (("thesis_e1_agent",), "obs_agent_lr1e3", "dtde"),
    "E1 agent_market": (("thesis_e1_market",), "obs_market_lr1e3", "dtde"),
    "E2 salazar": (("thesis_e2",), "salazar_lr1e3", "dtde"),
    "E3 CTDE": (("thesis_e3",), "lr1e3", "ctde"),
    "E3 CTCE": (("thesis_e3_ctce",), "lr1e3", "ctce"),
}
BASE = "base (DTDE, paper, bill)"
STEP2 = ("base_step2",)


# --------------------------------------------------------------------------------------
# Step 2: the learning rate and the budget
# --------------------------------------------------------------------------------------
SUFFIX = ""


def _name(experiment: str) -> str:
    return experiment


def plateau(curve: pd.Series) -> int:
    """The first point after which the curve rises by less than ``RISE`` at every
    point of the next ``WINDOW`` steps; the last point if none (RP-6d)."""
    points = [p for p in curve.index if p > 0]

    for point in points:
        later = [q for q in points if point < q <= point + WINDOW]

        if later and max(curve[q] - curve[point] for q in later) < RISE:
            return int(point)

    return int(points[-1])


def select() -> None:
    runs = [r for r in results.find_runs() if r.experiment in {_name(e) for e in STEP2}]
    rows = []

    for ref in runs:
        scores = results.validation_scores(ref.folder)

        if scores is None:
            print(f"{ref.run}: no validation tables")
            continue

        rate = ref.run.rsplit("_", 1)[-1]
        seed = int(ref.run.split("_s")[1].split("_")[0])
        part = scores[scores.period == "all"].assign(rate=rate, seed=seed)
        rows.append(part)

    table = pd.concat(rows)
    OUT.mkdir(exist_ok=True)
    table.to_csv(OUT / f"step2_curves{SUFFIX}.csv", index=False)
    trained = table[table.policy == "trained"]
    curves = trained.groupby(["rate", "env_steps"]).vti_after_fees.agg(["mean", "count"])
    print(curves.unstack("rate").round(3).to_string())
    rule = trained[trained.policy == "trained"]
    rule = table[table.policy == "net_position"].vti_after_fees.mean()
    print(f"\nnet_position on the validation days: VTI after fees {rule:.3f}")
    found = {}

    for rate, part in curves["mean"].groupby(level="rate"):
        curve = part.droplevel("rate")
        budget = plateau(curve)
        found[rate] = (budget, float(curve[budget]))
        print(f"{rate}: budget {budget}, mean VTI after fees {curve[budget]:.3f}")

    (a, (ba, va)), (b, (bb, vb)) = found.items()

    if abs(va - vb) < RISE:
        chosen = a if ba <= bb else b
    else:
        chosen = a if va > vb else b

    print(f"\nchosen: {chosen} at {found[chosen][0]} steps")


# --------------------------------------------------------------------------------------
# The arms on the test weeks
# --------------------------------------------------------------------------------------
def _vti(totals: pd.DataFrame, money: str) -> pd.Series:
    played = totals[money].unstack("policy")
    refs = totals["energy_money"].unstack("policy")
    gap = refs["ceiling"] - refs["non_p2p"]

    return played.sub(refs["non_p2p"], axis=0).div(gap, axis=0).stack()


def per_run(steps: int) -> pd.DataFrame:
    """A row per run and policy over the 28 test days."""
    names = {f"{_name(e)}_at{steps}" for arm in ARMS.values() for e in arm[0]}
    refs = [r for r in results.find_runs() if r.experiment in names]
    loaded = results.load_runs(refs)
    days = results.day_indicators(loaded)
    days["paradigm"] = days.run.str.split("_").str[1]
    days["seed"] = days.run.str.split("_s").str[1].str.split("_").str[0].astype(int)
    keys = ["experiment", "variant", "paradigm", "seed", "policy"]
    table = days.pivot_table(index=keys + ["day"], columns="indicator", values="value")
    groups = table.groupby(level=keys)
    totals = pd.concat(
        [
            groups[[c for c in SUMMED if c in table]].sum(),
            groups[[c for c in HIGHEST if c in table]].max(),
            groups[[c for c in ("participants_better",) if c in table]].mean(),
        ],
        axis=1,
    )
    totals = totals.join(_vti(totals, "energy_money").rename("vti"))
    totals = totals.join(_vti(totals, "team_money").rename("vti_after_fees"))
    season = table.reset_index()
    season["season"] = pd.to_datetime(season.day).dt.month.map(SEASONS)
    money = season.groupby(keys + ["season"])[["energy_money", "team_money"]].sum()

    for name in SEASONS.values():
        part = money.xs(name, level="season")
        totals[f"vti_after_fees_{name}"] = _vti(part, "team_money")

    return totals.reset_index()


def arm_of(row) -> str | None:
    for arm, (experiments, variant, paradigm) in ARMS.items():
        base = row.experiment.rsplit("_at", 1)[0]

        if base in {_name(e) for e in experiments} and row.variant == variant and row.paradigm == paradigm:
            return arm

    return None


def bootstrap(values: np.ndarray, seed: int = 0) -> tuple[float, float]:
    """A 95 % percentile interval of the mean over seeds."""
    rng = np.random.default_rng(seed)
    means = rng.choice(values, (SEED_BOOTSTRAPS, len(values))).mean(axis=1)

    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def score(steps: int) -> None:
    runs = per_run(steps)
    runs["arm"] = runs.apply(arm_of, axis=1)
    runs = runs[runs.arm.notna()]
    OUT.mkdir(exist_ok=True)
    runs.to_csv(OUT / f"thesis_runs{SUFFIX}.csv", index=False)
    shown = [
        "vti_after_fees",
        "vti",
        "team_money",
        "energy_money",
        "fees",
        "participants_better",
        "hours_over_limit",
        "hours_loading_limit",
        "hours_voltage_limit",
        "highest_trafo_loading",
        "highest_voltage",
        "p2p_kwh",
    ] + [f"vti_after_fees_{s}" for s in SEASONS.values()]
    shown = [c for c in shown if c in runs]
    arms = []

    for (arm, policy), part in runs.groupby(["arm", "policy"]):
        row = {"arm": arm, "policy": policy, "seeds": len(part)}

        for column in shown:
            values = part[column].to_numpy(dtype=float)
            row[column] = values.mean()

            if policy == "trained" and column in ("vti_after_fees", "vti"):
                row[f"{column}_low"], row[f"{column}_high"] = bootstrap(values)
                row[f"{column}_seeds"] = " ".join(f"{v:.3f}" for v in values)

        arms.append(row)

    arms = pd.DataFrame(arms)
    arms.to_csv(OUT / f"thesis_arms{SUFFIX}.csv", index=False)
    trained = runs[runs.policy == "trained"].set_index(["arm", "seed"])
    base = trained.xs(BASE, level="arm")
    paired = []

    for arm in ARMS:
        if arm == BASE or arm not in trained.index.get_level_values("arm"):
            continue

        mine = trained.xs(arm, level="arm")
        seeds = mine.index.intersection(base.index)

        for column in ("vti_after_fees", "vti", "team_money", "hours_over_limit"):
            diff = (mine.loc[seeds, column] - base.loc[seeds, column]).to_numpy(float)
            low, high = bootstrap(diff)
            paired.append(
                {
                    "arm": arm,
                    "indicator": column,
                    "seeds": len(seeds),
                    "mean_difference": diff.mean(),
                    "low": low,
                    "high": high,
                    "per_seed": " ".join(f"{d:.3f}" for d in diff),
                }
            )

    paired = pd.DataFrame(paired)
    paired.to_csv(OUT / f"thesis_paired{SUFFIX}.csv", index=False)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print(arms.round(3).to_string())
    print(paired.round(3).to_string())


if __name__ == "__main__":
    if sys.argv[1] == "select":
        select()
    else:
        score(int(sys.argv[2]))
