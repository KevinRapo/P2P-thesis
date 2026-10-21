#!/bin/bash
# Jupyter Lab as a SLURM job, for VS Code through an SSH tunnel (hpc/hpc.ps1).
# `hpc start` submits it with the account from .env and REPO / PORT exported:
#   sbatch --account=<account> --export=ALL,REPO=<checkout>,PORT=<port> jupyter.slurm
# Options on the sbatch line override the lines below.
#SBATCH --job-name=jupyter
#SBATCH --partition=short            # max 4 h
#SBATCH --time=02:00:00              # job and billing end here at the latest
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --output=%x-%j.out

PORT="${PORT:-9437}"
source ~/miniforge3/etc/profile.d/conda.sh
conda activate marlem
cd "${REPO:-$HOME/marlem-v2}"
echo "Jupyter on node $(hostname), port $PORT"
jupyter lab --no-browser --ip=0.0.0.0 --port="$PORT" --ServerApp.port_retries=0 \
    --IdentityProvider.token="$(cat ~/.jupyter_token)"
