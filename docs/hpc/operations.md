# Monitoring and troubleshooting

## Watching jobs

```bash
srun --jobid=$(squeue -u $USER -n jupyter -h -o %i) --overlap --pty top
seff <jobid>
sacct -u $USER --starttime=2026-10-01 --format=JobID,JobName,Partition,Elapsed,AllocCPUS,State
sinfo -p short,common
```

In order: live `top` inside the Jupyter job (`q` quits, or `hpc top`); CPU and
memory a finished job used, to size the next one; jobs since a date; free nodes.

For an experiment, `python -m core.runner status <name> --target taltech` gives
each run's state, SLURM state and node. A failed run's error is in its
`status.json`; submitit's task logs are in `runs/<experiment>/slurm/` on the
cluster (`sync` leaves them out).

## Getting results

Experiments: `python -m core.runner sync <name> --target taltech`, into
`runs/@taltech/<name>`. That folder is replaced on every sync, so keep analysis
elsewhere. Checkpoints, `slurm/` and anything outside an experiment (e.g. notebook
runs) need a copy by hand, from the repository root:

```powershell
scp -r taltech:~/marlem-v1/runs/probes_thorough .\runs\
```

Without a job, files can also be browsed at <https://ondemand.hpc.taltech.ee>
(Files, Home Directory).

## Problems

| Symptom | Fix |
|---|---|
| `ssh taltech` hangs | The VPN is off |
| Tunnel: `channel ... open failed` | The job is not running yet, or Jupyter crashed: read `~/jupyter-<jobid>.out` |
| Port in use | Set another `MARLEM_JUPYTER_PORT` in `.env` (`hpc start` passes it to the job) |
| VS Code cannot connect | The tunnel window is closed or the job ended |
| Kernel dies | `-t` limit reached, or out of memory (`seff <jobid>`) |
| Old code runs | Pull on the cluster (when no experiment uses the checkout) and restart the kernel |
| `git pull` refuses | Files changed on the cluster: `git status` there |
| `check` reports problems | For the commits: commit and `git shipc`, so both sides are at the same clean commit (specs and scenarios need no commit: they are sent with the start) |
| `tput: No value for $TERM` | Harmless |
| Many `Failed to connect to GCS`, `Resource temporarily unavailable` | Thread limit: too many Ray instances on the node. Use the shared Ray (notebook) or fewer runs per node |
| Notebook runs stay `running` in `run.json` with no process | They died before recording it; run the cell again. Runner experiments show such runs as `lost`; `start` runs them again |
| The Studio shows a refresh error | The data shown is the last good read, with its time; it does not mean the jobs stopped |
| `hpc` not found in VS Code's terminal | Restart VS Code fully (PATH is read at start) |
