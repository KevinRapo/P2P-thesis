# Notebook guide

The notebooks are exploratory presentation layers. They are not maintained
command-line case scripts and do not substitute for the focused validation gate.

Run the validated regression suite first:

```powershell
uv run pytest -q
```

Available notebooks:

- `case1_market_mechanisms.ipynb`
- `case2_agent_heterogeneity.ipynb`
- `case3_dso_intervention.ipynb`
- `case4_grid_constraints.ipynb`
- `case5_battery_coordination.ipynb`
- `case6_implicit_cooperation.ipynb`
- `case7_scalability_analysis.ipynb`
- `case_studies_index.ipynb`

The validated learning baselines are DTDE and CTCE. CTDE is intentionally
disabled until its executed local actors have a verified actor-training path.
Use the unit and metric contracts in `docs/` when adapting a notebook; do not
interpret removed proxy analytics as welfare, coordination, or self-consumption.
