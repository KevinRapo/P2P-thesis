"""Learning curves of every synced TalTech run: the training return (smoothed) at 50,
75 and 100 % of the budget, its slope over the last quarter (per 100k steps), policy
entropy at the start and end, the KL per update at the end, and the evaluation
returns during training.

usage: python analysis/curves.py"""
import sys, glob, os, json, pandas as pd, numpy as np
from pathlib import Path
os.chdir(Path(__file__).resolve().parents[1] / "runs" / "@taltech")
rows=[]
for m in glob.glob("*/*/metrics.csv"):
    d=os.path.dirname(m); exp,run=d.split(os.sep)
    df=pd.read_csv(m)
    if len(df)<20: continue
    r=df.team_return_mean.rolling(10,min_periods=1).mean()
    n=len(df); s=df.env_steps.iloc[-1]
    q=lambda f: r.iloc[int(f*(n-1))]
    ent=[c for c in df.columns if c.endswith('/entropy')]
    kl=[c for c in df.columns if c.endswith('/mean_kl_loss')]
    # slope of last quarter, per 100k steps, via linear fit on raw returns
    t=df.iloc[int(0.75*n):]
    sl=np.polyfit(t.env_steps/1e5,t.team_return_mean,1)[0]
    ev=None
    e=os.path.join(d,"evaluation.csv")
    if os.path.exists(e):
        ed=pd.read_csv(e); ed=ed[ed.policy=="trained"]
        ev=" ".join(f"{v:.2f}" for v in ed.team_return_mean)
    rows.append(dict(run=f"{exp}/{run}",steps=int(s),r50=q(.5),r75=q(.75),r100=q(1),slope_last25=sl,
        ent0=df[ent].iloc[0].mean(),ent_end=df[ent].iloc[-5:].mean().mean(),kl_end=df[kl].iloc[-5:].mean().mean(),eval=ev))
out=pd.DataFrame(rows).sort_values("run")
pd.set_option("display.width",250); pd.set_option("display.max_rows",300); pd.set_option("display.max_colwidth",60)
print(out.round(3).to_string(index=False))
