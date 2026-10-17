# Notebook sessions

A Jupyter job on a compute node; VS Code runs the notebook's cells there. For
unattended training use [training experiments](experiments.md) instead: they need
no Jupyter job.

## The loop

On this PC, in `marlem-v1`:

```powershell
git shipc "what changed"
hpc start -c 78 --mem=60G -t 01:30:00
```

In VS Code: kernel `TalTech`, restart it, run the cells. When done:

```powershell
hpc stop
```

Skip `git shipc` when only notebook cells changed. Size the job to the work
([sizing](performance.md#sizing)): `-c 78 --mem=60G` is a whole green node, for
the probe notebook's 38 parallel runs.

## By hand

What `hpc start` does, step by step.

**1. Update the code on the cluster**, after committing: `git pushc` (push, then
pull on the cluster), or by hand after a plain push (VS Code's Sync button):

```powershell
ssh taltech "cd ~/marlem-v1 && git pull --ff-only"
```

**2. Submit the job**, on the cluster (`ssh taltech`, then `cd ~/marlem-v1`), with
your account (`MARLEM_SLURM_ACCOUNT` in `.env`):

| Command | Job |
|---|---|
| `sbatch --account=<account> scripts/jupyter.slurm` | The script's own settings: 4 CPUs, 8 GB, 2 h, partition `short` |
| `sbatch --account=<account> -c 20 --mem=16G -t 03:00:00 scripts/jupyter.slurm` | One probe's 9 runs at once |
| `sbatch --account=<account> -c 78 --mem=60G -t 01:30:00 scripts/jupyter.slurm` | A green node's worth (SLURM picks the node) |

Options on the command line override the `#SBATCH` lines. Jupyter listens on port
9437, or `PORT` when exported (`--export=ALL,PORT=...`). Wait for `ST` = `R`
(`squeue -u $USER`) and for `Jupyter Server ... is running at` in
`tail -5 ~/jupyter-*.out`.

**3. Open the tunnel**, on this PC, in a window left open:

```powershell
$node = ssh taltech 'squeue -u $USER -n jupyter -h -o %N'
ssh -N -L 9437:${node}:9437 taltech
```

A new job means a new node: close the old tunnel (Ctrl+C) and open it again.

**4. Connect** in VS Code: kernel picker, `TalTech` server, `Python 3 (ipykernel)`;
restart the kernel after a new job. The first time: Select Another Kernel, Existing
Jupyter Server, `http://localhost:9437/?token=<token>` (the token:
`ssh taltech "cat ~/.jupyter_token"`). To check where the kernel runs:

```python
import os, socket
print(socket.gethostname(), os.environ.get("SLURM_JOB_ID"), os.environ.get("SLURM_CPUS_PER_TASK"))
```

**Stop:** `scancel -n jupyter` on the cluster (billing stops here), Ctrl+C in the
tunnel window, and switch the notebook back to the local `marlem` kernel. A
forgotten job ends at its `-t` limit.

## Changing the job

| To change | Option | Notes |
|---|---|---|
| CPUs | `-c 20` | SLURM counts hyper-threads: 2 per physical core |
| Memory | `--mem=20G` | A green node has about 90 GB usable |
| Time limit | `-t 03:00:00` | The job and every run in it end here |
| Partition | `-p short` | `short` up to 4 h, `common` up to 8 days |
| GPU | `-p gpu --gres=gpu:L40:1` | 0.62 EUR per GPU-hour; little gain expected for this code |
| Account | `--account=project_xxx` | Or permanently: `MARLEM_SLURM_ACCOUNT` in `.env` |

One-off changes go on the `sbatch` line (or after `hpc start`); permanent ones in
[scripts/jupyter.slurm](../../scripts/jupyter.slurm), committed and pulled like
any code.
