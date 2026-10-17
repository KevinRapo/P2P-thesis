# Setup and HPC helper scripts

[HPC overview](../hpc.md) | [Resources](resources.md) | [Experiments](experiments.md)

## Access

- Login node: `base.hpc.taltech.ee`, user `kerapo`, short name `taltech` (in your
  `~/.ssh/config`, key login).
- Billing account: `user_kerapo` (personal, about 10 EUR per quarter).
  Later a project account: change `--account` in the job script.
- Off campus: connect the TalTech VPN first.
- Docs: <https://docs.hpc.taltech.ee/>. Support: hpcsupport@taltech.ee.


## What is where

| Thing | Location |
|---|---|
| Notebook files you edit | This PC |
| Code the kernel imports (`core/`) | Cluster: `~/marlem-v1` (a git clone) |
| Files the code writes (`runs/`) | Cluster: `~/marlem-v1/runs/` |
| Python environment | Cluster: `~/miniforge3/envs/marlem` |
| Jupyter job script | Cluster: `~/jupyter.slurm` |
| Jupyter token | Cluster: `~/.jupyter_token` |
| Job logs | Cluster: `~/jupyter-<jobid>.out` |

Cell edits need no sync: VS Code sends the cell text when you run it. Changes to
`core/` (or scenario / experiment files) need a push here and a pull there, then a
kernel restart.


## Quick commands (`hpc`)

`hpc.ps1` wraps the steps below. It and `hpc.cmd` (so that `hpc` also works in cmd)
are tracked in [scripts/](../../scripts/) inside `marlem-v1`.
[hpc.ps1](../../scripts/hpc.ps1) implements the commands;
[hpc.cmd](../../scripts/hpc.cmd) delegates to it for cmd.exe. Add that directory
to the user PATH; do not add the old workspace-level `scripts/` directory.

| Command | Does |
|---|---|
| `hpc start` | submit `~/jupyter.slurm` with its own settings, wait for Jupyter, open the tunnel |
| `hpc start -c 78 --mem=60G -t 01:30:00` | the same with `sbatch` options (they override the script) |
| `hpc tunnel` | reopen the tunnel to the running job (closes old ones first) |
| `hpc status` | your jobs and the end of the Jupyter log |
| `hpc log` | the last 30 lines of the Jupyter log |
| `hpc top` | live `top` inside the job |
| `hpc stop` | cancel the job, close local tunnels |

The tunnel window stays open while you work; Ctrl+C closes only the tunnel. Then in
VS Code: kernel `TalTech`, restart it.

- `hpc start` refuses to submit a second job while one named `jupyter` exists.
- If the job dies before Jupyter starts, it prints the job's log.
- The cluster folder of the code is named after the branch checked out here
  (`marlem-v1` is `~/marlem-v1`).
- After changing the user PATH, VS Code has to be restarted fully once to see it
  (it is read when a program starts).

### Install the helper on this PC

From the repository root, this adds the actual checkout path without replacing
other PATH entries:

```powershell
$helperDirectory = (Resolve-Path .\scripts).Path
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$pathEntries = @($userPath -split ';' | Where-Object { $_ })
if ($helperDirectory -notin $pathEntries) {
    [Environment]::SetEnvironmentVariable('Path', (($pathEntries + $helperDirectory) -join ';'), 'User')
}
```

Restart VS Code and terminals afterwards. `Get-Command hpc` should resolve inside
`marlem-v1/scripts`; `hpc help` prints usage without contacting the cluster.
The migration on this PC replaced the old workspace-level PATH entry.

The helper uses Windows OpenSSH and the `taltech` SSH alias. Its account name,
port (9437), job name (`jupyter`) and remote script (`~/jupyter.slurm`) are constants
near the top of `hpc.ps1`. It derives the remote checkout from the **current
working directory's Git branch**, falling back to `marlem-v1` outside a repository.
Run it from `marlem-v1` for this project. The helper does not read `targets.toml`;
that file configures the separate experiment runner.

`hpc stop` cancels this user's jobs named `jupyter` and closes matching local
SSH tunnels. It does not cancel the runner's experiment arrays.

### Git aliases

Two local aliases in the repository's `.git/config` (shared by all worktrees; open it with
`git config --edit`):

```ini
[alias]
	pushc = "!f() { b=$(git rev-parse --abbrev-ref HEAD); if [ $# -eq 0 ]; then git push -u origin HEAD; else git push \"$@\"; fi && ssh -o BatchMode=yes taltech \"cd ~/$b && git pull --ff-only\" 2>&1 | grep -v \"^tput:\"; }; f"
	shipc = "!f() { if [ -z \"$1\" ]; then echo \"usage: git shipc \\\"commit message\\\"\"; return 1; fi; git add -A && git commit -m \"$1\" && git pushc; }; f"
```

| Command | Does |
|---|---|
| `git shipc "message"` | `git add -A`, commit, push, pull on the cluster |
| `git pushc` | push, then pull on the cluster |


The aliases are local Git configuration, not files cloned from GitHub. Configure
them separately on a new machine. They use the current branch as the remote
folder name; no absolute Windows path needs changing when the helpers move.
Before pulling on the cluster, wait for experiments using that checkout to end.

## Rebuild the cluster environment

On `base` (free; the environment is not backed up):

```bash
cd ~
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
~/miniforge3/bin/conda init bash
source ~/.bashrc
conda create -n marlem python=3.12 -y
conda activate marlem
pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu126
pip install submitit asyncssh psutil
pip install "ray[rllib]==2.51.1" benchmarl==1.5.2 torchrl==0.11.1 gymnasium==1.1.1 pettingzoo==1.27.0 pandapower==3.5.4 simbench==1.6.2 numpy==2.4.6 pandas==2.3.3 scipy matplotlib plotly numba pyyaml pydantic tensorboard jupyterlab ipykernel
git clone -b marlem-v1 https://github.com/KevinRapo/P2P-thesis.git ~/marlem-v1
```

The Jupyter token (a file only you can read) and the job script `~/jupyter.slurm`:

```bash
openssl rand -hex 16 > ~/.jupyter_token
chmod 600 ~/.jupyter_token
```

```bash
#!/bin/bash
#SBATCH --job-name=jupyter
#SBATCH --account=user_kerapo        # later: project_xxx
#SBATCH --partition=short            # max 4 h
#SBATCH --time=02:00:00              # job and billing end here at the latest
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out

source ~/miniforge3/etc/profile.d/conda.sh
conda activate marlem
cd "${REPO:-$HOME/marlem-v1}"
echo "Jupyter on node $(hostname), port 9437"
jupyter lab --no-browser --ip=0.0.0.0 --port=9437 --ServerApp.port_retries=0 \
    --IdentityProvider.token="$(cat ~/.jupyter_token)"
```

`hpc start` passes `REPO`, the cluster folder named after the current branch;
without it the script uses `~/marlem-v1`. Jupyter listens on the node's network,
protected by the token: reach it only through the tunnel, and keep the token file
private.
