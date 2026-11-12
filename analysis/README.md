# analysis/

Working scripts for comparing experiments, kept so the numbers in the
[experiment diary](../docs/experiments/diary.md) can be reproduced. Not part of
`core/` and not documented on the site; whether it stays, and in what form, is
undecided. Run from the repository root in the marlem environment, after syncing the
runs (`python -m core.runner sync <experiment> --target taltech`).

| Script | What it gives |
|---|---|
| `analyse.py [1\|0] [experiments...]` | per run and policy, over all test days: money, fees, grid hours, VTI pooled over the days, and the VTI per season. `0` turns `keep_end` off in the references. Writes `out/summary[_<experiments>]_keep<0\|1>.csv` |
| `table.py [summary.csv]` | that summary pooled over seeds, one row per arm (mean, sd, every seed) |
| `curves.py` | every TalTech run's learning curve: training return at 50/75/100 % of the budget, slope over the last quarter, entropy, KL per update, evaluation returns |

`out/night_12nov_keep1.csv` and `out/night_12nov_keep0.csv` are the summaries behind
the diary's 12 Nov tables (111 runs; `keep_end` on and off).
