# Monitoring, results and troubleshooting

[HPC overview](../hpc.md) | [Resources](resources.md) | [Experiments](experiments.md)

## Watch and measure

Live view inside the running job (`q` to quit):

```bash
srun --jobid=$(squeue -u $USER -n jupyter -h -o %i) --overlap --pty top
```

After a job: how much of the CPUs and memory it used, to size the next one:

```bash
seff <jobid>
```

Jobs since a date, with run time and CPUs:

```bash
sacct -u $USER --starttime=2026-10-01 --format=JobID,JobName,Partition,Elapsed,AllocCPUS,State
```

Free nodes per partition:

```bash
sinfo -p short,common
```


## Results

Browse without a job: <https://ondemand.hpc.taltech.ee> (Files, Home Directory).

Copy a run folder to this PC (from the repository root):

```powershell
scp -r taltech:~/marlem-v1/runs/probes_thorough .\runs\
```


## Problems

| Symptom | Fix |
|---|---|
| `ssh taltech` hangs | VPN off |
| Tunnel: `channel ... open failed` | Job not running yet, or Jupyter crashed: read `~/jupyter-<jobid>.out` |
| Log says port in use | Change `9437` in the script and in the tunnel lines |
| VS Code cannot connect | Tunnel window closed or job ended |
| Kernel dies suddenly | `-t` limit reached, or out of memory (`seff <jobid>`) |
| Old code runs | When no experiment uses the checkout, pull the committed code on the cluster and restart the notebook kernel |
| `git pull` refuses | Files changed on the cluster: `git status` there |
| `tput: No value for $TERM` | Harmless |
| Many `Failed to connect to GCS`, `Resource temporarily unavailable` | Thread limit hit: too many Ray instances; use the shared Ray (train cell) or fewer workers |
| Notebook runs stay `running` in `run.json`, no processes | They died before recording a failure; rerun the notebook cell. For runner experiments, inspect `status` and restart unfinished runs through the runner |
| `hpc` not found in VS Code terminal | Restart VS Code fully (PATH is read at start) |


## Experiment-specific checks

```powershell
python -m core.runner check experiments/market_3x3.json --target taltech
python -m core.runner status market_3x3--test --target taltech
python -m core.runner sync market_3x3--test --target taltech
```

A failed refresh in Studio keeps the last data and its timestamp visible; it is
not proof the job stopped. Start, Stop and Sync errors are shown as notifications.
A nonzero `scancel` result is reported before runs are marked stopped.

For a failed cluster run, inspect `status.json` for the recorded exception and
`runs/<experiment>/slurm/` on the cluster for submitit's task logs. Sync excludes
that directory and checkpoints. Local job output is `<run>/log.txt`, and the
local supervisor writes `worker.log`. To retrieve omitted files, use an explicit
copy such as `scp`; the results mirror is replaced by each later sync.

A checkpoint is currently written at the end of training. Restarting a failed,
stopped or lost run starts its training from scratch; it is not checkpoint resume.
