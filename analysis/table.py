"""analyse.py's summary pooled over seeds, one row per arm: the variant with its
paradigm prefix, "@960k" added for experiments named long*, "fee:" for fee_parts*.

usage: python analysis/table.py [summary.csv]  (default analysis/out/summary_keep1.csv)"""
import pandas as pd, sys
from pathlib import Path
d = pd.read_csv(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent / "out" / "summary_keep1.csv")
t = d[d.policy.eq("trained")].copy()
pv = lambda r: "pv1" if r.variant.split(":")[1].startswith("pv1_") else ("pv2" if "pv2" in r.variant else "pv15")
t["pv"] = t.apply(pv, axis=1)
t["fees"] = ~t.variant.str.contains("nofees")
t["arm"] = t.variant
t.loc[t.experiment.str.contains("long"), "arm"] = t.variant + "@960k"
t.loc[t.experiment.str.startswith("fee_parts"), "arm"] = "fee:" + t.variant
t.loc[t.experiment.str.startswith("ppo_lr_entropy") | t.experiment.str.startswith("long"), "seed_ok"] = True
cols = ["vti_pooled", "vti_after_fees_pooled", "hours_loading_limit", "hours_over_limit", "highest_trafo_loading"]
g = t.groupby("arm")
out = g[cols].mean().round(2)
out.insert(0, "n", g.size())
out.insert(1, "vti_sd", g.vti_pooled.std().round(2))
out.insert(2, "seeds", g.vti_pooled.apply(lambda s: " ".join(f"{v:.2f}" for v in s)))
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 40)
print(out.sort_values("vti_pooled", ascending=False).to_string())
n = d[d.policy.isin(["net_position", "non_p2p", "ceiling"])].drop_duplicates(["variant", "policy"])
print(n[["variant", "policy", "vti_pooled", "vti_after_fees_pooled", "hours_loading_limit", "hours_over_limit", "highest_trafo_loading"]].round(2).to_string())
