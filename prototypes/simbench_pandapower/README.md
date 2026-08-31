# SimBench + pandapower prototype

This folder is intentionally independent from MARLEM. It proves the first
integration boundary before any market, RL, or MARLEM grid code is touched:

```text
SimBench feeder -> pandapower AC power flow -> voltages / loading / losses
```

It loads the low-voltage SimBench feeder `1-LV-rural1--0-sw`, chooses the first
active load deterministically, and runs three steady-state AC power flows:

1. the unmodified feeder;
2. the same feeder with that load doubled (active and reactive power); and
3. the unmodified feeder with a 5 kW unity-power-factor PV static generator at
   that load's bus.

The scenarios are independent copies of the same feeder. They are not a time
series and they do not represent a MARLEM participant mapping yet.

## Run

From this folder:

```powershell
conda activate marlem
python run_demo.py
pytest -q
```

To retain machine-readable evidence without altering MARLEM output folders:

```powershell
python run_demo.py --json-output output/demo-results.json
```

`output/` is ignored by Git. The shared Conda environment is defined by the
repository root's `environment.yml` file. `pandapower` uses MW internally; the command
reports powers and losses in kW. The external-grid sign is shown unchanged from
pandapower (normally positive means upstream import for this example).

## What success proves

A successful run proves all of the following:

- the selected SimBench code loads into a `pandapowerNet`;
- Newton-Raphson AC power flow converges for each operating point; and
- bus voltage, line/transformer loading, losses, and upstream-grid exchange can
  be extracted in a small result contract.

It does **not** prove that MARLEM trades map to physical flows. The next small
step should be a persistent, scenario-declared mapping from a deliberately
selected MARLEM household to a specific SimBench load/bus, followed by updating
only that household's physical injection once per MARLEM timestep.

## Sources

SimBench documents `simbench.get_simbench_net()` as the supported route from a
SimBench code to a pandapower network. pandapower documents `runpp()` as its AC
power-flow entry point.

- https://simbench.de/en/download/datasets/
- https://pandapower.readthedocs.io/en/stable/powerflow/ac.html
