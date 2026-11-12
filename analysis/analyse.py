"""Per run and policy, summed over all test days: money, fees, grid hours and the VTI
pooled over the days; then the VTI per season for the trained policy and net_position.

usage: python analysis/analyse.py [keep_end: 1|0] [experiments...]

keep_end 0 turns the references' end-of-period battery rule off (ceiling and
non_p2p). Reads the synced runs in runs/; writes
analysis/out/summary[_<experiments>]_keep<0|1>.csv."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).parent / "out"
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

import core.market.ceiling as ceiling  # noqa: E402
from core.runner import results  # noqa: E402

# --------------------------------------------------------------------------------------
# What is summed, what is the maximum, and what is printed
# --------------------------------------------------------------------------------------

RUN = ["experiment", "variant", "seed", "policy"]
SEASONS = {1: "winter", 4: "spring", 7: "summer", 10: "autumn"}  # test week's month

SUMMED = [
    "energy_money",
    "team_money",
    "fees",
    "loss_charge",
    "hours_over_limit",
    "hours_loading_limit",
    "hours_voltage_limit",
    "grid_losses_kwh",
    "p2p_kwh",
    "battery_throughput_kwh",
    "stored_change_kwh",
    "grid_export_kwh",
    "grid_import_kwh",
]
HIGHEST = ["highest_trafo_loading", "highest_voltage"]

SHOWN = [
    "energy_money",
    "team_money",
    "fees",
    "loss_charge",
    "vti_pooled",
    "vti_after_fees_pooled",
    "hours_over_limit",
    "hours_loading_limit",
    "hours_voltage_limit",
    "highest_trafo_loading",
    "grid_losses_kwh",
    "p2p_kwh",
    "battery_throughput_kwh",
    "stored_change_kwh",
]


# --------------------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------------------


def set_keep_end(keep: bool) -> None:
    """Make ``keep_end`` (the last argument of ``ceiling.optimise``) default to
    ``keep``, so every reference computed from here on uses it."""
    defaults = ceiling.optimise.__defaults__
    ceiling.optimise.__defaults__ = defaults[:-1] + (keep,)


def day_table(experiments: list[str]) -> tuple[pd.DataFrame, int]:
    """Every indicator per experiment, variant, seed, policy, season and test day,
    one column per indicator; and how many runs it comes from. No experiments:
    every synced run."""
    runs = [
        run
        for run in results.find_runs()
        if not experiments or run.experiment in experiments
    ]
    days = results.day_indicators(results.load_runs(runs))

    if "run" in days:  # the paradigm (ppo_<paradigm>_s0_...) in front of the variant
        paradigm = days.run.str.split("_").str[1].fillna("")
        days["variant"] = paradigm + ":" + days.variant

    days["season"] = pd.to_datetime(days.day).dt.month.map(SEASONS)
    table = days.pivot_table(
        index=RUN + ["season", "day"], columns="indicator", values="value"
    )

    return table, len(runs)


def vti(totals: pd.DataFrame, money: str) -> pd.Series:
    """(money - non_p2p) / (ceiling - non_p2p) per run and policy, with both
    references on energy money."""
    played = totals[money].unstack("policy")
    refs = totals["energy_money"].unstack("policy")
    gap = refs["ceiling"] - refs["non_p2p"]

    return played.sub(refs["non_p2p"], axis=0).div(gap, axis=0).stack()


def per_run(table: pd.DataFrame) -> pd.DataFrame:
    """Each run and policy over all its test days: the sums, the highest values and
    the VTI before and after fees, pooled over the days."""
    runs = table.groupby(level=RUN)
    totals = pd.concat(
        [
            runs[[c for c in SUMMED if c in table]].sum(),
            runs[[c for c in HIGHEST if c in table]].max(),
        ],
        axis=1,
    )
    before = vti(totals, "energy_money").rename("vti_pooled")
    after = vti(totals, "team_money").rename("vti_after_fees_pooled")

    return totals.join(before).join(after)


def per_season(table: pd.DataFrame) -> pd.DataFrame:
    """The VTI of the trained policy and net_position per test week, and the week's
    gap between the references."""
    money = table.groupby(level=RUN + ["season"]).energy_money.sum()
    money = money.unstack("policy")
    gap = money["ceiling"] - money["non_p2p"]
    scores = {
        policy: (money[policy] - money["non_p2p"]) / gap
        for policy in ("trained", "net_position")
        if policy in money
    }

    return pd.DataFrame(scores).assign(gap=gap)


# --------------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------------


def main(argv: list[str]) -> None:
    keep = argv[0] != "0" if argv else True
    experiments = argv[1:]
    set_keep_end(keep)
    table, count = day_table(experiments)
    summary = per_run(table)

    pd.set_option("display.width", 300)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.max_rows", 500)
    print(f"keep_end={keep}; {count} runs")
    print(summary[[c for c in SHOWN if c in summary]].round(2).to_string())
    print(per_season(table).round(3).unstack("season").to_string())

    OUT.mkdir(exist_ok=True)
    name = "_".join(["summary"] + experiments)
    summary.to_csv(OUT / f"{name}_keep{int(keep)}.csv")


if __name__ == "__main__":
    main(sys.argv[1:])
