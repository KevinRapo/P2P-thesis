# Setup

## Access

- Login node `base.hpc.taltech.ee`, user `kerapo`, SSH alias `taltech` (in
  `~/.ssh/config`, key login). Off campus, connect the TalTech VPN first.
- Billing account `user_kerapo` (personal, about 10 EUR per quarter). A project
  account later: change `account` in [targets.toml](../../hpc/targets.toml) and
  `--account` in `~/jupyter.slurm`.
- Docs: <https://docs.hpc.taltech.ee/>. Support: hpcsupport@taltech.ee.

## What is where

| Thing | Where |
|---|---|
| Notebook files you edit | This PC |
| Code the cluster runs (`core/`, specs, scenarios) | Cluster: `~/marlem-v1`, a clone of branch `marlem-v1` |
| Results (`runs/`) | Cluster: `~/marlem-v1/runs/`; synced experiments on this PC in `runs/@taltech/` |
| Python environment | Cluster: `~/miniforge3/envs/marlem` |
| Jupyter job script, token, logs | Cluster: `~/jupyter.slurm`, `~/.jupyter_token`, `~/jupyter-<jobid>.out` |

A notebook cell runs as sent from VS Code; a change to `core/`, a spec or a
scenario reaches the cluster only by a push and a pull there (`git shipc`).

## The `hpc` helper

[scripts/hpc.ps1](../../scripts/hpc.ps1) drives the Jupyter job;
[hpc.cmd](../../scripts/hpc.cmd) makes `hpc` work in cmd too.

| Command | Does |
|---|---|
| `hpc start [sbatch options]` | Submit `~/jupyter.slurm`, wait for Jupyter, open the tunnel. E.g. `hpc start -c 78 --mem=60G -t 01:30:00` |
| `hpc tunnel` | Reopen the tunnel to the running job |
| `hpc status` | Your jobs and the end of the Jupyter log |
| `hpc log` | The last 30 lines of the Jupyter log |
| `hpc top` | Live `top` inside the job |
| `hpc stop` | Cancel the `jupyter` job, close local tunnels (experiment arrays are not touched) |

- One `jupyter` job at a time: `hpc start` refuses a second.
- The cluster folder is named after the branch checked out here (`marlem-v1` →
  `~/marlem-v1`), passed to the job as `REPO`.
- The SSH alias, port 9437, job name and job script are constants at the top of
  `hpc.ps1`. The helper does not read `targets.toml`; that is the runner's.

**Install:** add `marlem-v1\scripts` to the user PATH, from the repository root:

```powershell
$helperDirectory = (Resolve-Path .\scripts).Path
$userPath = [Environment]::GetEnvironmentVariable('Path', 'User')
$pathEntries = @($userPath -split ';' | Where-Object { $_ })
if ($helperDirectory -notin $pathEntries) {
    [Environment]::SetEnvironmentVariable('Path', (($pathEntries + $helperDirectory) -join ';'), 'User')
}
```

Then restart VS Code fully (it reads PATH at start). `hpc help` prints the usage
without contacting the cluster.

## Git aliases

Two aliases in the repository's `.git/config` (shared by all worktrees, not
cloned: set them again on a new machine with `git config --edit`):

```ini
[alias]
	pushc = "!f() { b=$(git rev-parse --abbrev-ref HEAD); if [ $# -eq 0 ]; then git push -u origin HEAD; else git push \"$@\"; fi && ssh -o BatchMode=yes taltech \"cd ~/$b && git pull --ff-only\" 2>&1 | grep -v \"^tput:\"; }; f"
	shipc = "!f() { if [ -z \"$1\" ]; then echo \"usage: git shipc \\\"commit message\\\"\"; return 1; fi; git add -A && git commit -m \"$1\" && git pushc; }; f"
```

| Command | Does |
|---|---|
| `git pushc` | Push, then `git pull --ff-only` in `~/<branch>` on the cluster |
| `git shipc "message"` | `git add -A`, commit, `git pushc`; each step only if the previous one succeeded |

`add -A` stages everything, new files included: check `git status` first when
unsure. Do not pull on the cluster while experiments are queued or running there
([why](experiments.md#limits)).

## Rebuild the cluster environment

On `base` (free; home is not backed up):

```bash
cd ~
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh -b -p ~/miniforge3
~/miniforge3/bin/conda init bash
source ~/.bashrc
git clone -b marlem-v1 https://github.com/KevinRapo/P2P-thesis.git ~/marlem-v1
conda env create -f ~/marlem-v1/environment.yml
```

The same file builds the environment on this PC. The Jupyter token and job script:

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

Jupyter listens on the node's network behind the token: reach it only through
the tunnel, and keep the token file private.
