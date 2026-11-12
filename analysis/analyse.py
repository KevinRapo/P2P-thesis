"""Per run and policy, summed over all test days: money, fees, grid hours and the VTI
pooled over the days; then the VTI per season for the trained policy and net_position.

usage: python analysis/analyse.py [keep_end: 1|0] [experiments...]
keep_end 0 patches the references' end-of-period battery rule off (ceiling and
non_p2p). Reads the synced runs in runs/; writes analysis/out/summary_keep<0|1>.csv."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import pandas as pd
import core.market.ceiling as C
keep = sys.argv[1] != "0" if len(sys.argv) > 1 else True
C.optimise.__defaults__ = C.optimise.__defaults__[:-1] + (keep,)
from core.runner import results as R
exps = sys.argv[2:]  # none: every synced run
refs = [r for r in R.find_runs() if not exps or r.experiment in exps]
d = R.day_indicators(R.load_runs(refs))
if "run" in d: d["variant"] = d.run.str.split("_").str[1].fillna("") + ":" + d.variant
d["season"] = pd.to_datetime(d.day).dt.month.map({1: "winter", 4: "spring", 7: "summer", 10: "autumn"})
SUM = ["energy_money", "team_money", "fees", "loss_charge", "hours_over_limit", "hours_loading_limit",
       "hours_voltage_limit", "grid_losses_kwh", "p2p_kwh", "battery_throughput_kwh", "stored_change_kwh",
       "grid_export_kwh", "grid_import_kwh"]
MAX = ["highest_trafo_loading", "highest_voltage"]
p = d.pivot_table(index=["experiment", "variant", "seed", "policy", "season", "day"], columns="indicator", values="value")
g = p.groupby(level=["experiment", "variant", "seed", "policy"])
out = pd.concat([g[[c for c in SUM if c in p]].sum(), g[[c for c in MAX if c in p]].max()], axis=1)
def vti(frame, col):
    m = frame[col].unstack("policy") if col in frame else None
    ref = frame["energy_money"].unstack("policy")
    gap = ref["ceiling"] - ref["non_p2p"]
    return m.sub(ref["non_p2p"], axis=0).div(gap, axis=0)
tot = out
v = vti(tot, "energy_money").stack().rename("vti_pooled")
va = vti(tot.assign(tm=tot.team_money), "tm").stack().rename("vti_after_fees_pooled")
out = out.join(v).join(va)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500)
cols = ["energy_money", "team_money", "fees", "loss_charge", "vti_pooled", "vti_after_fees_pooled",
        "hours_over_limit", "hours_loading_limit", "hours_voltage_limit", "highest_trafo_loading",
        "grid_losses_kwh", "p2p_kwh", "battery_throughput_kwh", "stored_change_kwh"]
print(f"keep_end={keep}; {len(refs)} runs")
print(out[[c for c in cols if c in out]].round(2).to_string())
# per season VTI of trained and net_position
ps = p.groupby(level=["experiment", "variant", "seed", "policy", "season"])["energy_money"].sum().unstack("policy")
gap = ps["ceiling"] - ps["non_p2p"]
sv = pd.DataFrame({k: (ps[k] - ps["non_p2p"]) / gap for k in ("trained", "net_position") if k in ps}).assign(gap=gap)
print(sv.round(3).unstack("season").to_string())
OUT = Path(__file__).parent / "out"; OUT.mkdir(exist_ok=True)
name = "summary" if len(sys.argv) <= 2 else "summary_" + "_".join(exps)
out.to_csv(OUT / f"{name}_keep{int(keep)}.csv")
