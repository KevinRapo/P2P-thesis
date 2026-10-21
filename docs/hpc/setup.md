# Setup

## Access

- Login node `base.hpc.taltech.ee` with your TalTech user, through an SSH alias
  (here `taltech`, in `~/.ssh/config`, key login). Off campus, connect the TalTech
  VPN first.
- A billing account (a personal `user_<name>` account, about 10 EUR per quarter,
  or a project account).
- Docs: <https://docs.hpc.taltech.ee/>. Support: hpcsupport@taltech.ee.

## This machine's settings (`.env`)

What belongs to a person or a site, not to the project, is in `.env` in the
repository root: git-ignored, one `KEY=VALUE` per line.
[.env.example](../../.env.example) lists every key with its default; copy it to
`.env` and fill in. An environment variable of the same name takes precedence.
[core/settings.py](../../core/settings.py) reads it for the Python code, and
[hpc.ps1](../../scripts/hpc.ps1) reads the same file.

| Key | Default | Used by |
|---|---|---|
| `MARLEM_SLURM_ACCOUNT` | none (required to submit) | `targets.toml`, `hpc start` |
| `MARLEM_SSH_HOST` | `taltech` | `targets.toml`, `hpc` |
| `MARLEM_CLUSTER_REPO` | `~/marlem-v2` (V1: `~/marlem-v1`) | `targets.toml` |
| `MARLEM_CLUSTER_PYTHON` | `~/miniforge3/envs/marlem/bin/python` | `targets.toml` |
| `MARLEM_JUPYTER_PORT` | `9437` | `hpc`, the Jupyter job |
| `MARLEM_RUNS` | `<repo>/runs` | the runner |
| `MARLEM_HOME` | `%LOCALAPPDATA%\MARLEM` | the Studio's workspace |
| `MARLEM_STUDIO_PORT`, `MARLEM_STUDIO_SHOW` | `8091`, `1` | the Studio |

[hpc/targets.toml](../../hpc/targets.toml) refers to them as `${KEY}` or
`${KEY:-default}`. A missing value is an error only where it is used: the PC
needs no account to list or watch the cluster, but the cluster's checkout needs
one to submit, so put a `.env` there too (`~/marlem-v2/.env`, at least
`MARLEM_SLURM_ACCOUNT`).

## What is where

| Thing | Where |
|---|---|
| Notebook files you edit | This PC |
| Code the cluster runs (`core/`, specs, scenarios) | Cluster: `~/marlem-v2`, a clone of branch `marlem-v2` (V1: `~/marlem-v1`) |
| Results (`runs/`) | Cluster: `~/marlem-v2/runs/`; synced experiments on this PC in the V2 worktree's `runs/@taltech/` (V1's stay in V1's) |
| Python environment | Cluster: `~/miniforge3/envs/marlem` |
| Jupyter job script | [scripts/jupyter.slurm](../../scripts/jupyter.slurm), in the cluster's checkout |
| Jupyter token, logs | Cluster: `~/.jupyter_token`, `~/jupyter-<jobid>.out` |

A notebook cell runs as sent from VS Code; a change to `core/`, a spec or a
scenario reaches the cluster only by a push and a pull there (`git shipc`).

## The `hpc` helper

[scripts/hpc.ps1](../../scripts/hpc.ps1) drives the Jupyter job;
[hpc.cmd](../../scripts/hpc.cmd) makes `hpc` work in cmd too.

| Command | Does |
|---|---|
| `hpc start [sbatch options]` | Submit `scripts/jupyter.slurm` with the account from `.env`, wait for Jupyter, open the tunnel. E.g. `hpc start -c 78 --mem=60G -t 01:30:00` |
| `hpc tunnel` | Reopen the tunnel to the running job |
| `hpc status` | Your jobs and the end of the Jupyter log |
| `hpc log` | The last 30 lines of the Jupyter log |
| `hpc top` | Live `top` inside the job |
| `hpc stop` | Cancel the `jupyter` job, close local tunnels (experiment arrays are not touched) |

- One `jupyter` job at a time: `hpc start` refuses a second.
- The job runs in the cluster folder named after the branch checked out here
  (`marlem-v2` → `~/marlem-v2`), so that checkout must have `scripts/jupyter.slurm`.
- sbatch options given to `hpc start` override the script's `#SBATCH` lines.

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
cloned: set them again on a new machine with `git config --edit`). `taltech` is
your SSH alias:

```ini
[alias]
	pushc = "!f() { b=$(git rev-parse --abbrev-ref HEAD); if [ $# -eq 0 ]; then git push -u origin HEAD; else git push \"$@\"; fi && ssh -o BatchMode=yes taltech \"cd ~/$b && git pull --ff-only\" 2>&1 | grep -v \"^tput:\"; }; f"
	shipc = "!f() { if [ -z \"$1\" ]; then echo \"usage: git shipc \\\"commit message\\\"\"; return 1; fi; git add -A && git commit -m \"$1\" && git pushc; }; f"
```

| Command | Does |
|---|---|
| `git pushc` | Push, then `git pull --ff-only` in `~/<branch>` on the cluster |
| `git shipc "message"` | `git add -A`, commit, `git pushc`; each step only if the previous one succeeded |

`add -A` stages everything, new files included (`.env` is ignored): check
`git status` first when unsure. Do not pull on the cluster while experiments are
queued or running there ([why](experiments.md#limits)).

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
echo "MARLEM_SLURM_ACCOUNT=<account>" > ~/marlem-v1/.env
openssl rand -hex 16 > ~/.jupyter_token
chmod 600 ~/.jupyter_token
```

The same `environment.yml` builds the environment on this PC. Jupyter listens on
the node's network behind the token: reach it only through the tunnel, and keep
the token file private.
