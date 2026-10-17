# Notebook sessions on TalTech

[HPC overview](../hpc.md) | [Resources](resources.md) | [Experiments](experiments.md)

The helper controls the Jupyter allocation only. For unattended training arrays,
use [Training experiments](experiments.md). Updating imported code requires a
kernel restart; do not update a checkout while experiments using it are active.

## The loop

On this PC, in `marlem-v1`:

```powershell
git shipc "what changed"
hpc start -c 78 --mem=60G -t 01:30:00
```

Then in VS Code: kernel `TalTech`, restart it, run the cells. When done:

```powershell
hpc stop
```

- `git shipc` commits everything, pushes, and pulls on the cluster ([Git aliases](setup.md#git-aliases)).
- `hpc start` submits the Jupyter job, waits for it and opens the tunnel.
- Only notebook cells changed: skip `git shipc`.
- The job above is a whole green node for the probe notebook's 38 workers; size it
  to the work (see [Sizing](performance.md#sizing)).


## Start a session (by hand)

### 1. Update the code on the cluster

On this PC, in `marlem-v1`, after committing:

```powershell
git pushc
```

`git pushc` is the [configured alias](setup.md#git-aliases): `git push`, then, if that succeeded,
`git pull --ff-only` in `~/marlem-v1` on the cluster. Extra arguments go to
`git push` (e.g. `git pushc origin marlem-v1`). VS Code's Sync button runs plain
`git push` (pull by hand, below).

Everything in one go (stage all changes, commit, push, pull on the cluster):

```powershell
git shipc "commit message"
```

`git shipc` runs `git add -A`, `git commit -m "..."` and `git pushc`, each only
if the previous step succeeded; without a message it only prints its usage.
`add -A` stages everything in the worktree, new files included: check
`git status` first when unsure.

Pull by hand after a plain push:

```powershell
ssh taltech "cd ~/marlem-v1 && git pull --ff-only"
```

Restart the cluster kernel afterwards so it imports the new code.

### 2. Start Jupyter as a job

Log in:

```powershell
ssh taltech
```

Then on the cluster, one of:

```bash
sbatch ~/jupyter.slurm
```

```bash
sbatch -c 78 --mem=60G -t 01:30:00 ~/jupyter.slurm
```

```bash
sbatch -c 20 --mem=20G -t 03:00:00 ~/jupyter.slurm
```

- The first uses the script's own settings (4 CPUs, 8 GB, 2 h, partition `short`).
- The second requests the green-node-sized allocation used in the dated probe notes.
  It does not force Slurm to choose a green node; placement and worker count
  depend on the node and notebook settings.
- The third fits one probe's 9 runs at full speed.
- Options on the command line override the `#SBATCH` lines in the script.

Wait until the job runs (`ST` = `R`; `NODELIST` shows the node):

```bash
squeue -u $USER
```

Check that Jupyter started (look for `Jupyter Server ... is running at`):

```bash
tail -5 ~/jupyter-*.out
```

### 3. Open the tunnel

On this PC, in a new PowerShell window, left open while you work:

```powershell
$node = ssh taltech "squeue -u kerapo -n jupyter -h -o %N"
echo $node
ssh -N -L 9437:${node}:9437 taltech
```

The window looks frozen: that is the open tunnel. A new job means a new node, so
close the old tunnel (Ctrl+C) and run these three lines again.

### 4. Connect the notebook

In VS Code: kernel picker, then `TalTech` server, then `Python 3 (ipykernel)`.
After a new job, restart the kernel and run the cells from the top.

First time only: Select Another Kernel, Existing Jupyter Server,
`http://localhost:9437/?token=<token>`. Show the token with:

```powershell
ssh taltech "cat ~/.jupyter_token"
```

Check where the kernel runs (expect the node name, the job ID, the CPU count):

```python
import os, socket
print(socket.gethostname(), os.environ.get("SLURM_JOB_ID"), os.environ.get("SLURM_CPUS_PER_TASK"))
```


## Stop

On the cluster (billing stops here):

```bash
scancel -n jupyter
squeue -u $USER
```

Then Ctrl+C in the tunnel window, and switch the notebook back to the local
`marlem` kernel for local work. A forgotten job ends by itself at its `-t` limit.


## Change the job

| To change | Option | Notes |
|---|---|---|
| CPUs | `-c 20` | SLURM counts hyper-threads: CPUs = 2 x physical cores |
| Memory | `--mem=20G` | Green node: about 90 GB usable |
| Time limit | `-t 03:00:00` | Job and every run are killed when it is reached |
| Partition | `-p short` | `short` up to 4 h, `common` up to 8 days |
| GPU | `-p gpu --gres=gpu:L40:1` | 0.62 EUR per GPU-hour; likely little gain for this code |
| Account | `--account=project_xxx` | Once a project account exists |

One-off changes: put the option on the `sbatch` line. Permanent changes: edit
`~/jupyter.slurm` ([setup script](setup.md#rebuild-the-cluster-environment)).

### Edit the job script

- VS Code: Remote-SSH, connect to `taltech`, File, Open File, `~/jupyter.slurm`.
  Close that window when done; it runs a small server on the login node.
- Browser: OnDemand, Files, Home Directory, `jupyter.slurm`, Edit.
- Terminal on the cluster: `nano ~/jupyter.slurm` (Ctrl+O, Enter, Ctrl+X).

