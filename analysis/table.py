"""analyse.py's summary pooled over seeds, one row per arm: the variant with its
paradigm prefix, "@<experiment>" added for experiments named long* (their budgets
differ), "fee:" for fee_parts*.

usage: python analysis/table.py [summary.csv]  (default analysis/out/summary_keep1.csv)
"""

import sys
from pathlib import Path

import pandas as pd

DEFAULT = Path(__file__).parent / "out" / "summary_keep1.csv"
SHOWN = [
    "vti_pooled",
    "vti_after_fees_pooled",
    "hours_loading_limit",
    "hours_over_limit",
    "highest_trafo_loading",
]
REFERENCES = ["net_position", "non_p2p", "ceiling"]


def arms(summary: pd.DataFrame) -> pd.DataFrame:
    """The trained policies' rows, each with the arm it is pooled under."""
    trained = summary[summary.policy.eq("trained")].copy()
    trained["arm"] = trained.variant
    long = trained.experiment.str.contains("long")
    fee_parts = trained.experiment.str.startswith("fee_parts")
    trained.loc[long, "arm"] = trained.variant + "@" + trained.experiment
    trained.loc[fee_parts, "arm"] = "fee:" + trained.variant

    return trained


def pooled(trained: pd.DataFrame) -> pd.DataFrame:
    """Per arm: how many seeds, the VTI's spread and every seed's VTI, then the
    means; best VTI first."""
    by_arm = trained.groupby("arm")
    table = by_arm[SHOWN].mean().round(2)
    table.insert(0, "n", by_arm.size())
    table.insert(1, "vti_sd", by_arm.vti_pooled.std().round(2))
    seeds = by_arm.vti_pooled.apply(lambda s: " ".join(f"{v:.2f}" for v in s))
    table.insert(2, "seeds", seeds)

    return table.sort_values("vti_pooled", ascending=False)


def references(summary: pd.DataFrame) -> pd.DataFrame:
    """The rule and the two references once per variant."""
    rows = summary[summary.policy.isin(REFERENCES)]
    rows = rows.drop_duplicates(["variant", "policy"])

    return rows[["variant", "policy"] + SHOWN].round(2)


def main(argv: list[str]) -> None:
    summary = pd.read_csv(argv[0] if argv else DEFAULT)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_colwidth", 40)
    print(pooled(arms(summary)).to_string())
    print(references(summary).to_string())


if __name__ == "__main__":
    main(sys.argv[1:])
